"""Filesystem globbing tool."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class GlobToolInput(BaseModel):
    """Arguments for the glob tool."""

    pattern: str = Field(description="Glob pattern relative to the working directory")
    root: str | None = Field(default=None, description="Optional search root")
    limit: int = Field(default=200, ge=1, le=5000)


class GlobTool(BaseTool):
    """List files matching a glob pattern."""

    name = "glob"
    description = "List files matching a glob pattern."
    input_model = GlobToolInput

    def is_read_only(self, arguments: GlobToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: GlobToolInput, context: ToolExecutionContext) -> ToolResult:
        from openharness.sandbox.session import get_docker_sandbox
        session = get_docker_sandbox()

        if session:
            # 路径重定向：将容器路径映射回宿主机实际物理路径
            root = session.map_to_host_path(arguments.root or ".")
            
            from openharness.sandbox.path_validator import validate_sandbox_path
            
            # 在沙箱模式下，允许在 workspace, user-home 和 local-bin 根目录下进行查找
            extra_allowed = [session.host_workspace, session.host_home, session.host_bin]
            allowed, reason = validate_sandbox_path(root, Path(session.host_workspace), extra_allowed=extra_allowed)
            
            if not allowed:
                return ToolResult(output=f"Sandbox: {reason}", is_error=True)
        else:
            # 对于 glob，我们主要验证根目录是否在工作区内
            # 由于 glob 可能涉及多个文件，这里仅验证 root 边界
            if not str(root.resolve()).startswith(str(context.cwd.resolve())):
                return ToolResult(
                    output=f"❌ 安全限制：不允许访问工作区外的目录 ({root})", 
                    is_error=True
                )

        matches = await _glob(root, arguments.pattern, limit=arguments.limit)
        if not matches:
            return ToolResult(output="(no matches)")
        return ToolResult(output="\n".join(matches))


def _resolve_path(base: Path, candidate: str | None) -> Path:
    path = Path(candidate or ".").expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _looks_like_git_repo(path: Path) -> bool:
    """Heuristic: determine whether we should include hidden paths when searching.

    For codebases, hidden dirs like `.github/` are relevant; for arbitrary dirs
    (like a user's home), searching hidden paths can explode the search space.
    """
    current = path
    for _ in range(6):
        git_dir = current / ".git"
        if git_dir.exists():
            return True
        if current.parent == current:
            break
        current = current.parent
    return False


async def _glob(root: Path, pattern: str, *, limit: int) -> list[str]:
    """Fast glob implementation.

    Uses ripgrep's file walker when available (respects .gitignore and can skip
    heavy directories like `.venv/`), with a Python fallback.
    """
    # Normalize pattern: pathlib.glob does not support patterns starting with /
    # Any leading slash is treated as relative to the search root.
    clean_pattern = pattern.lstrip("/")
    if not clean_pattern:
        clean_pattern = "*"

    rg = shutil.which("rg")
    # `Path.glob("**/*")` will traverse hidden and ignored paths (like `.venv/`)
    # and can be very slow on real workspaces. Prefer `rg --files`.
    if rg and ("**" in clean_pattern or "/" in clean_pattern):
        include_hidden = _looks_like_git_repo(root)
        cmd = [rg, "--files"]
        if include_hidden:
            cmd.append("--hidden")
        cmd.extend(["--glob", clean_pattern, "."])

        from openharness.sandbox.session import get_docker_sandbox

        session = get_docker_sandbox()
        if session is not None and session.is_running:
            process = await session.exec_command(
                cmd,
                cwd=root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        lines: list[str] = []
        try:
            assert process.stdout is not None
            while len(lines) < limit:
                raw = await process.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    lines.append(line)
        finally:
            if process.returncode is None:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=0.5)
                except (asyncio.TimeoutError, ProcessLookupError):
                    if process.returncode is None:
                        process.kill()
                        await process.wait()

        # Sorting keeps unit tests and user output deterministic for small results.
        lines.sort()
        return lines

    # Fallback: non-recursive patterns are usually cheap; keep Python semantics.
    try:
        return sorted(
            str(path.relative_to(root))
            for path in root.glob(clean_pattern)
        )[:limit]
    except (NotImplementedError, ValueError):
        # Handle cases where globbing fails due to pattern issues or path escape attempts
        return []
