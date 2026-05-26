"""Host-side delivery bridge for files generated inside the sandbox."""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from openharness.sandbox.session import get_active_sandbox, get_sandbox_session
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class DeliverArtifactInput(BaseModel):
    """Arguments for delivering sandbox artifacts to the host/UI layer."""

    sandbox_path: str | None = Field(
        default=None,
        description="Single absolute sandbox file path, normally under /home/user.",
    )
    paths: list[str] | None = Field(
        default=None,
        description="Multiple absolute sandbox file paths to deliver in one call.",
    )
    filename: str | None = Field(
        default=None,
        description="Optional output filename. Required only when renaming a single file or naming a zip bundle.",
    )
    package_as_zip: bool = Field(
        default=False,
        description="When true, deliver all provided paths as one zip file.",
    )

    @model_validator(mode="after")
    def validate_paths(self) -> "DeliverArtifactInput":
        candidates = self.paths or ([self.sandbox_path] if self.sandbox_path else [])
        if not candidates:
            raise ValueError("Provide sandbox_path or paths")
        return self


class DeliverArtifactTool(BaseTool):
    """Copy sandbox-generated files to the host workspace and notify the UI."""

    name = "deliver_artifact"
    description = (
        "Deliver files generated inside the sandbox to the user. Use this immediately after "
        "a sandbox command creates a needed file under /home/user. Supports one file, multiple "
        "files, or a zip bundle."
    )
    input_model = DeliverArtifactInput
    requires_sandbox = False

    async def execute(
        self,
        arguments: DeliverArtifactInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        session = _resolve_sandbox_session(context)
        if session is None or not getattr(session, "is_running", False):
            return ToolResult(output="No active sandbox session is available for artifact delivery.", is_error=True)

        raw_paths = arguments.paths or ([arguments.sandbox_path] if arguments.sandbox_path else [])
        requested_paths = [_normalize_sandbox_path(path) for path in raw_paths if path]
        sandbox_paths = await _expand_requested_paths(session, requested_paths)
        if not sandbox_paths:
            return ToolResult(output="No sandbox paths were provided.", is_error=True)

        for path in sandbox_paths:
            if not _is_allowed_sandbox_path(path):
                return ToolResult(
                    output=f"Refusing to deliver path outside the sandbox user area: {path}",
                    is_error=True,
                )

        thread_id = str(context.metadata.get("thread_id") or "default")
        output_dir = _resolve_output_dir(context.cwd, thread_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        delivered: list[Path] = []
        try:
            if arguments.package_as_zip or _contains_directory_request(requested_paths, sandbox_paths):
                zip_name = _safe_filename(arguments.filename or "artifacts.zip")
                if not zip_name.lower().endswith(".zip"):
                    zip_name += ".zip"
                local_zip = _unique_path(output_dir / zip_name)
                with zipfile.ZipFile(local_zip, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                    for sandbox_path in sandbox_paths:
                        content = await session.read_file_binary(sandbox_path)
                        bundle.writestr(_safe_archive_name(sandbox_path), _ensure_bytes(content))
                delivered.append(local_zip)
            else:
                for index, sandbox_path in enumerate(sandbox_paths):
                    filename = (
                        _safe_filename(arguments.filename)
                        if arguments.filename and len(sandbox_paths) == 1
                        else _safe_filename(os.path.basename(sandbox_path) or f"artifact_{index + 1}")
                    )
                    local_path = _unique_path(output_dir / filename)
                    content = await session.read_file_binary(sandbox_path)
                    local_path.write_bytes(_ensure_bytes(content))
                    delivered.append(local_path)
        except Exception as exc:
            return ToolResult(output=f"Failed to deliver artifact: {exc}", is_error=True)

        hook = context.metadata.get("hook")
        if hook is not None:
            for local_path in delivered:
                await hook.on_artifact(
                    str(local_path),
                    reason=f"Delivered sandbox artifact: {local_path.name}",
                    sandbox_session=session,
                )

        lines = ["Delivered artifact(s):"]
        lines.extend(f"- {path}" for path in delivered)
        return ToolResult(
            output="\n".join(lines),
            metadata={"artifact_paths": [str(path) for path in delivered]},
        )


def _resolve_sandbox_session(context: ToolExecutionContext):
    user_id = context.metadata.get("user_id")
    thread_id = context.metadata.get("thread_id")
    if user_id is not None and thread_id:
        try:
            session = get_active_sandbox(int(user_id), str(thread_id))
            if session is not None:
                return session
        except (TypeError, ValueError):
            pass
    return get_sandbox_session()


def _resolve_output_dir(cwd: Path, thread_id: str) -> Path:
    parts = cwd.resolve().parts
    if "temp_workspaces" in parts:
        idx = parts.index("temp_workspaces")
        return Path(*parts[: idx + 1]) / thread_id
    return cwd.resolve()


def _normalize_sandbox_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def _is_allowed_sandbox_path(path: str) -> bool:
    return path == "/home/user" or path.startswith("/home/user/")


async def _expand_requested_paths(session, requested_paths: list[str]) -> list[str]:
    expanded: list[str] = []
    for path in requested_paths:
        if await _sandbox_path_is_dir(session, path):
            expanded.extend(await _list_sandbox_files(session, path))
        else:
            expanded.append(path)
    return expanded


async def _sandbox_path_is_dir(session, path: str) -> bool:
    try:
        result = await session.exec_command(f"test -d {_shell_quote(path)} && printf dir || true")
        return getattr(result, "stdout_str", "").strip() == "dir"
    except Exception:
        return False


async def _list_sandbox_files(session, directory: str) -> list[str]:
    result = await session.exec_command(f"find {_shell_quote(directory)} -type f")
    output = getattr(result, "stdout_str", "") or ""
    return [line.strip() for line in output.splitlines() if line.strip()]


def _contains_directory_request(requested_paths: list[str], expanded_paths: list[str]) -> bool:
    return len(requested_paths) != len(expanded_paths)


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _ensure_bytes(content) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, bytearray):
        return bytes(content)
    if isinstance(content, memoryview):
        return content.tobytes()
    if isinstance(content, str):
        return content.encode("utf-8")
    return bytes(content)


def _safe_filename(filename: str) -> str:
    cleaned = os.path.basename(filename.strip().replace("\\", "/"))
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", cleaned).strip(" .")
    return cleaned or "artifact"


def _safe_archive_name(sandbox_path: str) -> str:
    rel = sandbox_path.removeprefix("/home/user/").strip("/")
    parts = [_safe_filename(part) for part in rel.split("/") if part not in {"", ".", ".."}]
    return "/".join(parts) or "artifact"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for idx in range(1, 1000):
        candidate = parent / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate unique path for {path}")
