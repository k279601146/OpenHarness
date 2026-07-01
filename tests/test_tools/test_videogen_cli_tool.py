"""Tests for the unified videogen_cli tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext
from openharness.tools.videogen_cli_tool import VideogenCliInput, VideogenCliTool, _build_output_paths


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


class FakeArtifactHook:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def on_artifact(self, file_path: str, **kwargs) -> None:
        self.calls.append({"file_path": file_path, **kwargs})


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


@pytest.mark.asyncio
async def test_videogen_cli_e2b_uploads_artifact_and_returns_sandbox_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = FakeE2BSession()
    hook = FakeArtifactHook()
    seen_env: dict[str, str] = {}

    async def fake_get_session(context):
        del context
        return sandbox

    def fake_run(argv, cwd, env, text, stdout, stderr, timeout, check):
        del cwd, text, stdout, stderr, timeout, check
        seen_env.update(env)
        out_index = argv.index("--out") + 1
        local_path = Path(argv[out_index])
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(b"mp4-bytes")
        metadata = {
            "artifact_paths": [str(local_path)],
            "video_model_id": "seedance-1.5-pro",
            "provider": "seedance",
        }

        class Completed:
            returncode = 0
            stdout = f"Wrote {local_path}\nVIDEOGEN_METADATA:{__import__('json').dumps(metadata)}"

        return Completed()

    monkeypatch.setattr("openharness.tools.videogen_cli_tool.get_e2b_task_session", fake_get_session)
    monkeypatch.setattr("openharness.tools.videogen_cli_tool.subprocess.run", fake_run)
    monkeypatch.setenv("SEEDANCE_VIDEO_API_KEY", "test-video-key")

    result = await VideogenCliTool().execute(
        VideogenCliInput(
            command="generate",
            prompt="intro",
            out="/home/user/projects/deck/videos/intro.mp4",
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
                "tool_use_id": "call-video",
                "hook": hook,
            },
        ),
    )

    assert not result.is_error
    assert result.metadata["artifact_paths"] == ["/home/user/projects/deck/videos/intro.mp4"]
    assert result.metadata["sandbox_path_role"] == "workspace_mirror"
    assert result.metadata["publish_state"] == "published"
    assert result.metadata["delivery_required"] is False
    assert result.metadata["do_not_deliver_artifact"] is True
    assert sandbox.files["/home/user/projects/deck/videos/intro.mp4"] == b"mp4-bytes"
    assert "D:\\home\\user" not in result.output
    assert "/home/user/projects/deck/videos/intro.mp4" in result.output
    assert "Do not call deliver_artifact" in result.output
    assert seen_env["SEEDANCE_VIDEO_API_KEY"] == "test-video-key"
    assert hook.calls == [
        {
            "file_path": hook.calls[0]["file_path"],
            "reason": "Generated video via videogen CLI: videogen_output.mp4",
            "source_tool": "videogen_cli",
            "tool_use_id": "call-video",
            "origin": "host_generated",
            "sandbox_path": "/home/user/projects/deck/videos/intro.mp4",
            "sandbox_path_role": "workspace_mirror",
            "metadata": {
                "publish_state": "published",
                "published_artifact": True,
                "delivery_required": False,
                "do_not_deliver_artifact": True,
            },
        }
    ]
