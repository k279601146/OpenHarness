"""Tests for the unified videogen_cli tool."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext
from openharness.tools.media_gateway_runtime import MediaSubprocessResult
from openharness.tools.videogen_cli_tool import VideogenCliInput, VideogenCliTool, _build_argv, _build_output_paths
from openharness.skills.bundled.content.videogen.scripts.videogen_runtime.providers import _build_payload
from openharness.skills.bundled.content.videogen.scripts.videogen_runtime.registry import get_model_spec


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
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")

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
async def test_videogen_cli_kling_3_accepts_fifteen_seconds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")

    result = await VideogenCliTool().execute(
        VideogenCliInput(
            command="generate",
            prompt="a longer cinematic product shot",
            model="kling-3.0",
            duration_seconds=15,
            resolution="1080p",
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert not result.is_error
    assert result.metadata["video_model_id"] == "kling-3.0"
    assert result.metadata["duration_seconds"] == 15


@pytest.mark.asyncio
async def test_videogen_cli_uses_ui_preferred_video_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")

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
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")
    monkeypatch.setenv("BILLING_CREDITS_PER_USD", "25")

    tool = VideogenCliTool()
    result = await tool.execute(
        VideogenCliInput(
            command="generate",
            prompt="a fast cinematic shot",
            model="video3.1-fast",
            duration_seconds=8,
            aspect_ratio="9:16",
            resolution="720p",
            generate_audio=True,
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert not result.is_error
    assert result.metadata["video_model_id"] == "veo-3.1-fast"
    assert result.metadata["billing_scheme"] == "google_veo_model_resolution_seconds"
    assert result.metadata["aspect_ratio"] == "9:16"
    assert result.metadata["generate_audio"] is True
    assert result.metadata["billing_units"] == 20.0


@pytest.mark.asyncio
async def test_videogen_cli_veo_accepts_4k_eight_seconds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")

    result = await VideogenCliTool().execute(
        VideogenCliInput(
            command="generate",
            prompt="a cinematic 4k shot",
            model="veo-3.1",
            resolution="4k",
            duration_seconds=8,
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert not result.is_error
    assert result.metadata["video_model_id"] == "veo-3.1"
    assert result.metadata["resolution"] == "4k"
    assert result.metadata["duration_seconds"] == 8


@pytest.mark.asyncio
async def test_videogen_cli_veo_720p_duration_matrix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")
    tool = VideogenCliTool()

    for duration in (4, 6, 8):
        result = await tool.execute(
            VideogenCliInput(
                command="generate",
                prompt=f"a {duration}s 720p shot",
                model="veo-3.1",
                resolution="720p",
                duration_seconds=duration,
                dry_run=True,
            ),
            ToolExecutionContext(cwd=tmp_path),
        )
        assert not result.is_error
        assert result.metadata["duration_seconds"] == duration

    rejected = await tool.execute(
        VideogenCliInput(
            command="generate",
            prompt="a 5s 720p shot",
            model="veo-3.1",
            resolution="720p",
            duration_seconds=5,
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )
    assert rejected.is_error
    assert "Unsupported duration_seconds=5" in rejected.output
    assert "Supported values: 4, 6, 8" in rejected.output


@pytest.mark.asyncio
async def test_videogen_cli_veo_rejects_4k_four_seconds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")

    result = await VideogenCliTool().execute(
        VideogenCliInput(
            command="generate",
            prompt="a short 4k shot",
            model="veo-3.1",
            resolution="4k",
            duration_seconds=4,
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error
    assert "Unsupported duration_seconds=4" in result.output
    assert "Supported values: 8" in result.output


@pytest.mark.asyncio
async def test_videogen_cli_veo_resolution_specific_default_duration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")

    result = await VideogenCliTool().execute(
        VideogenCliInput(
            command="generate",
            prompt="a 1080p shot",
            model="veo-3.1-fast",
            resolution="1080p",
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert not result.is_error
    assert result.metadata["resolution"] == "1080p"
    assert result.metadata["duration_seconds"] == 8


@pytest.mark.asyncio
async def test_videogen_cli_seedance_first_last_billing_dimensions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")
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
    assert result.metadata["aspect_ratio"] == "16:9"
    assert result.metadata["mode"] == "pro"
    assert result.metadata["generate_audio"] is True
    assert result.metadata["billing_units"] > 0


@pytest.mark.asyncio
async def test_videogen_cli_rejects_unsupported_watermark(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")

    result = await VideogenCliTool().execute(
        VideogenCliInput(
            command="generate",
            prompt="a watermarked clip",
            model="veo-3.1",
            watermark=True,
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error
    assert "does not support watermark generation" in result.output


def test_videogen_cli_and_provider_adapters_forward_supported_watermark(tmp_path: Path) -> None:
    argv = _build_argv(
        Path("video_gen.py"),
        VideogenCliInput(command="generate", prompt="clip", watermark=True),
        tmp_path,
    )
    assert "--watermark" in argv

    common_args = {
        "command": "generate",
        "duration_seconds": None,
        "duration": None,
        "aspect_ratio": None,
        "resolution": None,
        "mode": None,
        "quality": None,
        "generate_audio": False,
        "watermark": True,
        "image": [],
        "images": [],
        "reference_files": [],
        "first_frame": None,
        "last_frame": None,
    }
    veo = _build_payload(replace(get_model_spec("veo-3.1"), supports_watermark=True), SimpleNamespace(**common_args), "clip")
    seedance = _build_payload(
        replace(get_model_spec("doubao-seedance-2-0-260128"), supports_watermark=True),
        SimpleNamespace(**common_args),
        "clip",
    )
    kling = _build_payload(replace(get_model_spec("kling-3.0"), supports_watermark=True), SimpleNamespace(**common_args), "clip")

    assert veo["parameters"]["watermark"] is True
    assert seedance["watermark"] is True
    assert kling["watermark"] is True


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
async def test_videogen_cli_e2b_publishes_without_uploading_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = FakeE2BSession()
    hook = FakeArtifactHook()
    seen_env: dict[str, str] = {}

    async def fake_get_session(context):
        del context
        return sandbox

    async def fake_run_media_subprocess(*, argv, cwd, env, timeout_seconds, context, kind):
        del cwd, timeout_seconds, context, kind
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

        output = f"Wrote {local_path}\nVIDEOGEN_METADATA:{__import__('json').dumps(metadata)}"
        return MediaSubprocessResult(0, output, {})

    monkeypatch.setattr("openharness.tools.videogen_cli_tool.get_e2b_task_session", fake_get_session)
    monkeypatch.setattr("openharness.tools.videogen_cli_tool.run_media_subprocess", fake_run_media_subprocess)
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-video-key")

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
    assert len(result.metadata["artifact_paths"]) == 1
    assert "sandbox_path_role" not in result.metadata
    assert result.metadata["publish_state"] == "published"
    assert result.metadata["delivery_required"] is False
    assert result.metadata["do_not_deliver_artifact"] is True
    assert sandbox.files == {}
    assert "D:\\home\\user" not in result.output
    assert "Published artifact paths:" in result.output
    assert seen_env["OPENHARNESS_MEDIA_GATEWAY_API_KEY"] == "test-video-key"
    assert hook.calls == [
        {
            "file_path": hook.calls[0]["file_path"],
            "reason": "Generated video via videogen CLI: videogen_output.mp4",
            "source_tool": "videogen_cli",
            "tool_use_id": "call-video",
            "origin": "host_generated",
            "metadata": {
                "publish_state": "published",
                "published_artifact": True,
                "delivery_required": False,
                "do_not_deliver_artifact": True,
            },
        }
    ]


@pytest.mark.asyncio
async def test_videogen_cli_e2b_materializes_artifact_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = FakeE2BSession()
    sandbox.files["/home/user/tasks/thread-1/inputs/materialized/first-art_123.png"] = b"png"
    seen_argv: list[str] = []
    seen_input = b""

    async def fake_get_session(context):
        del context
        return sandbox

    async def fake_materializer(raw, *, sandbox_session):
        assert raw == "artifact:art_123"
        assert sandbox_session is sandbox
        return {"sandbox_path": "/home/user/tasks/thread-1/inputs/materialized/first-art_123.png"}

    async def fake_run_media_subprocess(*, argv, cwd, env, timeout_seconds, context, kind):
        nonlocal seen_input
        del cwd, env, timeout_seconds, context, kind
        seen_argv[:] = list(argv)
        seen_input = Path(argv[argv.index("--image") + 1]).read_bytes()
        out_index = argv.index("--out") + 1
        local_path = Path(argv[out_index])
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(b"mp4-bytes")
        output = f"VIDEOGEN_METADATA:{__import__('json').dumps({'artifact_paths': [str(local_path)]})}"
        return MediaSubprocessResult(0, output, {})

    monkeypatch.setattr("openharness.tools.videogen_cli_tool.get_e2b_task_session", fake_get_session)
    monkeypatch.setattr("openharness.tools.videogen_cli_tool.run_media_subprocess", fake_run_media_subprocess)

    result = await VideogenCliTool().execute(
        VideogenCliInput(command="image-to-video", prompt="animate", images=["artifact:art_123"], out="output/videogen/clip.mp4"),
        ToolExecutionContext(
            cwd=tmp_path,
            metadata={
                "workspace_backend": "e2b",
                "primary_workspace": "/home/user/tasks/thread-1",
                "settings": object(),
                "user_id": 1,
                "thread_id": "thread-1",
                "artifact_materializer": fake_materializer,
            },
        ),
    )

    assert not result.is_error
    image_arg = seen_argv[seen_argv.index("--image") + 1]
    assert image_arg.endswith("image_1.png")
    assert seen_input == b"png"
