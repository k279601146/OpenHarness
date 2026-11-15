"""Filesystem globbing tool."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from pydantic import AliasChoices, BaseModel, Field

from openharness.tools.artifact_reference_guard import artifact_lookup_guard_result
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.sandbox_workspace import (
    ensure_sandbox_skill_path,
    get_e2b_task_session,
    sandbox_glob,
    to_sandbox_path,
    uses_e2b_task_workspace,
)
from openharness.utils.paths import normalize_host_path


class GlobToolInput(BaseModel):
    """Arguments for the glob tool."""

    pattern: str = Field(
        description="Glob pattern relative to the working directory",
        validation_alias=AliasChoices("pattern", "path"),
    )
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
        guard_result = artifact_lookup_guard_result(context, " ".join(part for part in [arguments.root or "", arguments.pattern] if part))
        if guard_result is not None:
            return guard_result
        if uses_e2b_task_workspace(context):
            try:
                session = await get_e2b_task_session(context)
                root = to_sandbox_path(context, arguments.root)
                await ensure_sandbox_skill_path(context, session, root)
                matches = await sandbox_glob(session, root, arguments.pattern, limit=arguments.limit)
            except Exception as exc:
                return ToolResult(output=f"Sandbox workspace error: {exc}", is_error=True)
            if not matches:
                return ToolResult(output="(no matches)")
            return ToolResult(output="\n".join(matches), metadata={"root": root, "workspace": "e2b"})

        root, pattern = _resolve_glob_request(context.cwd, arguments.root, arguments.pattern)
        matches, truncated = await _glob_with_truncation(root, pattern, limit=arguments.limit)
        if not matches:
            return ToolResult(output="(no matches)")
        output = "\n".join(matches)
        if truncated:
            output += (
                f"\n\n[Results truncated to {len(matches)} matches across directories. "
                "Narrow your glob pattern or root directory.]"
            )
        return ToolResult(
            output=output,
            metadata={"count": len(matches), "truncated": truncated},
        )


def _resolve_path(base: Path, candidate: str | None) -> Path:
    return normalize_host_path(base, candidate or ".")


def _resolve_glob_request(base: Path, root_arg: str | None, pattern: str) -> tuple[Path, str]:
    """Return a concrete search root plus a root-relative glob pattern."""
    if not pattern.strip():
        return (_resolve_path(base, root_arg) if root_arg else base, pattern)

    candidate = Path(pattern).expanduser()
    if not candidate.is_absolute():
        return (_resolve_path(base, root_arg) if root_arg else base, pattern)

    parts = candidate.parts
    first_glob_index = next(
        (index for index, part in enumerate(parts) if _has_glob_magic(part)),
        None,
    )
    if first_glob_index is None:
        return candidate.parent.resolve(), candidate.name

    root_parts = parts[:first_glob_index]
    root = Path(*root_parts).resolve() if root_parts else Path(candidate.anchor or "/").resolve()
    relative_pattern = str(Path(*parts[first_glob_index:]))
    return root, relative_pattern


def _has_glob_magic(value: str) -> bool:
    return any(char in value for char in "*?[")


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


_GLOB_RG_TIMEOUT_SECONDS = 30.0


async def _glob(root: Path, pattern: str, *, limit: int) -> list[str]:
    matches, _ = await _glob_with_truncation(root, pattern, limit=limit)
    return matches


async def _glob_with_truncation(
    root: Path,
    pattern: str,
    *,
    limit: int,
) -> tuple[list[str], bool]:
    """Fast glob implementation using ripgrep (--no-config + VCS excludes) with fair sampling."""
    from openharness.tools.file_state import (
        is_ignored_search_relpath,
        rg_vcs_exclude_args,
        sample_across_top_level,
    )

    if not root.exists() or not root.is_dir():
        return [], False

    rg = shutil.which("rg")
    if rg and ("**" in pattern or "/" in pattern):
        include_hidden = _looks_like_git_repo(root)
        cmd = [rg, "--no-config", "--files", "--sort=modified"]
        if include_hidden:
            cmd.append("--hidden")
        cmd.extend(["--glob", pattern])
        cmd.extend(rg_vcs_exclude_args())
        cmd.append(".")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        lines: list[str] = []
        scan_cap = max(limit * 4, limit + 1)

        async def _read_stdout() -> None:
            assert process.stdout is not None
            while len(lines) < scan_cap:
                raw = await process.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    lines.append(line)

        try:
            try:
                await asyncio.wait_for(_read_stdout(), timeout=_GLOB_RG_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                pass
        finally:
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    await process.wait()

        if len(lines) > limit:
            return sample_across_top_level(lines, limit), True
        lines.sort()
        return lines, False

    candidates: list[str] = []
    scan_cap = max(limit * 4, limit + 1)
    for path in root.glob(pattern):
        rel_path = path.relative_to(root)
        if is_ignored_search_relpath(rel_path, pattern=pattern):
            continue
        candidates.append(str(rel_path))
        if len(candidates) >= scan_cap:
            break

    if len(candidates) > limit:
        return sample_across_top_level(candidates, limit), True
    return sorted(candidates), False
