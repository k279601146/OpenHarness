"""Shell command execution tool."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from openharness.sandbox import SandboxUnavailableError
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.utils.shell import create_shell_subprocess


_READ_REMAINING_OUTPUT_TIMEOUT_SECONDS = 2.0


class BashToolInput(BaseModel):
    """Arguments for the bash tool."""

    command: str = Field(description="Shell command to execute")
    cwd: str | None = Field(default=None, description="Working directory override")
    timeout_seconds: int = Field(default=600, ge=1, le=600)


class BashTool(BaseTool):
    """Execute a shell command with stdout/stderr capture."""

    name = "bash"
    description = (
        "Run a shell command only when file/search tools cannot complete the task "
        "or command execution is explicitly required."
    )
    input_model = BashToolInput
    requires_sandbox = True

    async def execute(self, arguments: BashToolInput, context: ToolExecutionContext) -> ToolResult:
        cwd = context.cwd
        if _uses_e2b_sandbox(context):
            cwd = _normalize_e2b_cwd(arguments.cwd, host_cwd=context.cwd)
        elif arguments.cwd:
            cwd = Path(arguments.cwd).expanduser()
            if not cwd.is_absolute():
                cwd = context.cwd / cwd
        preflight_error = _preflight_interactive_command(arguments.command)
        if preflight_error is not None:
            return ToolResult(
                output=preflight_error,
                is_error=True,
                metadata={"interactive_required": True},
            )
        process: asyncio.subprocess.Process | None = None
        try:
            process = await create_shell_subprocess(
                arguments.command,
                cwd=cwd,
                settings=context.metadata.get("settings"),
                prefer_pty=True,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                user_id=context.metadata.get("user_id"),
                thread_id=context.metadata.get("thread_id"),
                db_session=context.metadata.get("db_session"),
                env=_build_forwarded_sandbox_env(context) if _uses_e2b_sandbox(context) else None,
            )
        except SandboxUnavailableError as exc:
            return ToolResult(output=str(exc), is_error=True)
        except asyncio.CancelledError:
            if process is not None:
                await _terminate_process(process, force=False)
            raise

        try:
            await asyncio.wait_for(process.wait(), timeout=arguments.timeout_seconds)
        except asyncio.TimeoutError:
            output_buffer = await _drain_available_output(process.stdout)
            await _terminate_process(process, force=True)
            output_buffer.extend(await _read_remaining_output(process))
            return ToolResult(
                output=_format_timeout_output(
                    output_buffer,
                    command=arguments.command,
                    timeout_seconds=arguments.timeout_seconds,
                ),
                is_error=True,
                metadata={"returncode": process.returncode, "timed_out": True},
            )
        except asyncio.CancelledError:
            await _terminate_process(process, force=False)
            raise

        output_buffer = await _read_remaining_output(process)
        text = _format_output(output_buffer)
        return ToolResult(
            output=text,
            is_error=process.returncode != 0,
            metadata={"returncode": process.returncode},
        )


def _uses_e2b_sandbox(context: ToolExecutionContext) -> bool:
    settings = context.metadata.get("settings")
    sandbox = getattr(settings, "sandbox", None)
    return bool(
        getattr(sandbox, "enabled", False)
        and getattr(sandbox, "backend", None) == "e2b"
    )


def _build_forwarded_sandbox_env(context: ToolExecutionContext) -> dict[str, str] | None:
    """Forward only approved host/project env vars needed by sandbox commands."""
    project_env = _load_nearest_dotenv(context.cwd)
    forwarded: dict[str, str] = {}

    for key in (
        "GPT_IMAGEGEN_API_KEY",
        "GPT_IMAGEGEN_BASE_URL",
        "NANO_BANANA_API_KEY",
        "NANO_BANANA_BASE_URL",
        "DOUBAO_IMAGE_API_KEY",
        "DOUBAO_IMAGE_BASE_URL",
        "KOLORS_IMAGE_API_KEY",
        "KOLORS_IMAGE_BASE_URL",
        "IMAGE_GEN_API_KEY",
        "IMAGE_GEN_BASE_URL",
        "SEEDANCE_VIDEO_API_KEY",
        "SEEDANCE_VIDEO_BASE_URL",
        "VEO_VIDEO_API_KEY",
        "VEO_VIDEO_BASE_URL",
        "KLING_VIDEO_API_KEY",
        "KLING_VIDEO_BASE_URL",
        "VIDEO_GEN_API_KEY",
        "VIDEO_GEN_BASE_URL",
        "BILLING_CREDITS_PER_USD",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "https_proxy",
        "http_proxy",
        "no_proxy",
    ):
        value = os.getenv(key) or project_env.get(key)
        if value:
            forwarded[key] = value

    if "GPT_IMAGEGEN_API_KEY" not in forwarded:
        value = os.getenv("IMAGE_GEN_API_KEY") or project_env.get("IMAGE_GEN_API_KEY")
        if value:
            forwarded["GPT_IMAGEGEN_API_KEY"] = value
    if "GPT_IMAGEGEN_BASE_URL" not in forwarded:
        value = os.getenv("IMAGE_GEN_BASE_URL") or project_env.get("IMAGE_GEN_BASE_URL")
        if value:
            forwarded["GPT_IMAGEGEN_BASE_URL"] = value

    return forwarded or None


def _load_nearest_dotenv(cwd: Path) -> dict[str, str]:
    try:
        start = Path(cwd).expanduser().resolve()
    except OSError:
        start = Path.cwd()
    if start.is_file():
        start = start.parent

    for directory in (start, *start.parents):
        env_path = directory / ".env"
        if not env_path.is_file():
            continue
        try:
            from dotenv import dotenv_values

            values = dotenv_values(env_path)
            return {str(k): str(v) for k, v in values.items() if k and v is not None}
        except Exception:
            return _parse_simple_dotenv(env_path)
    return {}


def _parse_simple_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return values

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def _normalize_e2b_cwd(raw_cwd: str | None, *, host_cwd: Path) -> str:
    if raw_cwd is None or not str(raw_cwd).strip():
        return "/home/user"

    raw = str(raw_cwd).strip()
    normalized = raw.replace("\\", "/")
    if normalized in {".", "~"}:
        return "/home/user"
    if normalized == "/home/user" or normalized.startswith("/home/user/"):
        return normalized.rstrip("/") or "/home/user"
    if normalized.startswith("/") and ":" not in normalized:
        return normalized.rstrip("/") or "/home/user"

    try:
        raw_path = Path(raw).expanduser().resolve()
        host_path = Path(host_cwd).expanduser().resolve()
        rel = raw_path.relative_to(host_path)
    except (OSError, ValueError):
        if len(normalized) >= 2 and normalized[1] == ":":
            return "/home/user"
        rel = Path(normalized)

    rel_text = rel.as_posix().strip("/")
    if not rel_text or rel_text == ".":
        return "/home/user"
    return f"/home/user/{rel_text}"


async def _terminate_process(process: asyncio.subprocess.Process, *, force: bool) -> None:
    if process.returncode is not None:
        return
    if force:
        process.kill()
        await process.wait()
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


async def _read_remaining_output(process: asyncio.subprocess.Process) -> bytearray:
    output_buffer = bytearray()
    if process.stdout is not None:
        try:
            remaining = await asyncio.wait_for(
                process.stdout.read(),
                timeout=_READ_REMAINING_OUTPUT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            remaining = b""
        output_buffer.extend(remaining)
    return output_buffer


async def _drain_available_output(
    stream: asyncio.StreamReader | None,
    *,
    read_timeout: float = 0.05,
) -> bytearray:
    output_buffer = bytearray()
    if stream is None:
        return output_buffer
    while True:
        try:
            chunk = await asyncio.wait_for(stream.read(65536), timeout=read_timeout)
        except asyncio.TimeoutError:
            return output_buffer
        if not chunk:
            return output_buffer
        output_buffer.extend(chunk)


def _format_output(output_buffer: bytearray) -> str:
    text = output_buffer.decode("utf-8", errors="replace").replace("\r\n", "\n").strip()
    if not text:
        return "(no output)"
    if len(text) > 12000:
        return f"{text[:12000]}\n...[truncated]..."
    return text


def _format_timeout_output(output_buffer: bytearray, *, command: str, timeout_seconds: int) -> str:
    parts = [f"Command timed out after {timeout_seconds} seconds."]
    text = _format_output(output_buffer)
    if text != "(no output)":
        parts.extend(["", "Partial output:", text])
    hint = _interactive_command_hint(command=command, output=text)
    if hint:
        parts.extend(["", hint])
    return "\n".join(parts)


def _preflight_interactive_command(command: str) -> str | None:
    lowered_command = command.lower()
    if not _looks_like_interactive_scaffold(lowered_command):
        return None
    return (
        "This command appears to require interactive input before it can continue. "
        "The bash tool is non-interactive, so it cannot answer installer/scaffold prompts live. "
        "Prefer non-interactive flags (for example --yes, -y, --skip-install, --defaults, --non-interactive), "
        "or run the scaffolding step once in an external terminal before asking the agent to continue."
    )


def _interactive_command_hint(*, command: str, output: str) -> str | None:
    lowered_command = command.lower()
    if _looks_like_interactive_scaffold(lowered_command) or _looks_like_prompt(output):
        return (
            "This command appears to require interactive input. "
            "The bash tool is non-interactive, so prefer non-interactive flags "
            "(for example --yes, -y, --skip-install, or similar) or run the "
            "scaffolding step once in an external terminal before continuing."
        )
    return None


def _looks_like_interactive_scaffold(lowered_command: str) -> bool:
    scaffold_markers: tuple[str, ...] = (
        "create-next-app",
        "npm create ",
        "pnpm create ",
        "yarn create ",
        "bun create ",
        "pnpm dlx ",
        "npm init ",
        "pnpm init ",
        "yarn init ",
        "bunx create-",
        "npx create-",
    )
    non_interactive_markers: tuple[str, ...] = (
        "--yes",
        " -y",
        "--skip-install",
        "--defaults",
        "--non-interactive",
        "--ci",
    )
    return any(marker in lowered_command for marker in scaffold_markers) and not any(
        marker in lowered_command for marker in non_interactive_markers
    )


def _looks_like_prompt(output: str) -> bool:
    if not output:
        return False
    prompt_markers: Iterable[str] = (
        "would you like",
        "ok to proceed",
        "select an option",
        "which",
        "press enter to continue",
        "?",
    )
    lowered_output = output.lower()
    return any(marker in lowered_output for marker in prompt_markers)
