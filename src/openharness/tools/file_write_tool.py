"""File writing tool."""

from __future__ import annotations

import difflib
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.sandbox_workspace import get_e2b_task_session, to_sandbox_path, uses_e2b_task_workspace


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
        from openharness.tools.file_state import (
            atomic_write_sandbox_text,
            bytes_version,
            check_mutation_guard,
            file_lock,
            host_file_version,
            host_observation_key,
            observe_file,
            sandbox_observation_key,
            validate_host_workspace_path,
        )
        from openharness.utils.fs import atomic_write_text

        if uses_e2b_task_workspace(context):
            try:
                session = await get_e2b_task_session(context)
                sandbox_path = to_sandbox_path(context, arguments.path, for_write=True)
                obs_key = sandbox_observation_key(sandbox_path)
                async with file_lock(obs_key):
                    existing_version: str | None = None
                    try:
                        existing_bytes = await session.read_file_binary(sandbox_path)
                        existing_version = bytes_version(existing_bytes)
                    except Exception:
                        existing_version = None

                    guard_error = check_mutation_guard(
                        context,
                        obs_key,
                        current_version=existing_version,
                        operation="create_or_replace",
                        display_path=sandbox_path,
                    )
                    if guard_error is not None:
                        return ToolResult(output=guard_error, is_error=True)

                    await atomic_write_sandbox_text(
                        session,
                        sandbox_path,
                        arguments.content,
                        create_directories=arguments.create_directories,
                    )
                    observe_file(context, obs_key, bytes_version(arguments.content.encode("utf-8")))
                return ToolResult(
                    output=f"Wrote sandbox file: {sandbox_path}",
                    metadata={
                        "path": sandbox_path,
                        "workspace": "e2b",
                        "operation": "update" if existing_version is not None else "create",
                    },
                )
            except Exception as exc:
                return ToolResult(output=f"Sandbox workspace error: {exc}", is_error=True)

        path = _resolve_path(context.cwd, arguments.path)

        from openharness.sandbox.session import is_docker_sandbox_active

        if is_docker_sandbox_active():
            from openharness.sandbox.path_validator import validate_sandbox_path

            allowed, reason = validate_sandbox_path(path, context.cwd)
            if not allowed:
                return ToolResult(output=f"Sandbox: {reason}", is_error=True)

        validation_error = validate_host_workspace_path(
            path,
            context.cwd,
            allow_missing=True,
            operation="write",
        )
        if validation_error is not None:
            return ToolResult(output=validation_error, is_error=True)

        obs_key = host_observation_key(path)
        async with file_lock(obs_key):
            current_version = host_file_version(path)
            guard_error = check_mutation_guard(
                context,
                obs_key,
                current_version=current_version,
                operation="create_or_replace",
                display_path=str(path),
            )
            if guard_error is not None:
                return ToolResult(output=guard_error, is_error=True)

            if not arguments.create_directories and not path.parent.exists():
                return ToolResult(output=f"Parent directory does not exist: {path.parent}", is_error=True)

            metadata = getattr(context, "metadata", None) or {}
            approval_prompt = metadata.get("edit_approval_prompt")
            stats = ""
            if approval_prompt is not None:
                original = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
                diff_text, added, removed = _compute_diff(str(path), original, arguments.content)
                reply = await approval_prompt(str(path), diff_text, added, removed)
                if reply == "reject":
                    return ToolResult(output=f"Write rejected by user: {path}", is_error=True)
                if host_file_version(path) != current_version:
                    return ToolResult(
                        output=f"FS_STALE_VERSION: File {path} changed while awaiting write approval.",
                        is_error=True,
                    )
                stats = f"  ({_ANSI_GREEN}+{added}{_ANSI_RESET} {_ANSI_RED}-{removed}{_ANSI_RESET})"

            if arguments.create_directories:
                path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, arguments.content, encoding="utf-8")
            new_version = host_file_version(path)
            if new_version is not None:
                observe_file(context, obs_key, new_version)
            return ToolResult(
                output=f"Wrote {path}{stats}",
                metadata={
                    "path": str(path),
                    "workspace": "host",
                    "operation": "update" if current_version is not None else "create",
                },
            )


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


def _shell_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)
