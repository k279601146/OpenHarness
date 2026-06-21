"""Tests for the unified videogen_cli tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext
from openharness.tools.videogen_cli_tool import VideogenCliInput, VideogenCliTool, _build_output_paths


@pytest.mark.asyncio
async def test_videogen_cli_dry_run_routes_keling_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KLING_VIDEO_API_KEY", "test-key")

    tool = VideogenCliTool()
    result = await tool.execute(
        VideogenCliInput(
            command="generate",
            prompt="a product video",
            model="keling-3.0",
            duration_seconds=10,
            resolution="1080p",
            out="output/videogen/product.mp4",
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert not result.is_error
    assert result.metadata["video_model_id"] == "kling-3.0"
    assert result.metadata["provider"] == "kling"
    assert result.metadata["billing_scheme"] == "kling_resource_units"
    assert result.metadata["duration_seconds"] == 10
    assert result.metadata["resolution"] == "1080p"
    assert result.metadata["billing_units"] > 0


@pytest.mark.asyncio
async def test_videogen_cli_uses_ui_preferred_video_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEO_VIDEO_API_KEY", "test-key")

    tool = VideogenCliTool()
    result = await tool.execute(
        VideogenCliInput(
            command="generate",
            prompt="a cinematic shot",
            dry_run=True,
        ),
        ToolExecutionContext(
            cwd=tmp_path,
            metadata={"media_preferences": {"video_model": "video3.1", "is_auto": False}},
        ),
    )

    assert not result.is_error
    assert result.metadata["video_model_id"] == "veo-3.1"
    assert result.metadata["provider"] == "veo"
    assert result.metadata["billing_scheme"] == "google_veo_model_resolution_seconds"


@pytest.mark.asyncio
async def test_videogen_cli_veo_fast_uses_resolution_second_billing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VEO_VIDEO_API_KEY", "test-key")
    monkeypatch.setenv("BILLING_CREDITS_PER_USD", "25")

    tool = VideogenCliTool()
    result = await tool.execute(
        VideogenCliInput(
            command="generate",
            prompt="a fast cinematic shot",
            model="video3.1-fast",
            duration_seconds=8,
            resolution="720p",
            generate_audio=True,
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert not result.is_error
    assert result.metadata["video_model_id"] == "veo-3.1-fast"
    assert result.metadata["billing_scheme"] == "google_veo_model_resolution_seconds"
    assert result.metadata["billing_units"] == 20.0


@pytest.mark.asyncio
async def test_videogen_cli_seedance_first_last_billing_dimensions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEEDANCE_VIDEO_API_KEY", "test-key")
    first = tmp_path / "first.png"
    last = tmp_path / "last.png"
    first.write_bytes(b"png")
    last.write_bytes(b"png")

    tool = VideogenCliTool()
    result = await tool.execute(
        VideogenCliInput(
            command="first-last-frame",
            prompt="transition between frames",
            model="seedance-1.5-pro",
            first_frame=str(first),
            last_frame=str(last),
            duration_seconds=6,
            resolution="1080p",
            generate_audio=True,
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert not result.is_error
    assert result.metadata["video_model_id"] == "seedance-1.5-pro"
    assert result.metadata["provider"] == "seedance"
    assert result.metadata["billing_scheme"] == "seedance_official_dimensions"
    assert result.metadata["duration_seconds"] == 6
    assert result.metadata["mode"] == "pro"
    assert result.metadata["billing_units"] > 0


def test_build_video_output_paths_multiple(tmp_path: Path) -> None:
    paths = _build_output_paths("clip.mp4", 2, None, tmp_path)
    assert paths == [tmp_path / "clip-1.mp4", tmp_path / "clip-2.mp4"]


def test_build_video_output_paths_out_dir(tmp_path: Path) -> None:
    paths = _build_output_paths("clip.mp4", 2, "renders", tmp_path)
    assert paths == [tmp_path / "renders" / "video_1.mp4", tmp_path / "renders" / "video_2.mp4"]


def test_default_registry_exposes_only_unified_video_tool() -> None:
    registry = create_default_tool_registry()
    names = {tool.name for tool in registry.list_tools()}
    assert "videogen_cli" in names
    assert "gen_creative_video" not in names
    assert "animate_first_frame" not in names
    assert "video_interpolation" not in names
    assert "video_with_reference" not in names
