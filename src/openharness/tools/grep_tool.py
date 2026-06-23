"""Content search tool with a pure-Python fallback."""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.sandbox_workspace import get_e2b_task_session, sandbox_grep, to_sandbox_path, uses_e2b_task_workspace
from openharness.utils.paths import normalize_host_path


class GrepToolInput(BaseModel):
    """Arguments for the grep tool."""

    pattern: str = Field(description="Regular expression to search for")
    root: str | None = Field(
        default=None,
        description="Search root directory or file. For multiple roots, call grep separately per root.",
    )
    file_glob: str = Field(default="**/*")
    case_sensitive: bool = Field(default=True)
    limit: int = Field(default=200, ge=1, le=2000)
    timeout_seconds: int = Field(default=20, ge=1, le=120)


class GrepTool(BaseTool):
    """Search host workspace text files for a regex pattern."""

    name = "grep"
    description = "Search host workspace file contents with a regular expression."
    input_model = GrepToolInput
    requires_sandbox = False

    def is_read_only(self, arguments: GrepToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: GrepToolInput, context: ToolExecutionContext) -> ToolResult:
        if uses_e2b_task_workspace(context):
            try:
                session = await get_e2b_task_session(context)
                root = to_sandbox_path(context, arguments.root)
                output = await sandbox_grep(
                    session,
                    root,
                    pattern=arguments.pattern,
                    file_glob=arguments.file_glob,
                    case_sensitive=arguments.case_sensitive,
                    limit=arguments.limit,
                )
            except Exception as exc:
                return ToolResult(output=f"Sandbox workspace error: {exc}", is_error=True)
            return ToolResult(output=output, metadata={"root": root, "workspace": "e2b"})

        root = _resolve_path(context.cwd, arguments.root) if arguments.root else context.cwd
        if not root.exists():
            return ToolResult(
                output=(
                    f"Search root does not exist: {root}\n"
                    "If you intended multiple roots, call grep separately for each root."
                ),
                is_error=True,
            )
        if root.is_file():
            display_base = _display_base(root, context.cwd)
            matches = await _rg_grep_file(
                path=root,
                pattern=arguments.pattern,
                case_sensitive=arguments.case_sensitive,
                limit=arguments.limit,
                display_base=display_base,
                timeout_seconds=arguments.timeout_seconds,
            )
            if matches is not None:
                return _format_rg_result(matches, arguments.timeout_seconds)

            return ToolResult(
                output=_python_grep_files(
                    paths=[root],
                    pattern=arguments.pattern,
                    case_sensitive=arguments.case_sensitive,
                    limit=arguments.limit,
                    display_base=display_base,
                )
            )

        matches = await _rg_grep(
            root=root,
            pattern=arguments.pattern,
            file_glob=arguments.file_glob,
            case_sensitive=arguments.case_sensitive,
            limit=arguments.limit,
            timeout_seconds=arguments.timeout_seconds,
        )
        if matches is not None:
            return _format_rg_result(matches, arguments.timeout_seconds)

        return ToolResult(
            output=_python_grep_files(
                paths=root.glob(arguments.file_glob),
                pattern=arguments.pattern,
                case_sensitive=arguments.case_sensitive,
                limit=arguments.limit,
                display_base=root,
            )
        )


def _display_base(path: Path, cwd: Path) -> Path:
    try:
        path.relative_to(cwd)
    except ValueError:
        return path.parent
    return cwd


def _python_grep_files(
    *,
    paths,
    pattern: str,
    case_sensitive: bool,
    limit: int,
    display_base: Path,
) -> str:
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        compiled = re.compile(pattern, flags)
    except re.error as exc:
        return f"(invalid regex pattern '{pattern}': {exc})"
    collected: list[str] = []

    for path in paths:
        if len(collected) >= limit:
            break
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if compiled.search(line):
                collected.append(f"{_format_path(path, display_base)}:{line_no}:{line}")
                if len(collected) >= limit:
                    break

    if not collected:
        return "(no matches)"
    return "\n".join(collected)


def _resolve_path(base: Path, candidate: str | None) -> Path:
    return normalize_host_path(base, candidate or ".")


