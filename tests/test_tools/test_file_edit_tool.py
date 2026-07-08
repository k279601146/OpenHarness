"""Tests for precise edit_file behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.file_edit_tool import FileEditTool, FileEditToolInput


@pytest.mark.asyncio
async def test_file_edit_replaces_unique_match_and_reports_metadata(tmp_path: Path):
    target = tmp_path / "notes.txt"
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = await FileEditTool().execute(
        FileEditToolInput(path="notes.txt", old_str="two", new_str="TWO"),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is False
    assert target.read_text(encoding="utf-8") == "one\nTWO\nthree\n"
    assert result.metadata == {
        "path": str(target),
        "workspace": "host",
        "match_count": 1,
        "replacements": 1,
        "changed": True,
    }


@pytest.mark.asyncio
async def test_file_edit_rejects_ambiguous_single_replace(tmp_path: Path):
    target = tmp_path / "notes.txt"
    target.write_text("alpha\nbeta\nbeta\n", encoding="utf-8")

    result = await FileEditTool().execute(
        FileEditToolInput(path="notes.txt", old_str="beta", new_str="BETA"),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is True
    assert "matched 2 times" in result.output
    assert target.read_text(encoding="utf-8") == "alpha\nbeta\nbeta\n"


@pytest.mark.asyncio
async def test_file_edit_replace_all_updates_every_match(tmp_path: Path):
    target = tmp_path / "notes.txt"
    target.write_text("alpha\nbeta\nbeta\n", encoding="utf-8")

    result = await FileEditTool().execute(
        FileEditToolInput(
            path="notes.txt",
            old_str="beta",
            new_str="BETA",
            replace_all=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is False
    assert target.read_text(encoding="utf-8") == "alpha\nBETA\nBETA\n"
    assert result.metadata["match_count"] == 2
    assert result.metadata["replacements"] == 2


@pytest.mark.asyncio
async def test_file_edit_rejects_empty_old_str(tmp_path: Path):
    target = tmp_path / "notes.txt"
    target.write_text("alpha\n", encoding="utf-8")

    result = await FileEditTool().execute(
        FileEditToolInput(path="notes.txt", old_str="", new_str="BETA"),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is True
    assert "old_str must not be empty" in result.output
    assert target.read_text(encoding="utf-8") == "alpha\n"


@pytest.mark.asyncio
async def test_file_edit_rejects_missing_directory_workspace_escape_and_sensitive_paths(
    tmp_path: Path,
):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("secret\n", encoding="utf-8")
    try:
        (tmp_path / "folder").mkdir()
        (tmp_path / ".env.local").write_text("TOKEN=value\n", encoding="utf-8")

        context = ToolExecutionContext(cwd=tmp_path)
        missing = await FileEditTool().execute(
            FileEditToolInput(path="missing.txt", old_str="x", new_str="y"),
            context,
        )
        directory = await FileEditTool().execute(
            FileEditToolInput(path="folder", old_str="x", new_str="y"),
            context,
        )
        escaped = await FileEditTool().execute(
            FileEditToolInput(path=str(outside), old_str="secret", new_str="redacted"),
            context,
        )
        sensitive = await FileEditTool().execute(
            FileEditToolInput(path=".env.local", old_str="TOKEN", new_str="SAFE"),
            context,
        )

        assert missing.is_error is True
        assert "File not found" in missing.output
        assert directory.is_error is True
        assert "Cannot edit directory" in directory.output
        assert escaped.is_error is True
        assert "outside the workspace" in escaped.output
        assert sensitive.is_error is True
        assert "sensitive environment file" in sensitive.output
        assert outside.read_text(encoding="utf-8") == "secret\n"
        assert (tmp_path / ".env.local").read_text(encoding="utf-8") == "TOKEN=value\n"
    finally:
        outside.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_file_edit_rejects_sensitive_symlink_target(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside-secret.txt"
    outside.write_text("secret\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError) as exc:
        outside.unlink(missing_ok=True)
        pytest.skip(f"symlinks are unavailable: {exc}")

    try:
        result = await FileEditTool().execute(
            FileEditToolInput(path="link.txt", old_str="secret", new_str="redacted"),
            ToolExecutionContext(cwd=tmp_path),
        )

        assert result.is_error is True
        assert "outside the workspace" in result.output
        assert outside.read_text(encoding="utf-8") == "secret\n"
    finally:
        link.unlink(missing_ok=True)
        outside.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_file_edit_rejects_when_edit_approval_denied(tmp_path: Path):
    target = tmp_path / "notes.txt"
    target.write_text("one\ntwo\n", encoding="utf-8")
    approvals: list[tuple[str, str, int, int]] = []

    async def _reject(path: str, diff: str, added: int, removed: int) -> str:
        approvals.append((path, diff, added, removed))
        return "reject"

    result = await FileEditTool().execute(
        FileEditToolInput(path="notes.txt", old_str="two", new_str="TWO"),
        ToolExecutionContext(cwd=tmp_path, metadata={"edit_approval_prompt": _reject}),
    )

    assert result.is_error is True
    assert "Edit rejected by user" in result.output
    assert target.read_text(encoding="utf-8") == "one\ntwo\n"
    assert len(approvals) == 1
    path, diff, added, removed = approvals[0]
    assert path == str(target)
    assert added == 1
    assert removed == 1
    assert "-two" in diff
    assert "+TWO" in diff


@pytest.mark.asyncio
async def test_file_edit_rejects_when_file_changes_during_approval(tmp_path: Path):
    target = tmp_path / "notes.txt"
    target.write_text("one\ntwo\n", encoding="utf-8")

    async def _mutate_and_approve(path: str, diff: str, added: int, removed: int) -> str:
        del path, diff, added, removed
        target.write_text("one\nchanged\n", encoding="utf-8")
        return "once"

    result = await FileEditTool().execute(
        FileEditToolInput(path="notes.txt", old_str="two", new_str="TWO"),
        ToolExecutionContext(cwd=tmp_path, metadata={"edit_approval_prompt": _mutate_and_approve}),
    )

    assert result.is_error is True
    assert "changed while edit approval was pending" in result.output
    assert target.read_text(encoding="utf-8") == "one\nchanged\n"
