"""String-based file editing tool."""

from __future__ import annotations

import difflib
import os
import posixpath
import shlex
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.sandbox_workspace import (
    get_e2b_task_session,
    sandbox_path_status,
    to_sandbox_path,
    uses_e2b_task_workspace,
)
from openharness.utils.paths import normalize_host_path


class FileEditToolInput(BaseModel):
    """Arguments for the file edit tool."""

    path: str = Field(description="Path of the UTF-8 text file to edit")
    old_str: str = Field(description="Exact existing text to replace; must not be empty")
    new_str: str = Field(description="Replacement text; may be empty to delete old_str")
    replace_all: bool = Field(
        default=False,
        description=(
            "When false, old_str must match exactly once. When true, every exact "
            "non-overlapping match is replaced."
        ),
    )


class FileEditTool(BaseTool):
    """Replace text in an existing file."""

    name = "edit_file"
    description = (
        "Precisely edit an existing UTF-8 text file by replacing old_str with new_str. "
        "By default old_str must match exactly once; set replace_all=true to replace all matches."
    )
    input_model = FileEditToolInput

    async def execute(
        self,
        arguments: FileEditToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        if uses_e2b_task_workspace(context):
            return await _edit_sandbox_file(arguments, context)

        path = _resolve_path(context.cwd, arguments.path)
        workspace = Path(context.cwd).resolve()

        from openharness.sandbox.session import is_docker_sandbox_active

        if is_docker_sandbox_active():
            from openharness.sandbox.path_validator import validate_sandbox_path

            allowed, reason = validate_sandbox_path(path, context.cwd)
            if not allowed:
                return ToolResult(output=f"Sandbox: {reason}", is_error=True)

        safety_error = _validate_host_edit_path(path, workspace)
        if safety_error:
            return ToolResult(output=safety_error, is_error=True)

        try:
            original = _read_host_text(path)
            plan = _build_replacement_plan(arguments, original, location_label="file")
        except ValueError as exc:
            return ToolResult(output=str(exc), is_error=True)
        except OSError as exc:
            return ToolResult(output=f"Failed to read file {path}: {exc}", is_error=True)

        approval_prompt = context.metadata.get("edit_approval_prompt") if context.metadata else None
        metadata = _result_metadata(str(path), "host", plan)
        if approval_prompt is not None:
            diff_text, added, removed = _compute_diff(str(path), original, plan.updated)
            reply = await approval_prompt(str(path), diff_text, added, removed)
            if reply == "reject":
                return ToolResult(output=f"Edit rejected by user: {path}", is_error=True)
            try:
                latest = _read_host_text(path)
            except ValueError as exc:
                return ToolResult(output=str(exc), is_error=True)
            except OSError as exc:
                return ToolResult(output=f"Failed to read file {path}: {exc}", is_error=True)
            if latest != original:
                return ToolResult(
                    output=f"File changed while edit approval was pending; please retry: {path}",
                    is_error=True,
                )
            try:
                _atomic_write_host_text(path, plan.updated)
            except OSError as exc:
                return ToolResult(
                    output=f"Failed to write file atomically: {path}: {exc}",
                    is_error=True,
                )
            stats = f"  ({_ANSI_GREEN}+{added}{_ANSI_RESET} {_ANSI_RED}-{removed}{_ANSI_RESET})"
            return ToolResult(output=f"Updated {path}{stats}", metadata=metadata)

        try:
            _atomic_write_host_text(path, plan.updated)
        except OSError as exc:
            return ToolResult(
                output=f"Failed to write file atomically: {path}: {exc}",
                is_error=True,
            )
        return ToolResult(output=f"Updated {path}", metadata=metadata)


def _resolve_path(base: Path, candidate: str) -> Path:
    return normalize_host_path(base, candidate)


@dataclass(frozen=True)
class _ReplacementPlan:
    updated: str
    match_count: int
    replacements: int
    changed: bool


_DANGEROUS_PATH_PARTS = {
    ".git",
    ".ssh",
    ".aws",
    ".azure",
    ".gcp",
    "credentials",
    "secrets",
}
_DANGEROUS_FILE_NAMES = {
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "private.key",
    "secrets.yaml",
    "secrets.yml",
}


def _validate_host_edit_path(path: Path, workspace: Path) -> str | None:
    try:
        path.relative_to(workspace)
    except ValueError:
        return f"Security restriction: cannot edit files outside the workspace: {path}"

    lowered_parts = [part.lower() for part in path.relative_to(workspace).parts]
    dangerous_parts = sorted(set(lowered_parts) & _DANGEROUS_PATH_PARTS)
    if dangerous_parts:
        return f"Security restriction: cannot edit sensitive path: {', '.join(dangerous_parts)}"
    if any(part.startswith(".env") for part in lowered_parts):
        return f"Security restriction: cannot edit sensitive environment file: {path}"
    if path.name.lower() in _DANGEROUS_FILE_NAMES:
        return f"Security restriction: cannot edit sensitive file: {path.name}"

    if not path.exists():
        return f"File not found: {path}"
    if path.is_dir():
        return f"Cannot edit directory: {path}"
    if not path.is_file():
        return f"Cannot edit non-file path: {path}"
    return None


def _read_host_text(path: Path) -> str:
    raw = path.read_bytes()
    return _decode_utf8_text(raw, path_label=str(path))


def _decode_utf8_text(raw: bytes | bytearray | memoryview | str, *, path_label: str) -> str:
    if isinstance(raw, str):
        text = raw
    else:
        data = bytes(raw)
        if b"\x00" in data:
            raise ValueError(f"Binary file cannot be edited as text: {path_label}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"File is not valid UTF-8: {path_label}: {exc}") from exc
    if "\x00" in text:
        raise ValueError(f"Binary file cannot be edited as text: {path_label}")
    return text


def _build_replacement_plan(
    arguments: FileEditToolInput,
    original: str,
    *,
    location_label: str,
) -> _ReplacementPlan:
    if arguments.old_str == "":
        raise ValueError("old_str must not be empty")

    match_count = original.count(arguments.old_str)
    if match_count == 0:
        raise ValueError(f"old_str was not found in the {location_label}")
    if not arguments.replace_all and match_count > 1:
        raise ValueError(
            f"old_str matched {match_count} times in the {location_label}; "
            "provide a more specific old_str or set replace_all=true"
        )

    replacements = match_count if arguments.replace_all else 1
    updated = original.replace(arguments.old_str, arguments.new_str, replacements)
    return _ReplacementPlan(
        updated=updated,
        match_count=match_count,
        replacements=replacements,
        changed=updated != original,
    )


def _result_metadata(path: str, workspace: str, plan: _ReplacementPlan) -> dict[str, object]:
    return {
        "path": path,
        "workspace": workspace,
        "match_count": plan.match_count,
        "replacements": plan.replacements,
        "changed": plan.changed,
    }


def _atomic_write_host_text(path: Path, content: str) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.openharness-edit-",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def _compute_diff(filename: str, original: str, updated: str) -> tuple[str, int, int]:
    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=filename,
            tofile=filename,
            lineterm="",
        )
    )
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    return "".join(diff_lines), added, removed


