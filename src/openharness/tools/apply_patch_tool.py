"""Multi-file atomic patch application tool using the Codex unified patch format."""

from __future__ import annotations

import shlex
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.file_state import (
    atomic_write_sandbox_text,
    bytes_version,
    check_mutation_guard,
    compute_unified_diff,
    detect_line_endings,
    file_lock,
    host_file_version,
    host_observation_key,
    normalize_line_endings,
    observe_absent,
    observe_file,
    restore_line_endings,
    sandbox_observation_key,
    validate_host_workspace_path,
)
from openharness.tools.sandbox_workspace import (
    get_e2b_task_session,
    sandbox_path_status,
    to_sandbox_path,
    uses_e2b_task_workspace,
)
from openharness.utils.fs import atomic_write_text
from openharness.utils.paths import normalize_host_path

_BEGIN_PATCH_MARKER = "*** Begin Patch"
_END_PATCH_MARKER = "*** End Patch"
_ADD_FILE_MARKER = "*** Add File: "
_DELETE_FILE_MARKER = "*** Delete File: "
_UPDATE_FILE_MARKER = "*** Update File: "
_MOVE_TO_MARKER = "*** Move to: "
_EOF_MARKER = "*** End of File"

_UNICODE_PUNCTUATION_MAP = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u201f": '"',
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    "\u00a0": " ",
})


class PatchParseError(ValueError):
    """Raised when a patch fails structural parsing."""


class PatchPreflightError(ValueError):
    """Raised during dry-run validation before any filesystem write."""


@dataclass(frozen=True)
class UpdateFileChunk:
    change_context: str | None
    old_lines: list[str]
    new_lines: list[str]
    is_end_of_file: bool = False


@dataclass(frozen=True)
class AddFileHunk:
    kind: Literal["add"] = "add"
    path: str = ""
    contents: str = ""


@dataclass(frozen=True)
class DeleteFileHunk:
    kind: Literal["delete"] = "delete"
    path: str = ""


@dataclass(frozen=True)
class UpdateFileHunk:
    kind: Literal["update"] = "update"
    path: str = ""
    move_path: str | None = None
    chunks: list[UpdateFileChunk] = field(default_factory=list)


PatchHunk = AddFileHunk | DeleteFileHunk | UpdateFileHunk


@dataclass(frozen=True)
class _PlannedWrite:
    kind: Literal["add", "update", "delete"]
    key: str
    display_path: str
    target_path: Any
    content: str | None = None
    remove_path: Any | None = None
    remove_key: str | None = None
    expected_version: str | None = None
    diff_original: str = ""
    diff_updated: str = ""


def _normalize_unicode_punctuation(value: str) -> str:
    return value.translate(_UNICODE_PUNCTUATION_MAP)