def _format_rg_result(matches: list[str], timeout_seconds: int) -> ToolResult:
    timed_out = bool(matches and matches[-1] == _timeout_marker(timeout_seconds))
    rendered = matches[:-1] if timed_out else matches
    output = "\n".join(rendered) if rendered else "(no matches)"
    if timed_out:
        output = (
            f"{output}\n\n[grep timed out after {timeout_seconds} seconds]"
            if output != "(no matches)"
            else f"[grep timed out after {timeout_seconds} seconds]"
        )
    return ToolResult(output=output, is_error=timed_out)


async def _rg_grep(
    *,
    root: Path,
    pattern: str,
    file_glob: str,
    case_sensitive: bool,
    limit: int,
    timeout_seconds: int,
) -> list[str] | None:
    rg = shutil.which("rg")
    if not rg:
        return None

    include_hidden = (root / ".git").exists() or (root / ".gitignore").exists()
    cmd: list[str] = [
        rg,
        "--no-heading",
        "--line-number",
        "--color",
        "never",
    ]
    if include_hidden:
        cmd.append("--hidden")
    if not case_sensitive:
        cmd.append("-i")
    if file_glob:
        cmd.extend(["--glob", file_glob])
    cmd.extend(["--", pattern, "."])

    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        limit=8 * 1024 * 1024,
    )

    matches: list[str] = []
    try:
        await asyncio.wait_for(
            _collect_rg_matches(process, matches, limit=limit),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        matches.append(_timeout_marker(timeout_seconds))
        await _terminate_process(process)
    except asyncio.CancelledError:
        await _terminate_process(process)
        raise
    finally:
        if len(matches) >= limit and process.returncode is None:
            await _terminate_process(process)
        elif process.returncode is None:
            await process.wait()

    if process.returncode in {0, 1, -15, -9}:
        return matches
    return None


async def _rg_grep_file(
    *,
    path: Path,
    pattern: str,
    case_sensitive: bool,
    limit: int,
    display_base: Path,
    timeout_seconds: int,
) -> list[str] | None:
    rg = shutil.which("rg")
    if not rg:
        return None

    cmd: list[str] = [
        rg,
        "--no-heading",
        "--line-number",
        "--color",
        "never",
    ]
    if not case_sensitive:
        cmd.append("-i")
    cmd.extend(["--", pattern, path.name])

    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(path.parent),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        limit=8 * 1024 * 1024,
    )

    matches: list[str] = []
    try:
        await asyncio.wait_for(
            _collect_rg_file_matches(
                process,
                matches,
                limit=limit,
                path=path,
                display_base=display_base,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        matches.append(_timeout_marker(timeout_seconds))
        await _terminate_process(process)
    except asyncio.CancelledError:
        await _terminate_process(process)
        raise
    finally:
        if len(matches) >= limit and process.returncode is None:
            await _terminate_process(process)
        elif process.returncode is None:
            await process.wait()

    if process.returncode in {0, 1, -15, -9}:
        return matches
    return None


def _timeout_marker(timeout_seconds: int) -> str:
    return f"__OPENHARNESS_GREP_TIMEOUT__:{timeout_seconds}"


async def _collect_rg_matches(
    process: asyncio.subprocess.Process,
    matches: list[str],
    *,
    limit: int,
) -> None:
    assert process.stdout is not None
    while len(matches) < limit:
        try:
            raw = await process.stdout.readline()
        except ValueError:
            continue
        if not raw:
            break
        line = raw.decode("utf-8", errors="replace").rstrip("\n")
        if line:
            matches.append(line)


async def _collect_rg_file_matches(
    process: asyncio.subprocess.Process,
    matches: list[str],
    *,
    limit: int,
    path: Path,
    display_base: Path,
) -> None:
    assert process.stdout is not None
    while len(matches) < limit:
        try:
            raw = await process.stdout.readline()
        except ValueError:
            continue
        if not raw:
            break
        line = raw.decode("utf-8", errors="replace").rstrip("\n")
        if not line:
            continue
        matches.append(f"{_format_path(path, display_base)}:{line}")


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


def _format_path(path: Path, display_base: Path) -> str:
    try:
        return str(path.relative_to(display_base))
    except ValueError:
        return str(path)
