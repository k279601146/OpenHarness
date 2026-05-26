"""File reading tool."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.utils.paths import normalize_host_path


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
        path = _resolve_path(Path(context.cwd), arguments.path)
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