def parse_patch(patch_text: str) -> list[PatchHunk]:
    """Parse a Codex-format patch (`*** Begin Patch` ... `*** End Patch`)."""
    lines = normalize_line_endings(patch_text).split("\n")
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()

    if not lines or lines[0].strip() != _BEGIN_PATCH_MARKER:
        raise PatchParseError("The first line of the patch must be '*** Begin Patch'")
    if lines[-1].strip() != _END_PATCH_MARKER:
        raise PatchParseError("The last line of the patch must be '*** End Patch'")

    hunks: list[PatchHunk] = []
    index = 1
    limit = len(lines) - 1

    while index < limit:
        line = lines[index]
        if line.strip() == "":
            index += 1
            continue

        if line.startswith(_ADD_FILE_MARKER):
            path = line[len(_ADD_FILE_MARKER) :].strip()
            if not path:
                raise PatchParseError(f"Line {index + 1}: Add File path must not be empty")
            index += 1
            added_lines: list[str] = []
            while index < limit and not lines[index].startswith("*** "):
                body_line = lines[index]
                if not body_line.startswith("+"):
                    raise PatchParseError(
                        f"Line {index + 1}: Add File lines must start with '+', got: {body_line!r}"
                    )
                added_lines.append(body_line[1:])
                index += 1
            contents = "\n".join(added_lines) + ("\n" if added_lines else "")
            hunks.append(AddFileHunk(path=path, contents=contents))
            continue

        if line.startswith(_DELETE_FILE_MARKER):
            path = line[len(_DELETE_FILE_MARKER) :].strip()
            if not path:
                raise PatchParseError(f"Line {index + 1}: Delete File path must not be empty")
            hunks.append(DeleteFileHunk(path=path))
            index += 1
            continue

        if line.startswith(_UPDATE_FILE_MARKER):
            path = line[len(_UPDATE_FILE_MARKER) :].strip()
            if not path:
                raise PatchParseError(f"Line {index + 1}: Update File path must not be empty")
            index += 1
            move_path: str | None = None
            if index < limit and lines[index].startswith(_MOVE_TO_MARKER):
                move_path = lines[index][len(_MOVE_TO_MARKER) :].strip()
                if not move_path:
                    raise PatchParseError(f"Line {index + 1}: Move to path must not be empty")
                index += 1

            chunks: list[UpdateFileChunk] = []
            while index < limit:
                current = lines[index]
                if current.strip() == "":
                    index += 1
                    continue
                if current.startswith(("*** Add File:", "*** Delete File:", "*** Update File:")):
                    break

                change_context: str | None = None
                if current == "@@":
                    index += 1
                elif current.startswith("@@ "):
                    change_context = current[3:]
                    index += 1
                elif not chunks:
                    raise PatchParseError(
                        f"Line {index + 1}: Expected '@@' hunk header after Update File: {path}"
                    )
                else:
                    break

                old_lines: list[str] = []
                new_lines: list[str] = []
                is_end_of_file = False
                saw_chunk_line = False

                while index < limit:
                    chunk_line = lines[index]
                    if chunk_line == _EOF_MARKER:
                        if not saw_chunk_line:
                            raise PatchParseError(
                                f"Line {index + 1}: '*** End of File' without preceding hunk lines"
                            )
                        is_end_of_file = True
                        index += 1
                        break
                    if chunk_line.startswith("@@") or chunk_line.startswith("*** "):
                        break
                    if chunk_line == "":
                        old_lines.append("")
                        new_lines.append("")
                        saw_chunk_line = True
                    elif chunk_line[0] == " ":
                        old_lines.append(chunk_line[1:])
                        new_lines.append(chunk_line[1:])
                        saw_chunk_line = True
                    elif chunk_line[0] == "+":
                        new_lines.append(chunk_line[1:])
                        saw_chunk_line = True
                    elif chunk_line[0] == "-":
                        old_lines.append(chunk_line[1:])
                        saw_chunk_line = True
                    else:
                        raise PatchParseError(
                            f"Line {index + 1}: Unexpected hunk line prefix in {path}: {chunk_line!r}"
                        )
                    index += 1

                if not saw_chunk_line:
                    raise PatchParseError(f"Empty update hunk in {path}")
                chunks.append(
                    UpdateFileChunk(
                        change_context=change_context,
                        old_lines=old_lines,
                        new_lines=new_lines,
                        is_end_of_file=is_end_of_file,
                    )
                )

            if not chunks and move_path is None:
                raise PatchParseError(f"Update File hunk for {path} contains no changes")
            hunks.append(UpdateFileHunk(path=path, move_path=move_path, chunks=chunks))
            continue

        raise PatchParseError(
            f"Line {index + 1}: Expected '*** Add File:', '*** Delete File:', or '*** Update File:', "
            f"got: {line!r}"
        )

    if not hunks:
        raise PatchParseError("Patch contains no file operations")
    return hunks


def seek_sequence(
    lines: list[str],
    pattern: list[str],
    start: int,
    *,
    eof: bool = False,
) -> int | None:
    """Find `pattern` inside `lines` starting at `start` using 4 progressive match passes."""
    if not pattern:
        return min(start, len(lines))
    if len(pattern) > len(lines):
        return None

    search_start = max(start, len(lines) - len(pattern)) if eof else max(0, start)
    max_start = len(lines) - len(pattern)

    normalizers = (
        lambda s: s,
        lambda s: s.rstrip(),
        lambda s: s.strip(),
        lambda s: _normalize_unicode_punctuation(s.strip()),
    )

    for norm in normalizers:
        norm_pattern = [norm(item) for item in pattern]
        for idx in range(search_start, max_start + 1):
            if all(norm(lines[idx + offset]) == norm_pattern[offset] for offset in range(len(pattern))):
                return idx

    if eof and search_start > start:
        return seek_sequence(lines, pattern, start, eof=False)
    return None


