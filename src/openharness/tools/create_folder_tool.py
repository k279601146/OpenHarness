"""Controlled host-side directory creation tool."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.safe_file_validator import DANGEROUS_PATHS
from openharness.tools.sandbox_workspace import get_e2b_task_session, to_sandbox_path, uses_e2b_task_workspace


class CreateFolderToolInput(BaseModel):
    """Arguments for creating a folder in the host workspace."""

    path: str = Field(description="Directory path to create")
    parents: bool = Field(default=True, description="Create missing parent directories")
    exist_ok: bool = Field(default=True, description="Do not fail if the directory already exists")


class CreateFolderTool(BaseTool):
    """Create a directory without invoking a shell or sandbox."""

    name = "create_folder"
    description = "Create a folder in the host workspace using controlled filesystem APIs."
    input_model = CreateFolderToolInput
    requires_sandbox = False

    async def execute(
        self,
        arguments: CreateFolderToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        if uses_e2b_task_workspace(context):
            try:
                session = await get_e2b_task_session(context)
                sandbox_path = to_sandbox_path(context, arguments.path, for_write=True)
                flags = "-p " if arguments.parents else ""
                command = f"mkdir {flags}{_shell_quote(sandbox_path)}"
                if arguments.exist_ok and not arguments.parents:
                    command += " 2>/dev/null || test -d " + _shell_quote(sandbox_path)
                process = await session.exec_command(command)
                await process.wait()
                if process.returncode != 0:
                    _stdout, stderr = await process.communicate()
                    return ToolResult(
                        output=f"Failed to create sandbox directory {sandbox_path}: {stderr.decode('utf-8', errors='replace')}",
                        is_error=True,
                    )
                return ToolResult(output=f"Created sandbox directory: {sandbox_path}", metadata={"path": sandbox_path, "workspace": "e2b"})
            except Exception as exc:
                return ToolResult(output=f"Sandbox workspace error: {exc}", is_error=True)

        path = _resolve_path(context.cwd, arguments.path)
        is_safe, error_msg = _validate_safe_directory(path, context.cwd)
        if not is_safe:
            return ToolResult(output=error_msg, is_error=True)

        if path.exists() and not path.is_dir():
            return ToolResult(output=f"Path exists and is not a directory: {path}", is_error=True)

        try:
            path.mkdir(parents=arguments.parents, exist_ok=arguments.exist_ok)
        except FileExistsError:
            return ToolResult(output=f"Directory already exists: {path}", is_error=True)
        except OSError as exc:
            return ToolResult(output=f"Failed to create directory {path}: {exc}", is_error=True)

        return ToolResult(output=f"Created directory: {path}")


def _resolve_path(base: Path, candidate: str) -> Path:
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _validate_safe_directory(path: Path, workspace: Path) -> tuple[bool, str]:
    resolved = path.resolve()
    workspace = Path(workspace).resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError:
        return False, (
            "Security restriction: cannot create folders outside the workspace.\n"
            f"Workspace: {workspace}\n"
            f"Requested: {resolved}"
        )

    dangerous_found = set(resolved.parts) & DANGEROUS_PATHS
    if dangerous_found:
        return False, (
            "Security restriction: cannot create folders inside sensitive directories.\n"
            f"Detected: {', '.join(sorted(dangerous_found))}"
        )

    return True, ""


def _shell_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)
