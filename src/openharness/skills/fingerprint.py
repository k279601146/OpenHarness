"""Stable fingerprints for skill package contents."""

from __future__ import annotations

import hashlib
from pathlib import Path


_EXCLUDED_DIR_NAMES = {"__pycache__"}
_EXCLUDED_FILE_NAMES = {".openharness-sync.json"}
_EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def iter_skill_source_files(source_dir: str | Path):
    """Yield files that are part of the authored skill package."""
    root = Path(source_dir).expanduser().resolve()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root)
        if any(part in _EXCLUDED_DIR_NAMES for part in rel.parts):
            continue
        if path.name in _EXCLUDED_FILE_NAMES:
            continue
        if path.suffix in _EXCLUDED_SUFFIXES:
            continue
        yield path


def skill_source_fingerprint(source_dir: str | Path) -> str:
    """Return a content-based fingerprint for a skill directory."""
    root = Path(source_dir).expanduser().resolve()
    hasher = hashlib.sha256()
    for path in iter_skill_source_files(root):
        rel = path.relative_to(root).as_posix()
        stat = path.stat()
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(str(stat.st_mode & 0o777).encode("ascii"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()
