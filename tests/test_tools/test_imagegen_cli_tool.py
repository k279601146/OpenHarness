"""Tests for the unified imagegen_cli tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.imagegen_cli_tool import ImagegenCliInput, ImagegenCliTool, _build_output_paths


@pytest.mark.asyncio
async def test_imagegen_cli_dry_run_routes_nano_banana(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NANO_BANANA_API_KEY", "test-key")

    tool = ImagegenCliTool()
    result = await tool.execute(
        ImagegenCliInput(
            command="generate",
            prompt="a cat",
            model="nano-banana-pro",
            aspect_ratio="16:9",
            out="output/imagegen/cat.png",
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert not result.is_error
    assert result.metadata["model_id"] == "nano-banana-pro"
    assert result.metadata["provider"] == "gemini"
    assert result.metadata["pricing_unit"] == 3.0
    assert result.metadata["billing_units"] == 3.0


@pytest.mark.asyncio
async def test_imagegen_cli_dry_run_routes_doubao_and_multiple_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOUBAO_IMAGE_API_KEY", "test-key")

    tool = ImagegenCliTool()
    result = await tool.execute(
        ImagegenCliInput(
            command="generate",
            prompt="a poster",
            model="doubao-seedream-5-0-260128",
            n=2,
            out="output/imagegen/poster.png",
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert not result.is_error
    assert result.metadata["model_id"] == "doubao-seedream-5-0-260128"
    assert result.metadata["provider"] == "doubao"
    assert result.metadata["output_count"] == 2
    assert result.metadata["billing_units"] == 4.0


@pytest.mark.asyncio
async def test_imagegen_cli_rejects_gpt_image_2_transparent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GPT_IMAGEGEN_API_KEY", "test-key")

    tool = ImagegenCliTool()
    result = await tool.execute(
        ImagegenCliInput(
            command="generate",
            prompt="a transparent icon",
            model="gpt-image-2",
            background="transparent",
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error
    assert "transparent backgrounds are not supported in gpt-image-2" in result.output


def test_build_output_paths_multiple(tmp_path: Path) -> None:
    paths = _build_output_paths("hero.png", "png", 2, None, tmp_path)
    assert paths == [tmp_path / "hero-1.png", tmp_path / "hero-2.png"]
