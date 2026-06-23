"""Tests for the unified imagegen_cli tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.imagegen_cli_tool import ImagegenCliInput, ImagegenCliTool, _build_output_paths


class FakeE2BProcess:
    stdout_str = ""

    async def communicate(self):
        return b"", b""


class FakeE2BSession:
    is_running = True

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.commands: list[str] = []

    async def exec_command(self, command: str):
        self.commands.append(command)
        return FakeE2BProcess()

    async def write_file_binary(self, path: str, content: bytes) -> None:
        self.files[path] = bytes(content)

    async def read_file_binary(self, path: str) -> bytes:
        return self.files[path]


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


@pytest.mark.asyncio
async def test_imagegen_cli_e2b_uploads_artifact_and_returns_sandbox_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = FakeE2BSession()

    async def fake_get_session(context):
        del context
        return sandbox

    def fake_run(argv, cwd, env, text, stdout, stderr, timeout, check):
        del cwd, env, text, stdout, stderr, timeout, check
        out_index = argv.index("--out") + 1
        local_path = Path(argv[out_index])
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(b"png-bytes")
        metadata = {
            "artifact_paths": [str(local_path)],
            "model_id": "kolors",
            "provider": "openai_compatible",
        }

        class Completed:
            returncode = 0
            stdout = f"Wrote {local_path}\nIMAGEGEN_METADATA:{__import__('json').dumps(metadata)}"

        return Completed()

    monkeypatch.setattr("openharness.tools.imagegen_cli_tool.get_e2b_task_session", fake_get_session)
    monkeypatch.setattr("openharness.tools.imagegen_cli_tool.subprocess.run", fake_run)

    result = await ImagegenCliTool().execute(
        ImagegenCliInput(
            command="generate",
            prompt="cover",
            out="/home/user/projects/deck/images/cover_bg.png",
            force=True,
        ),
        ToolExecutionContext(
            cwd=tmp_path,
            metadata={
                "workspace_backend": "e2b",
                "primary_workspace": "/home/user",
                "settings": object(),
                "user_id": 1,
                "thread_id": "thread-1",
            },
        ),
    )

    assert not result.is_error
    assert result.metadata["artifact_paths"] == ["/home/user/projects/deck/images/cover_bg.png"]
    assert sandbox.files["/home/user/projects/deck/images/cover_bg.png"] == b"png-bytes"
    assert "D:\\home\\user" not in result.output
    assert "/home/user/projects/deck/images/cover_bg.png" in result.output
