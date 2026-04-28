"""File reading tool."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class FileReadToolInput(BaseModel):
    """Arguments for the file read tool."""

    path: str = Field(description="Path of the file to read")
    offset: int = Field(default=0, ge=0, description="Zero-based starting line")
    limit: int = Field(default=200, ge=1, le=2000, description="Number of lines to return")


class FileReadTool(BaseTool):
    """Read a UTF-8 text file with line numbers."""

    name = "read_file"
    description = "Read a text file from the local repository."
    input_model = FileReadToolInput

    def is_read_only(self, arguments: FileReadToolInput) -> bool:
        del arguments
        return True

    async def execute(
        self,
        arguments: FileReadToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        from openharness.sandbox.session import get_docker_sandbox
        session = get_docker_sandbox()

        if session:
            # 路径重定向：将容器路径映射回宿主机实际物理路径
            path = session.map_to_host_path(arguments.path)
            
            from openharness.sandbox.path_validator import validate_sandbox_path
            
            # 在沙箱模式下，允许访问 workspace, user-home 和 local-bin
            extra_allowed = [session.host_workspace, session.host_home, session.host_bin]
            allowed, reason = validate_sandbox_path(path, Path(session.host_workspace), extra_allowed=extra_allowed)
            
            if not allowed:
                return ToolResult(output=f"Sandbox: {reason}", is_error=True)
        else:
            # MVP 安全模式：使用白名单验证
            from openharness.tools.safe_file_validator import validate_safe_file_operation
            
            is_safe, error_msg = validate_safe_file_operation(
                str(path), 
                str(context.cwd),
                operation="read"
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
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()
