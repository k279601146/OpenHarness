"""String-based file editing tool."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


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
        from openharness.sandbox.session import get_sandbox_session
        session = get_sandbox_session()

        if session:
            try:
                # 确保相对路径相对于 context.cwd (/home/user) 解析
                container_path = arguments.path.replace("\\", "/")
                if not container_path.startswith("/"):
                    base_cwd = str(context.cwd).replace("\\", "/")
                    container_path = f"{base_cwd}/{container_path}".replace("//", "/")

                original = await session.read_file(container_path)
            except Exception as e:
                return ToolResult(output=f"Error reading file {arguments.path}: {e}", is_error=True)
                
            if isinstance(original, bytes):
                try:
                    original = original.decode("utf-8")
                except UnicodeDecodeError:
                    return ToolResult(output="Cannot edit binary file", is_error=True)

            if arguments.old_str not in original:
                return ToolResult(output="old_str was not found in the file", is_error=True)

            if arguments.replace_all:
                updated = original.replace(arguments.old_str, arguments.new_str)
            else:
                updated = original.replace(arguments.old_str, arguments.new_str, 1)

            try:
                await session.write_file(container_path, updated)
            except Exception as e:
                return ToolResult(output=f"Error writing file {container_path}: {e}", is_error=True)
                
            return ToolResult(output=f"Updated {container_path}")
        else:
            # MVP 安全模式：使用白名单验证
            path = _resolve_path(Path(context.cwd), arguments.path)
            from openharness.tools.safe_file_validator import validate_safe_file_operation
            
            is_safe, error_msg = validate_safe_file_operation(
                str(path), 
                str(context.cwd),
                operation="edit"
            )
            if not is_safe:
                return ToolResult(output=error_msg, is_error=True)

            if not path.exists():
                return ToolResult(output=f"File not found: {path}", is_error=True)

            original = path.read_text(encoding="utf-8")
            if arguments.old_str not in original:
                return ToolResult(output="old_str was not found in the file", is_error=True)

            if arguments.replace_all:
                updated = original.replace(arguments.old_str, arguments.new_str)
            else:
                updated = original.replace(arguments.old_str, arguments.new_str, 1)

            path.write_text(updated, encoding="utf-8")
            return ToolResult(output=f"Updated {path}")

def _resolve_path(base: Path, candidate: str) -> Path:
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()
