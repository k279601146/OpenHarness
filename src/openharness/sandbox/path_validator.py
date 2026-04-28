"""Path boundary enforcement for sandbox file operations."""

from __future__ import annotations

from pathlib import Path


def validate_sandbox_path(
    path: Path,
    cwd: Path,
    extra_allowed: list[str] | None = None,
) -> tuple[bool, str]:
    """Check whether *path* falls within the sandbox boundary.

    Returns ``(True, "")`` when the path is allowed, or ``(False, reason)``
    when it falls outside the permitted directories.
    """
    resolved = path.resolve()
    resolved_cwd = cwd.resolve()

    # Primary check: path must be within the project directory (workspace)
    try:
        resolved.relative_to(resolved_cwd)
        return True, ""
    except ValueError:
        pass
    
    # [Enhancement] 如果提供了 extra_allowed，检查是否属于其他持久化层
    # 比如在 Docker 沙箱模式下，允许访问 user-home 和 local-bin
    for allowed in extra_allowed or []:
        try:
            allowed_path = Path(allowed).resolve()
            resolved.relative_to(allowed_path)
            return True, ""
        except ValueError:
            continue

    return False, f"path {resolved} is outside the sandbox boundary ({resolved_cwd})"
