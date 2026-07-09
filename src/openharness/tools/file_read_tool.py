"""File reading tool."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.artifact_reference_guard import artifact_lookup_guard_result
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.sandbox_workspace import (
    get_e2b_task_session,
    sandbox_file_size,
    sandbox_path_status,
    to_sandbox_path,
    uses_e2b_task_workspace,
)
from openharness.utils.paths import normalize_host_path

BINARY_READABLE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif",
    ".mp4", ".webm", ".mov", ".mp3", ".wav", ".m4a",
    ".pdf", ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls", ".zip",
}


class FileReadToolInput(BaseModel):
    """Arguments for the file read tool."""

    path: str = Field(description="Path of the file to read")
    offset: int = Field(default=0, ge=0, description="Zero-based starting line")
    limit: int = Field(default=200, ge=1, le=2000, description="Number of lines to return")


class FileReadTool(BaseTool):
    """Read a UTF-8 text file with line numbers from the host workspace."""

    name = "read_file"
    description = "Read a text file from the host workspace."
    input_model = FileReadToolInput
    requires_sandbox = False

    def is_read_only(self, arguments: FileReadToolInput) -> bool:
        del arguments
        return True

    async def execute(
        self,
        arguments: FileReadToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        guard_result = artifact_lookup_guard_result(context, arguments.path)
        if guard_result is not None:
            return guard_result
        if uses_e2b_task_workspace(context):
            return await _read_sandbox_file(arguments, context)

        path = _resolve_path(Path(context.cwd), arguments.path)
        if path.suffix.lower() in BINARY_READABLE_EXTENSIONS:
            allowed, error_msg = _validate_readable_binary_path(path, Path(context.cwd))
            if not allowed:
                return ToolResult(output=error_msg, is_error=True)
            if not path.exists():
                return ToolResult(output=f"File not found: {path}", is_error=True)
            if path.is_dir():
                return ToolResult(output=f"Cannot read directory: {path}", is_error=True)
            size = path.stat().st_size
            return ToolResult(
                output=(
                    f"Binary file is readable: {path}\n"
                    f"Type: {path.suffix.lower() or 'unknown'}\n"
                    f"Size: {size} bytes\n"
                    "Use a media-aware tool or pass this path as an attachment/reference; "
                    "read_file only returns text contents."
                ),
                metadata={"path": str(path), "size_bytes": size, "binary": True},
            )
        from openharness.tools.safe_file_validator import validate_safe_file_operation

        is_safe, error_msg = validate_safe_file_operation(
            str(path),
            str(context.cwd),
            operation="read",
        )
        if not is_safe:
            return ToolResult(output=error_msg, is_error=True)

        if not path.exists():
            return ToolResult(output=f"File not found: {path}", is_error=True)
        if path.is_dir():
            return ToolResult(output=f"Cannot read directory: {path}", is_error=True)

        raw = path.read_bytes()
        if b"\x00" in raw:
            return ToolResult(output=f"Binary file cannot be read as text: {path}", is_error=True)

        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        selected = lines[arguments.offset : arguments.offset + arguments.limit]
        numbered = [
            f"{arguments.offset + index + 1:>6}\t{line}"
            for index, line in enumerate(selected)
        ]
        if not numbered:
            return ToolResult(output=f"(no content in selected range for {path})")
        return ToolResult(output="\n".join(numbered))


def _resolve_path(base: Path, candidate: str) -> Path:
    return normalize_host_path(base, candidate)


def _validate_readable_binary_path(path: Path, cwd: Path) -> tuple[bool, str]:
    try:
        resolved = path.resolve()
        workspace = cwd.resolve()
        resolved.relative_to(workspace)
    except ValueError:
        return False, f"Security restriction: cannot read files outside the workspace: {path}"
    except Exception as exc:
        return False, f"Path validation failed: {exc}"
    dangerous = {".ssh", ".env", ".git", "credentials", "secrets", ".aws", ".azure", ".gcp", "private"}
    if set(resolved.parts) & dangerous:
        return False, f"Security restriction: cannot access sensitive path: {path}"
    return True, ""


async def _read_sandbox_file(arguments: FileReadToolInput, context: ToolExecutionContext) -> ToolResult:
    try:
        session = await get_e2b_task_session(context)
        sandbox_path = to_sandbox_path(context, arguments.path)
    except Exception as exc:
        return ToolResult(output=f"Sandbox workspace error: {exc}", is_error=True)

    status = await sandbox_path_status(session, sandbox_path)
    if status == "missing":
        return ToolResult(output=f"File not found in sandbox: {sandbox_path}", is_error=True)
    if status == "dir":
        return ToolResult(output=f"Cannot read sandbox directory: {sandbox_path}", is_error=True)
    if status != "file":
        return ToolResult(output=f"Cannot read non-file sandbox path: {sandbox_path}", is_error=True)

    suffix = Path(sandbox_path).suffix.lower()
    if suffix in BINARY_READABLE_EXTENSIONS:
        size = await sandbox_file_size(session, sandbox_path)
        return ToolResult(
            output=(
                f"Binary file is readable in sandbox: {sandbox_path}\n"
                f"Type: {suffix or 'unknown'}\n"
                f"Size: {size} bytes\n"
                "Use deliver_artifact for user-needed files; read_file only returns text contents."
            ),
            metadata={"path": sandbox_path, "size_bytes": size, "binary": True, "workspace": "e2b"},
        )

    try:
        raw = await session.read_file_binary(sandbox_path)
    except Exception as exc:
        return ToolResult(output=f"Failed to read sandbox file {sandbox_path}: {exc}", is_error=True)
    data = bytes(raw) if isinstance(raw, (bytearray, memoryview)) else raw
    if isinstance(data, str):
        text = data
    else:
        if b"\x00" in data:
            return ToolResult(output=f"Binary file cannot be read as text in sandbox: {sandbox_path}", is_error=True)
        text = data.decode("utf-8", errors="replace")

    lines = text.splitlines()
    selected = lines[arguments.offset : arguments.offset + arguments.limit]
    numbered = [
        f"{arguments.offset + index + 1:>6}\t{line}"
        for index, line in enumerate(selected)
    ]
    if not numbered:
        return ToolResult(output=f"(no content in selected range for {sandbox_path})")
    return ToolResult(output="\n".join(numbered), metadata={"path": sandbox_path, "workspace": "e2b"})
