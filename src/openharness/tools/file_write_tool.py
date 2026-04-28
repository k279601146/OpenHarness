"""File writing tool."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class FileWriteToolInput(BaseModel):
    """Arguments for the file write tool."""

    path: str = Field(description="Path of the file to write")
    content: str = Field(description="Full file contents")
    create_directories: bool = Field(default=True)


class FileWriteTool(BaseTool):
    """Write complete file contents."""

    name = "write_file"
    description = "Create or overwrite a text file in the local repository."
    input_model = FileWriteToolInput

    async def execute(
        self,
        arguments: FileWriteToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        from openharness.sandbox.session import get_docker_sandbox
        session = get_docker_sandbox()

        if session:
            # 路径重定向：将容器路径映射回宿主机实际物理路径
            path = session.map_to_host_path(arguments.path)
            
            from openharness.sandbox.path_validator import validate_sandbox_path
            
            # 在沙箱模式下，允许写入 workspace 和 user-home (bin 通常是只读的，除非特殊操作)
            extra_allowed = [session.host_workspace, session.host_home]
            allowed, reason = validate_sandbox_path(path, Path(session.host_workspace), extra_allowed=extra_allowed)
            
            if not allowed:
                return ToolResult(output=f"Sandbox: {reason}", is_error=True)
        else:
            # MVP 安全模式：使用白名单验证
            from openharness.tools.safe_file_validator import validate_safe_file_operation
            
            is_safe, error_msg = validate_safe_file_operation(
                str(path), 
                str(context.cwd),
                operation="write"
            )
            if not is_safe:
                return ToolResult(output=error_msg, is_error=True)

        if arguments.create_directories:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(arguments.content, encoding="utf-8")
        return ToolResult(output=f"Wrote {path}")


def _resolve_path(base: Path, candidate: str) -> Path:
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()