_ANSI_GREEN = "\033[32m"
_ANSI_RED = "\033[31m"
_ANSI_RESET = "\033[0m"


async def _edit_sandbox_file(
    arguments: FileEditToolInput,
    context: ToolExecutionContext,
) -> ToolResult:
    try:
        session = await get_e2b_task_session(context)
        sandbox_path = to_sandbox_path(context, arguments.path, for_write=True)
    except Exception as exc:
        return ToolResult(output=f"Sandbox workspace error: {exc}", is_error=True)

    status = await sandbox_path_status(session, sandbox_path)
    if status == "missing":
        return ToolResult(output=f"File not found in sandbox: {sandbox_path}", is_error=True)
    if status != "file":
        return ToolResult(
            output=f"Cannot edit non-file sandbox path: {sandbox_path}",
            is_error=True,
        )

    try:
        original = await _read_sandbox_text(session, sandbox_path)
        plan = _build_replacement_plan(arguments, original, location_label="sandbox file")
    except ValueError as exc:
        return ToolResult(output=str(exc), is_error=True)
    except Exception as exc:
        return ToolResult(
            output=f"Failed to read sandbox file {sandbox_path}: {exc}",
            is_error=True,
        )

    approval_prompt = context.metadata.get("edit_approval_prompt") if context.metadata else None
    metadata = _result_metadata(sandbox_path, "e2b", plan)
    if approval_prompt is not None:
        diff_text, added, removed = _compute_diff(sandbox_path, original, plan.updated)
        reply = await approval_prompt(sandbox_path, diff_text, added, removed)
        if reply == "reject":
            return ToolResult(output=f"Edit rejected by user: {sandbox_path}", is_error=True)
        try:
            latest = await _read_sandbox_text(session, sandbox_path)
        except ValueError as exc:
            return ToolResult(output=str(exc), is_error=True)
        except Exception as exc:
            return ToolResult(
                output=f"Failed to read sandbox file {sandbox_path}: {exc}",
                is_error=True,
            )
        if latest != original:
            return ToolResult(
                output=(
                    "Sandbox file changed while edit approval was pending; "
                    f"please retry: {sandbox_path}"
                ),
                is_error=True,
            )
        try:
            await _atomic_write_sandbox_text(session, sandbox_path, plan.updated)
        except Exception as exc:
            return ToolResult(
                output=f"Failed to write sandbox file atomically: {sandbox_path}: {exc}",
                is_error=True,
            )
        stats = f"  ({_ANSI_GREEN}+{added}{_ANSI_RESET} {_ANSI_RED}-{removed}{_ANSI_RESET})"
        return ToolResult(output=f"Updated sandbox file: {sandbox_path}{stats}", metadata=metadata)

    try:
        await _atomic_write_sandbox_text(session, sandbox_path, plan.updated)
    except Exception as exc:
        return ToolResult(
            output=f"Failed to write sandbox file atomically: {sandbox_path}: {exc}",
            is_error=True,
        )
    return ToolResult(output=f"Updated sandbox file: {sandbox_path}", metadata=metadata)


async def _read_sandbox_text(session, sandbox_path: str) -> str:
    raw = await session.read_file_binary(sandbox_path)
    return _decode_utf8_text(raw, path_label=sandbox_path)


async def _atomic_write_sandbox_text(session, sandbox_path: str, content: str) -> None:
    directory = posixpath.dirname(sandbox_path) or "/home/user"
    filename = posixpath.basename(sandbox_path) or "file"
    temp_path = posixpath.join(directory, f".{filename}.openharness-edit-{uuid.uuid4().hex}.tmp")
    try:
        await session.write_file(temp_path, content)
        process = await session.exec_command(
            "set -e; "
            f"chmod --reference={shlex.quote(sandbox_path)} "
            f"{shlex.quote(temp_path)} 2>/dev/null || true; "
            f"mv -f {shlex.quote(temp_path)} {shlex.quote(sandbox_path)}"
        )
        stdout, stderr = await process.communicate()
        returncode = getattr(process, "returncode", 0)
        if returncode not in (0, None):
            details = (stderr or stdout or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(details or f"mv failed with exit code {returncode}")
    except Exception:
        try:
            cleanup = await session.exec_command(f"rm -f {shlex.quote(temp_path)}")
            await cleanup.communicate()
        except Exception:
            pass
        raise
