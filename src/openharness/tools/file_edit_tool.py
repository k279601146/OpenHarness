"""String-based file editing tool."""

from __future__ import annotations

import difflib
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.sandbox_workspace import get_e2b_task_session, sandbox_path_status, to_sandbox_path, uses_e2b_task_workspace


class FileEditToolInput(BaseModel):
    """Arguments for the file edit tool."""

    path: str = Field(description="Path of the file to edit")
    old_str: str = Field(description="Existing text to replace")
    new_str: str = Field(description="Replacement text")
    replace_all: bool = Field(default=False)


class FileEditTool(BaseTool):
    """Replace text in an existing file."""

    name = "edit_file"
    description = "Edit an existing file by replacing a string."
    input_model = FileEditToolInput

    async def execute(
        self,
        arguments: FileEditToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        if uses_e2b_task_workspace(context):
            return await _edit_sandbox_file(arguments, context)

        path = _resolve_path(context.cwd, arguments.path)

        from openharness.sandbox.session import is_docker_sandbox_active

        if is_docker_sandbox_active():
            from openharness.sandbox.path_validator import validate_sandbox_path

            allowed, reason = validate_sandbox_path(path, context.cwd)
            if not allowed:
                return ToolResult(output=f"Sandbox: {reason}", is_error=True)

        if not path.exists():
            return ToolResult(output=f"File not found: {path}", is_error=True)

        original = path.read_text(encoding="utf-8")
        if arguments.old_str not in original:
            return ToolResult(output="old_str was not found in the file", is_error=True)

        if arguments.replace_all:
            updated = original.replace(arguments.old_str, arguments.new_str)
        else:
            updated = original.replace(arguments.old_str, arguments.new_str, 1)

        approval_prompt = context.metadata.get("edit_approval_prompt") if context.metadata else None
        if approval_prompt is not None:
            diff_text, added, removed = _compute_diff(str(path), original, updated)
            reply = await approval_prompt(str(path), diff_text, added, removed)
            if reply == "reject":
                return ToolResult(output=f"Edit rejected by user: {path}", is_error=True)
            path.write_text(updated, encoding="utf-8")
            stats = f"  ({_ANSI_GREEN}+{added}{_ANSI_RESET} {_ANSI_RED}-{removed}{_ANSI_RESET})"
            return ToolResult(output=f"Updated {path}{stats}")

        path.write_text(updated, encoding="utf-8")
        return ToolResult(output=f"Updated {path}")


def _resolve_path(base: Path, candidate: str) -> Path:
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


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


async def _edit_sandbox_file(arguments: FileEditToolInput, context: ToolExecutionContext) -> ToolResult:
    try:
        session = await get_e2b_task_session(context)
        sandbox_path = to_sandbox_path(context, arguments.path, for_write=True)
    except Exception as exc:
        return ToolResult(output=f"Sandbox workspace error: {exc}", is_error=True)

    status = await sandbox_path_status(session, sandbox_path)
    if status == "missing":
        return ToolResult(output=f"File not found in sandbox: {sandbox_path}", is_error=True)
    if status != "file":
        return ToolResult(output=f"Cannot edit non-file sandbox path: {sandbox_path}", is_error=True)

    try:
        raw = await session.read_file_binary(sandbox_path)
    except Exception as exc:
        return ToolResult(output=f"Failed to read sandbox file {sandbox_path}: {exc}", is_error=True)
    data = bytes(raw) if isinstance(raw, (bytearray, memoryview)) else raw
    original = data if isinstance(data, str) else data.decode("utf-8", errors="replace")
    if arguments.old_str not in original:
        return ToolResult(output="old_str was not found in the sandbox file", is_error=True)

    updated = (
        original.replace(arguments.old_str, arguments.new_str)
        if arguments.replace_all
        else original.replace(arguments.old_str, arguments.new_str, 1)
    )
    await session.write_file(sandbox_path, updated)
    return ToolResult(output=f"Updated sandbox file: {sandbox_path}", metadata={"path": sandbox_path, "workspace": "e2b"})
