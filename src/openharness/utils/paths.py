"""Path normalization helpers shared by host-side tools."""

from __future__ import annotations

import re
from pathlib import Path, PurePath, PurePosixPath
from typing import Any


_WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:/")


def normalize_host_path(base: str | Path | PurePath, candidate: Any = ".") -> Path:
    """Resolve a tool supplied path against the host cwd."""
    base_path = _to_host_path(base)
    path = _to_host_path(candidate or ".")
    if not path.is_absolute():
        path = base_path / path
    return path.expanduser().resolve()


def _to_host_path(value: Any) -> Path:
    if isinstance(value, Path):
        return value.expanduser()

    text = str(value)
    if not text:
        return Path(".")

    text = text.replace("\\", "/")
    if _WINDOWS_DRIVE_RE.match(text):
        return Path(text)

    return Path(PurePosixPath(text)).expanduser()