def apply_update_chunks(original: str, chunks: list[UpdateFileChunk], *, path_label: str) -> str:
    """Apply parsed update chunks to an existing file string, preserving its line endings."""
    if not chunks:
        return original

    eol = detect_line_endings(original)
    norm_original = normalize_line_endings(original)
    had_trailing_newline = norm_original.endswith("\n")
    lines = norm_original.split("\n")
    if lines and lines[-1] == "" and had_trailing_newline:
        lines.pop()

    replacements: list[tuple[int, int, list[str]]] = []
    line_index = 0

    for chunk in chunks:
        if chunk.change_context is not None:
            ctx_pos = seek_sequence(lines, [chunk.change_context], line_index, eof=False)
            if ctx_pos is None:
                raise PatchPreflightError(
                    f"Failed to locate context '{chunk.change_context}' in {path_label}"
                )
            line_index = ctx_pos + 1

        if not chunk.old_lines:
            insert_at = len(lines)
            replacements.append((insert_at, 0, list(chunk.new_lines)))
            line_index = insert_at
            continue

        pattern = list(chunk.old_lines)
        new_slice = list(chunk.new_lines)
        found = seek_sequence(lines, pattern, line_index, eof=chunk.is_end_of_file)
        if found is None and pattern and pattern[-1] == "":
            found = seek_sequence(lines, pattern[:-1], line_index, eof=chunk.is_end_of_file)
            if found is not None:
                pattern = pattern[:-1]
                if new_slice and new_slice[-1] == "":
                    new_slice = new_slice[:-1]

        if found is None:
            preview = "\n".join(chunk.old_lines[:5])
            raise PatchPreflightError(
                f"Failed to find expected lines in {path_label}:\n{preview}"
            )

        replacements.append((found, len(pattern), new_slice))
        line_index = found + len(pattern)

    updated_lines = list(lines)
    for idx, old_len, new_slice in sorted(replacements, key=lambda item: item[0], reverse=True):
        updated_lines[idx : idx + old_len] = new_slice

    rendered = "\n".join(updated_lines)
    if updated_lines and (had_trailing_newline or norm_original.endswith("\n")):
        rendered += "\n"
    return restore_line_endings(rendered, eol)


def _decode_utf8_text(raw: bytes, *, path_label: str) -> str:
    if b"\x00" in raw:
        raise PatchPreflightError(f"Binary file cannot be patched: {path_label}")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatchPreflightError(f"File is not valid UTF-8 ({path_label}): {exc}") from exc


class ApplyPatchToolInput(BaseModel):
    patch: str = Field(
        description=(
            "Patch payload wrapped in '*** Begin Patch' and '*** End Patch', using "
            "'*** Add File:', '*** Delete File:', and '*** Update File:' hunks."
        )
    )


