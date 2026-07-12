"""Bundled plugin roots shipped with OpenHarness."""

from __future__ import annotations

from pathlib import Path

_BUNDLED_PLUGIN_ROOT = Path(__file__).parent / "content"


def get_bundled_plugin_roots() -> list[Path]:
    """Return bundled plugin roots that should be loaded explicitly by hosts."""
    if not _BUNDLED_PLUGIN_ROOT.exists():
        return []
    return [_BUNDLED_PLUGIN_ROOT]


__all__ = ["get_bundled_plugin_roots"]
