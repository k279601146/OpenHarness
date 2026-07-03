"""Tests for stable skill package fingerprints."""

from __future__ import annotations

from pathlib import Path

from openharness.skills.fingerprint import iter_skill_source_files, skill_source_fingerprint
from openharness.tools.sandbox_workspace import _skill_source_manifest


def test_skill_fingerprint_ignores_generated_runtime_files(tmp_path: Path) -> None:
    skill_dir = tmp_path / "imagegen"
    runtime_dir = skill_dir / "scripts" / "imagegen_runtime"
    cache_dir = runtime_dir / "__pycache__"
    cache_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Imagegen\n", encoding="utf-8")
    (runtime_dir / "registry.py").write_text("MODELS = []\n", encoding="utf-8")

    before = skill_source_fingerprint(skill_dir)
    (cache_dir / "registry.cpython-312.pyc").write_bytes(b"compiled bytes")
    (skill_dir / ".openharness-sync.json").write_text('{"fingerprint":"old"}', encoding="utf-8")

    assert skill_source_fingerprint(skill_dir) == before
    assert sorted(path.relative_to(skill_dir).as_posix() for path in iter_skill_source_files(skill_dir)) == [
        "SKILL.md",
        "scripts/imagegen_runtime/registry.py",
    ]


def test_skill_sync_manifest_uses_same_source_file_filter(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skill"
    cache_dir = skill_dir / "scripts" / "__pycache__"
    cache_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("hello", encoding="utf-8")
    (skill_dir / ".openharness-sync.json").write_text("{}", encoding="utf-8")
    (cache_dir / "tool.cpython-312.pyc").write_bytes(b"compiled")

    assert _skill_source_manifest(skill_dir) == {"file_count": 1, "total_size": 5}