class ApplyPatchTool(BaseTool):
    """Apply multi-file Codex-format patches with full preflight and atomic per-file writes."""

    name = "apply_patch"
    description = (
        "Apply a multi-file Codex patch wrapped between '*** Begin Patch' and '*** End Patch'. "
        "Supports '*** Add File: <path>', '*** Delete File: <path>', and '*** Update File: <path>' "
        "(with optional '*** Move to: <new_path>') and '@@' context hunks. Validates all files, "
        "workspace boundaries, and stale versions in a dry-run preflight before writing any file."
    )
    input_model = ApplyPatchToolInput

    async def execute(
        self,
        arguments: ApplyPatchToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        try:
            hunks = parse_patch(arguments.patch)
        except PatchParseError as exc:
            return ToolResult(output=f"Invalid patch: {exc}", is_error=True)

        if uses_e2b_task_workspace(context):
            return await _execute_sandbox_patch(hunks, context)
        return await _execute_host_patch(hunks, context)


def _check_docker_sandbox_path(path: Path, cwd: Path) -> str | None:
    from openharness.sandbox.session import is_docker_sandbox_active

    if not is_docker_sandbox_active():
        return None
    from openharness.sandbox.path_validator import validate_sandbox_path

    allowed, reason = validate_sandbox_path(path, cwd)
    if not allowed:
        return f"Sandbox: {reason}"
    return None


async def _execute_host_patch(
    hunks: list[PatchHunk],
    context: ToolExecutionContext,
) -> ToolResult:
    workspace = Path(context.cwd).resolve()

    resolved_targets: list[tuple[PatchHunk, Path, str, Path | None, str | None]] = []
    lock_keys: set[str] = set()
    for hunk in hunks:
        path = normalize_host_path(context.cwd, hunk.path)
        key = host_observation_key(path)
        lock_keys.add(key)
        move_path: Path | None = None
        move_key: str | None = None
        if isinstance(hunk, UpdateFileHunk) and hunk.move_path is not None:
            move_path = normalize_host_path(context.cwd, hunk.move_path)
            move_key = host_observation_key(move_path)
            lock_keys.add(move_key)
        resolved_targets.append((hunk, path, key, move_path, move_key))

    async with AsyncExitStack() as stack:
        for key in sorted(lock_keys):
            await stack.enter_async_context(file_lock(key))

        try:
            planned = _preflight_host_patch(resolved_targets, workspace, context)
        except PatchPreflightError as exc:
            return ToolResult(output=str(exc), is_error=True)

        metadata_map = getattr(context, "metadata", None) or {}
        approval_prompt = metadata_map.get("edit_approval_prompt")
        if approval_prompt is not None:
            combined_diffs: list[str] = []
            total_added = 0
            total_removed = 0
            for item in planned:
                diff_text, added, removed = compute_unified_diff(
                    item.display_path,
                    item.diff_original,
                    item.diff_updated,
                )
                if diff_text:
                    combined_diffs.append(diff_text)
                total_added += added
                total_removed += removed
            reply = await approval_prompt(
                ", ".join(item.display_path for item in planned),
                "\n\n".join(combined_diffs),
                total_added,
                total_removed,
            )
            if reply == "reject":
                return ToolResult(output="Patch rejected by user.", is_error=True)
            for item in planned:
                check_target = item.remove_path or item.target_path
                if item.expected_version is not None and host_file_version(check_target) != item.expected_version:
                    return ToolResult(
                        output=(
                            f"FS_STALE_VERSION: File {check_target} changed while awaiting patch "
                            "approval; please retry."
                        ),
                        is_error=True,
                    )

        added_paths: list[str] = []
        modified_paths: list[str] = []
        deleted_paths: list[str] = []
        summary_lines: list[str] = []

        try:
            for item in planned:
                target_path: Path = item.target_path
                if item.kind == "add":
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_text(target_path, item.content or "", encoding="utf-8")
                    ver = host_file_version(target_path)
                    if ver is not None:
                        observe_file(context, item.key, ver)
                    added_paths.append(str(target_path))
                    summary_lines.append(f"A {target_path}")
                elif item.kind == "delete":
                    target_path.unlink()
                    observe_absent(context, item.key)
                    deleted_paths.append(str(target_path))
                    summary_lines.append(f"D {target_path}")
                elif item.kind == "update":
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_text(target_path, item.content or "", encoding="utf-8")
                    ver = host_file_version(target_path)
                    if ver is not None:
                        observe_file(context, item.key, ver)
                    if item.remove_path is not None and item.remove_path != target_path:
                        source_path: Path = item.remove_path
                        if source_path.exists():
                            source_path.unlink()
                        if item.remove_key is not None:
                            observe_absent(context, item.remove_key)
                        summary_lines.append(f"R {source_path} -> {target_path}")
                        modified_paths.append(str(target_path))
                        deleted_paths.append(str(source_path))
                    else:
                        summary_lines.append(f"M {target_path}")
                        modified_paths.append(str(target_path))
        except OSError as exc:
            return ToolResult(output=f"Failed while committing patch: {exc}", is_error=True)

    affected = list(dict.fromkeys([*added_paths, *modified_paths, *deleted_paths]))
    return ToolResult(
        output="Success. Updated the following files:\n" + "\n".join(summary_lines),
        metadata={
            "workspace": "host",
            "affected_paths": affected,
            "added": added_paths,
            "modified": modified_paths,
            "deleted": deleted_paths,
        },
    )


def _preflight_host_patch(
    resolved_targets: list[tuple[PatchHunk, Path, str, Path | None, str | None]],
    workspace: Path,
    context: ToolExecutionContext,
) -> list[_PlannedWrite]:
    """Validate every hunk and compute all resulting contents before any host write."""
    virtual_contents: dict[str, str | None] = {}
    checked_guards: set[str] = set()
    initial_versions: dict[str, str | None] = {}
    planned: list[_PlannedWrite] = []

    def _load_virtual(path: Path, key: str, *, allow_missing: bool, op: str) -> str | None:
        docker_err = _check_docker_sandbox_path(path, context.cwd)
        if docker_err:
            raise PatchPreflightError(docker_err)
        if path.is_symlink():
            raise PatchPreflightError(f"Refusing to patch symlink: {path}")
        if key in virtual_contents:
            return virtual_contents[key]

        val_err = validate_host_workspace_path(
            path,
            workspace,
            allow_missing=allow_missing,
            operation=op,
        )
        if val_err:
            raise PatchPreflightError(val_err)

        ver = host_file_version(path)
        initial_versions[key] = ver
        if key not in checked_guards:
            guard_err = check_mutation_guard(
                context,
                key,
                current_version=ver,
                operation="create_or_replace" if allow_missing and ver is None else (
                    "delete" if op == "delete" else "update"
                ),
                display_path=str(path),
            )
            if guard_err:
                raise PatchPreflightError(guard_err)
            checked_guards.add(key)

        if ver is None:
            virtual_contents[key] = None
            return None
        try:
            text = _decode_utf8_text(path.read_bytes(), path_label=str(path))
        except OSError as exc:
            raise PatchPreflightError(f"Failed to read {path}: {exc}") from exc
        virtual_contents[key] = text
        return text

    for hunk, path, key, move_path, move_key in resolved_targets:
        if isinstance(hunk, AddFileHunk):
            existing = _load_virtual(path, key, allow_missing=True, op="add")
            if existing is not None:
                raise PatchPreflightError(
                    f"Cannot add file that already exists (use Update File instead): {path}"
                )
            virtual_contents[key] = hunk.contents
            planned.append(
                _PlannedWrite(
                    kind="add",
                    key=key,
                    display_path=str(path),
                    target_path=path,
                    content=hunk.contents,
                    expected_version=initial_versions.get(key),
                    diff_original="",
                    diff_updated=hunk.contents,
                )
            )
            continue

        if isinstance(hunk, DeleteFileHunk):
            existing = _load_virtual(path, key, allow_missing=False, op="delete")
            if existing is None:
                raise PatchPreflightError(f"Cannot delete missing file: {path}")
            virtual_contents[key] = None
            planned.append(
                _PlannedWrite(
                    kind="delete",
                    key=key,
                    display_path=str(path),
                    target_path=path,
                    expected_version=initial_versions.get(key),
                    diff_original=existing,
                    diff_updated="",
                )
            )
            continue

        assert isinstance(hunk, UpdateFileHunk)
        existing = _load_virtual(path, key, allow_missing=False, op="update")
        if existing is None:
            raise PatchPreflightError(f"Cannot update missing file: {path}")

        updated = apply_update_chunks(existing, hunk.chunks, path_label=str(path))
        if move_path is not None and move_key is not None:
            if move_key != key:
                dest_existing = _load_virtual(move_path, move_key, allow_missing=True, op="move")
                if dest_existing is not None:
                    raise PatchPreflightError(
                        f"Cannot move {path} to existing destination {move_path}"
                    )
                virtual_contents[key] = None
                virtual_contents[move_key] = updated
                planned.append(
                    _PlannedWrite(
                        kind="update",
                        key=move_key,
                        display_path=f"{path} -> {move_path}",
                        target_path=move_path,
                        content=updated,
                        remove_path=path,
                        remove_key=key,
                        expected_version=initial_versions.get(key),
                        diff_original=existing,
                        diff_updated=updated,
                    )
                )
                continue

        virtual_contents[key] = updated
        planned.append(
            _PlannedWrite(
                kind="update",
                key=key,
                display_path=str(path),
                target_path=path,
                content=updated,
                expected_version=initial_versions.get(key),
                diff_original=existing,
                diff_updated=updated,
            )
        )

    return planned


async def _execute_sandbox_patch(
    hunks: list[PatchHunk],
    context: ToolExecutionContext,
) -> ToolResult:
    try:
        session = await get_e2b_task_session(context)
    except Exception as exc:
        return ToolResult(output=f"Sandbox workspace error: {exc}", is_error=True)

    resolved_targets: list[tuple[PatchHunk, str, str, str | None, str | None]] = []
    lock_keys: set[str] = set()
    try:
        for hunk in hunks:
            sandbox_path = to_sandbox_path(context, hunk.path, for_write=True)
            key = sandbox_observation_key(sandbox_path)
            lock_keys.add(key)
            move_sandbox_path: str | None = None
            move_key: str | None = None
            if isinstance(hunk, UpdateFileHunk) and hunk.move_path is not None:
                move_sandbox_path = to_sandbox_path(context, hunk.move_path, for_write=True)
                move_key = sandbox_observation_key(move_sandbox_path)
                lock_keys.add(move_key)
            resolved_targets.append((hunk, sandbox_path, key, move_sandbox_path, move_key))
    except Exception as exc:
        return ToolResult(output=f"Sandbox workspace error: {exc}", is_error=True)

    async with AsyncExitStack() as stack:
        for key in sorted(lock_keys):
            await stack.enter_async_context(file_lock(key))

        try:
            planned = await _preflight_sandbox_patch(session, resolved_targets, context)
        except PatchPreflightError as exc:
            return ToolResult(output=str(exc), is_error=True)
        except Exception as exc:
            return ToolResult(output=f"Sandbox patch preflight failed: {exc}", is_error=True)

        added_paths: list[str] = []
        modified_paths: list[str] = []
        deleted_paths: list[str] = []
        summary_lines: list[str] = []

        try:
            for item in planned:
                target: str = item.target_path
                if item.kind == "add":
                    await atomic_write_sandbox_text(
                        session,
                        target,
                        item.content or "",
                        create_directories=True,
                    )
                    observe_file(
                        context,
                        item.key,
                        bytes_version((item.content or "").encode("utf-8")),
                    )
                    added_paths.append(target)
                    summary_lines.append(f"A {target}")
                elif item.kind == "delete":
                    rm_proc = await session.exec_command(f"rm -f {shlex.quote(target)}")
                    communicate = getattr(rm_proc, "communicate", None)
                    if callable(communicate):
                        await communicate()
                    observe_absent(context, item.key)
                    deleted_paths.append(target)
                    summary_lines.append(f"D {target}")
                elif item.kind == "update":
                    await atomic_write_sandbox_text(
                        session,
                        target,
                        item.content or "",
                        create_directories=True,
                    )
                    observe_file(
                        context,
                        item.key,
                        bytes_version((item.content or "").encode("utf-8")),
                    )
                    if item.remove_path is not None and item.remove_path != target:
                        src: str = item.remove_path
                        rm_proc = await session.exec_command(f"rm -f {shlex.quote(src)}")
                        communicate = getattr(rm_proc, "communicate", None)
                        if callable(communicate):
                            await communicate()
                        if item.remove_key is not None:
                            observe_absent(context, item.remove_key)
                        summary_lines.append(f"R {src} -> {target}")
                        modified_paths.append(target)
                        deleted_paths.append(src)
                    else:
                        summary_lines.append(f"M {target}")
                        modified_paths.append(target)
        except Exception as exc:
            return ToolResult(output=f"Failed while committing sandbox patch: {exc}", is_error=True)

    affected = list(dict.fromkeys([*added_paths, *modified_paths, *deleted_paths]))
    return ToolResult(
        output="Success. Updated the following sandbox files:\n" + "\n".join(summary_lines),
        metadata={
            "workspace": "e2b",
            "affected_paths": affected,
            "added": added_paths,
            "modified": modified_paths,
            "deleted": deleted_paths,
        },
    )


async def _preflight_sandbox_patch(
    session: Any,
    resolved_targets: list[tuple[PatchHunk, str, str, str | None, str | None]],
    context: ToolExecutionContext,
) -> list[_PlannedWrite]:
    virtual_contents: dict[str, str | None] = {}
    checked_guards: set[str] = set()
    planned: list[_PlannedWrite] = []

    async def _load_sandbox_virtual(
        sandbox_path: str,
        key: str,
        *,
        allow_missing: bool,
        op: str,
    ) -> str | None:
        if key in virtual_contents:
            return virtual_contents[key]

        status = await sandbox_path_status(session, sandbox_path)
        if status not in ("file", "missing"):
            raise PatchPreflightError(f"Target path is not a regular sandbox file: {sandbox_path}")
        if not allow_missing and status == "missing":
            raise PatchPreflightError(f"File not found in sandbox: {sandbox_path}")

        raw_bytes: bytes | None = None
        if status == "file":
            raw_bytes = await session.read_file_binary(sandbox_path)
        ver = bytes_version(raw_bytes) if raw_bytes is not None else None

        if key not in checked_guards:
            guard_err = check_mutation_guard(
                context,
                key,
                current_version=ver,
                operation="create_or_replace" if allow_missing and ver is None else (
                    "delete" if op == "delete" else "update"
                ),
                display_path=sandbox_path,
            )
            if guard_err:
                raise PatchPreflightError(guard_err)
            checked_guards.add(key)

        if raw_bytes is None:
            virtual_contents[key] = None
            return None
        text = _decode_utf8_text(raw_bytes, path_label=sandbox_path)
        virtual_contents[key] = text
        return text

    for hunk, sandbox_path, key, move_sandbox_path, move_key in resolved_targets:
        if isinstance(hunk, AddFileHunk):
            existing = await _load_sandbox_virtual(
                sandbox_path, key, allow_missing=True, op="add"
            )
            if existing is not None:
                raise PatchPreflightError(
                    f"Cannot add sandbox file that already exists: {sandbox_path}"
                )
            virtual_contents[key] = hunk.contents
            planned.append(
                _PlannedWrite(
                    kind="add",
                    key=key,
                    display_path=sandbox_path,
                    target_path=sandbox_path,
                    content=hunk.contents,
                    diff_original="",
                    diff_updated=hunk.contents,
                )
            )
            continue

        if isinstance(hunk, DeleteFileHunk):
            existing = await _load_sandbox_virtual(
                sandbox_path, key, allow_missing=False, op="delete"
            )
            if existing is None:
                raise PatchPreflightError(f"Cannot delete missing sandbox file: {sandbox_path}")
            virtual_contents[key] = None
            planned.append(
                _PlannedWrite(
                    kind="delete",
                    key=key,
                    display_path=sandbox_path,
                    target_path=sandbox_path,
                    diff_original=existing,
                    diff_updated="",
                )
            )
            continue

        assert isinstance(hunk, UpdateFileHunk)
        existing = await _load_sandbox_virtual(
            sandbox_path, key, allow_missing=False, op="update"
        )
        if existing is None:
            raise PatchPreflightError(f"Cannot update missing sandbox file: {sandbox_path}")

        updated = apply_update_chunks(existing, hunk.chunks, path_label=sandbox_path)
        if move_sandbox_path is not None and move_key is not None and move_key != key:
            dest_existing = await _load_sandbox_virtual(
                move_sandbox_path, move_key, allow_missing=True, op="move"
            )
            if dest_existing is not None:
                raise PatchPreflightError(
                    f"Cannot move sandbox file {sandbox_path} to existing {move_sandbox_path}"
                )
            virtual_contents[key] = None
            virtual_contents[move_key] = updated
            planned.append(
                _PlannedWrite(
                    kind="update",
                    key=move_key,
                    display_path=f"{sandbox_path} -> {move_sandbox_path}",
                    target_path=move_sandbox_path,
                    content=updated,
                    remove_path=sandbox_path,
                    remove_key=key,
                    diff_original=existing,
                    diff_updated=updated,
                )
            )
            continue

        virtual_contents[key] = updated
        planned.append(
            _PlannedWrite(
                kind="update",
                key=key,
                display_path=sandbox_path,
                target_path=sandbox_path,
                content=updated,
                diff_original=existing,
                diff_updated=updated,
            )
        )

    return planned
