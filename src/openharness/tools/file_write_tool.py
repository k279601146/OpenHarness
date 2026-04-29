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
        from openharness.sandbox.session import get_sandbox_session
        session = get_sandbox_session()

        if session:
            try:
                # E2B 沙箱模式：直接使用 sandbox.files API 写文件
                # 确保相对路径相对于 context.cwd (/home/user) 解析
                container_path = arguments.path.replace("\\", "/")
                if not container_path.startswith("/"):
                    # 使用 Posix 风格拼接
                    base_cwd = str(context.cwd).replace("\\", "/")
                    container_path = f"{base_cwd}/{container_path}".replace("//", "/")

                if arguments.create_directories:
                    container_dir = str(Path(container_path).parent).replace("\\", "/")
                    await session.exec_command(["mkdir", "-p", container_dir])
                    
                await session.write_file(container_path, arguments.content)
                return ToolResult(output=f"Wrote {container_path}")
            except Exception as e:
                return ToolResult(output=f"Sandbox file write error: {e}", is_error=True)
        else:
            # MVP 安全模式：使用白名单验证
            path = _resolve_path(Path(context.cwd), arguments.path)
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
