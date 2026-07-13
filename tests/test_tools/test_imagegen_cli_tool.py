"""Tests for the unified imagegen_cli tool."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.imagegen_cli_tool import (
    ImagegenCliInput,
    ImagegenCliTool,
    _build_argv,
    _build_output_paths,
    _normalize_openai_sdk_base_url,
)
from openharness.tools.media_gateway_runtime import MediaSubprocessResult
from openharness.skills.bundled.content.imagegen.scripts.imagegen_runtime.providers import _build_payload, emit_metadata
from openharness.skills.bundled.content.imagegen.scripts.imagegen_runtime.registry import get_model_spec


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


def _write_test_png(path: Path, size: tuple[int, int] = (32, 32)) -> None:
    del size
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"test-image-bytes")


def test_imagegen_cli_metadata_file_does_not_write_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    metadata_path = tmp_path / "metadata.json"
    monkeypatch.setenv("OPENHARNESS_IMAGEGEN_METADATA_PATH", str(metadata_path))

    emit_metadata({"artifact_paths": ["image.png"], "billing_units": 6.0})

    captured = capsys.readouterr()
    assert "IMAGEGEN_METADATA:" not in captured.out
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["billing_units"] == 6.0


@pytest.mark.asyncio
async def test_imagegen_cli_dry_run_routes_nano_banana(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")

    tool = ImagegenCliTool()
    result = await tool.execute(
        ImagegenCliInput(
            command="generate",
            prompt="a cat",
            model="nano-banana-pro",
            aspect_ratio="16:9",
            size="4K",
            out="output/imagegen/cat.png",
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert not result.is_error
    assert result.metadata["model_id"] == "nano-banana-pro"
    assert result.metadata["provider"] == "gemini"
    assert result.metadata["size"] == "4K"
    assert result.metadata["aspect_ratio"] == "16:9"
    assert "official_cost" not in result.metadata
    assert "pricing_multiplier" not in result.metadata
    assert "billing_units" not in result.metadata


@pytest.mark.asyncio
async def test_imagegen_cli_doubao_aspect_ratio_is_forwarded_as_execution_parameter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")

    result = await ImagegenCliTool().execute(
        ImagegenCliInput(
            command="generate",
            prompt="a vertical poster",
            model="doubao-seedream-5-0-260128",
            aspect_ratio="9:16",
            out="output/imagegen/poster.png",
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert not result.is_error
    assert result.metadata["resolution"] == "2K"
    assert result.metadata["size"] == "2048x2048"
    assert result.metadata["aspect_ratio"] == "9:16"
    assert result.metadata["execution_parameters"]["requested"]["aspect_ratio"] == "9:16"


@pytest.mark.asyncio
async def test_imagegen_cli_dry_run_routes_doubao_and_multiple_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")

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
    assert result.metadata["size"] == "2048x2048"
    assert result.metadata["quality"] == "medium"
    assert result.metadata["output_count"] == 2
    assert "official_currency" not in result.metadata
    assert "billing_units" not in result.metadata


@pytest.mark.asyncio
async def test_imagegen_cli_preserves_kolors_execution_hints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-key")

    result = await ImagegenCliTool().execute(
        ImagegenCliInput(
            command="generate",
            prompt="小红书美女封面图",
            model="kolors",
            resolution="2K",
            aspect_ratio="9:16",
            n=2,
            out="output/imagegen/xhs.png",
            dry_run=True,
        ),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert not result.is_error
    assert result.metadata["model_id"] == "kolors"
    assert result.metadata["resolution"] == "2K"
    assert result.metadata["size"] == "720x1280"
    assert result.metadata["effective_size"] == "720x1280"
    assert result.metadata["aspect_ratio"] == "9:16"
    assert result.metadata["requested_aspect_ratio"] == "9:16"
    assert result.metadata["output_count"] == 2
    assert result.metadata["execution_parameters"]["requested"]["resolution"] == "2K"
    assert result.metadata["execution_parameters"]["requested"]["aspect_ratio"] == "9:16"
    assert "IMAGEGEN_METADATA:" not in result.output


def test_build_argv_filters_gpt_image_2_unsupported_parameters(tmp_path: Path) -> None:
    argv = _build_argv(
        Path("image_gen.py"),
        ImagegenCliInput(
            command="edit",
            prompt="make it brighter",
            images=["source.png"],
            model="gpt-image-2",
            background="transparent",
            input_fidelity="high",
        ),
        tmp_path,
    )

    assert "--input-fidelity" not in argv
    assert "--background" not in argv


def test_build_argv_keeps_gpt_image_2_supported_parameters(tmp_path: Path) -> None:
    argv = _build_argv(
        Path("image_gen.py"),
        ImagegenCliInput(
            command="generate",
            prompt="a poster",
            model="gpt-image-2",
            n=3,
            size="1536x1024",
            quality="high",
            output_format="webp",
            output_compression=82,
            moderation="low",
        ),
        tmp_path,
    )

    for flag, value in {
        "--n": "3",
        "--size": "1536x1024",
        "--quality": "high",
        "--output-format": "webp",
        "--output-compression": "82",
        "--moderation": "low",
    }.items():
        assert flag in argv
        assert argv[argv.index(flag) + 1] == value


def test_gpt_image_2_dry_run_payload_keeps_auto_size_when_no_size_requested() -> None:
    script = Path(__file__).resolve().parents[2] / "src/openharness/skills/bundled/content/imagegen/scripts/image_gen.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "generate",
            "--prompt",
            "a vertical poster",
            "--model",
            "gpt-image-2",
            "--resolution",
            "2K",
            "--aspect-ratio",
            "9:16",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert '"size": "auto"' in result.stdout


def test_gemini_payload_forwards_resolution_and_aspect_ratio() -> None:
    payload = _build_payload(
        get_model_spec("nano-banana-pro"),
        SimpleNamespace(resolution="4K", size=None, aspect_ratio="16:9", image=[], n=1),
        "a wide cinematic image",
    )

    image_config = payload["generationConfig"]["imageConfig"]
    assert image_config["imageSize"] == "4K"
    assert image_config["aspectRatio"] == "16:9"


def test_kolors_payload_uses_siliconflow_fields() -> None:
    payload = _build_payload(
        get_model_spec("kolors"),
        SimpleNamespace(resolution=None, size=None, aspect_ratio="9:16", image=[], n=2, negative="low quality"),
        "a vertical poster",
    )

    assert payload["provider"] == "kolors"
    assert payload["model"] == "Kwai-Kolors/Kolors"
    assert payload["image_size"] == "720x1280"
    assert payload["batch_size"] == 2
    assert payload["negative_prompt"] == "low quality"
    assert "size" not in payload
    assert "n" not in payload


def test_build_argv_omits_gpt_image_2_opaque_background_default(tmp_path: Path) -> None:
    argv = _build_argv(
        Path("image_gen.py"),
        ImagegenCliInput(
            command="generate",
            prompt="a poster",
            model="gpt-image-2",
            background="opaque",
        ),
        tmp_path,
    )

    assert "--background" not in argv


def test_build_argv_keeps_gpt_image_2_auto_background(tmp_path: Path) -> None:
    argv = _build_argv(
        Path("image_gen.py"),
        ImagegenCliInput(
            command="generate",
            prompt="a poster",
            model="gpt-image-2",
            background="auto",
        ),
        tmp_path,
    )

    assert "--background" in argv
    assert argv[argv.index("--background") + 1] == "auto"


def test_build_argv_filters_png_output_compression(tmp_path: Path) -> None:
    argv = _build_argv(
        Path("image_gen.py"),
        ImagegenCliInput(
            command="generate",
            prompt="a poster",
            model="gpt-image-2",
            output_format="png",
            output_compression=82,
        ),
        tmp_path,
    )

    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "png"
    assert "--output-compression" not in argv


def test_normalize_openai_sdk_base_url_adds_v1() -> None:
    assert (
        _normalize_openai_sdk_base_url("https://api.packyapi.com")
        == "https://api.packyapi.com/v1"
    )
    assert (
        _normalize_openai_sdk_base_url("https://api.packyapi.com/v1")
        == "https://api.packyapi.com/v1"
    )


def test_build_argv_keeps_legacy_gpt_image_input_fidelity(tmp_path: Path) -> None:
    argv = _build_argv(
        Path("image_gen.py"),
        ImagegenCliInput(
            command="edit",
            prompt="make it brighter",
            images=["source.png"],
            model="gpt-image-1.5",
            input_fidelity="high",
        ),
        tmp_path,
    )

    assert "--input-fidelity" in argv
    assert argv[argv.index("--input-fidelity") + 1] == "high"


def test_build_argv_filters_non_gpt_provider_parameters(tmp_path: Path) -> None:
    argv = _build_argv(
        Path("image_gen.py"),
        ImagegenCliInput(
            command="edit",
            prompt="make it brighter",
            images=["source.png"],
            mask="mask.png",
            model="nano-banana-pro",
            n=2,
            aspect_ratio="16:9",
            quality="high",
            background="opaque",
            output_format="webp",
            output_compression=82,
            moderation="low",
            input_fidelity="high",
        ),
        tmp_path,
    )

    assert "--size" in argv
    assert "--aspect-ratio" in argv
    assert argv[argv.index("--aspect-ratio") + 1] == "16:9"
    for flag in [
        "--n",
        "--quality",
        "--background",
        "--output-format",
        "--output-compression",
        "--moderation",
        "--mask",
        "--input-fidelity",
    ]:
        assert flag not in argv


def test_build_argv_keeps_doubao_supported_parameters(tmp_path: Path) -> None:
    argv = _build_argv(
        Path("image_gen.py"),
        ImagegenCliInput(
            command="generate",
            prompt="a poster",
            model="doubao-seedream-5-0-260128",
            n=2,
            size="2048x2048",
            aspect_ratio="1:1",
            quality="high",
            output_format="webp",
        ),
        tmp_path,
    )

    for flag, value in {
        "--n": "2",
        "--size": "2048x2048",
        "--aspect-ratio": "1:1",
    }.items():
        assert flag in argv
        assert argv[argv.index(flag) + 1] == value
    assert "--quality" not in argv
    assert "--output-format" not in argv


def test_build_output_paths_multiple(tmp_path: Path) -> None:
    paths = _build_output_paths("hero.png", "png", 2, None, tmp_path)
    assert paths == [tmp_path / "hero-1.png", tmp_path / "hero-2.png"]


@pytest.mark.asyncio
async def test_imagegen_cli_fails_when_actual_dimensions_do_not_match_requested_aspect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReleaseHook:
        def __init__(self) -> None:
            self.released = False

        def release_media_tool_usage(self, reservation, *, reason, tool_metadata):
            self.released = True
            assert reservation["resource_log_id"] == 9
            assert reason == "media_tool_failed"
            assert "aspect ratio 9:16" in tool_metadata["error"]
            return {"media_billing_status": "voided"}

    async def fake_run_media_subprocess(*, argv, cwd, env, timeout_seconds, context, kind):
        del cwd, timeout_seconds, context, kind
        out_index = argv.index("--out") + 1
        local_path = Path(argv[out_index])
        _write_test_png(local_path, size=(1024, 1024))
        metadata = {
            "artifact_paths": [str(local_path)],
            "model_id": "kolors",
            "provider": "kolors",
            "effective_size": "720x1280",
            "requested_aspect_ratio": "9:16",
        }
        Path(env["OPENHARNESS_IMAGEGEN_METADATA_PATH"]).write_text(json.dumps(metadata), encoding="utf-8")
        return MediaSubprocessResult(0, f"Wrote {local_path}", {})

    hook = ReleaseHook()
    monkeypatch.setattr("openharness.tools.imagegen_cli_tool.run_media_subprocess", fake_run_media_subprocess)
    monkeypatch.setattr("openharness.tools.imagegen_cli_tool._read_image_dimensions", lambda path: (1024, 1024))
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-image-key")

    result = await ImagegenCliTool().execute(
        ImagegenCliInput(
            command="generate",
            prompt="vertical poster",
            model="kolors",
            aspect_ratio="9:16",
            out="output/imagegen/poster.png",
            force=True,
        ),
        ToolExecutionContext(
            cwd=tmp_path,
            metadata={
                "hook": hook,
                "media_billing_reservation": {"resource_log_id": 9},
            },
        ),
    )

    assert result.is_error
    assert hook.released is True
    assert "Actual dimensions: 1024x1024" in result.output
    assert result.metadata["media_billing_status"] == "voided"
    assert result.metadata["actual_width"] == 1024
    assert result.metadata["actual_height"] == 1024


@pytest.mark.asyncio
async def test_imagegen_cli_text_generation_skips_e2b_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = FakeArtifactHook()
    seen_env: dict[str, str] = {}

    async def fake_get_session(context):
        del context
        raise AssertionError("text-to-image generation must not acquire an E2B session")

    async def fake_run_media_subprocess(*, argv, cwd, env, timeout_seconds, context, kind):
        del cwd, timeout_seconds, context, kind
        seen_env.update(env)
        out_index = argv.index("--out") + 1
        local_path = Path(argv[out_index])
        _write_test_png(local_path)
        metadata = {
            "artifact_paths": [str(local_path)],
            "model_id": "kolors",
            "provider": "kolors",
        }

        Path(env["OPENHARNESS_IMAGEGEN_METADATA_PATH"]).write_text(json.dumps(metadata), encoding="utf-8")
        output = f"Wrote {local_path}"
        return MediaSubprocessResult(0, output, {})

    monkeypatch.setattr("openharness.tools.imagegen_cli_tool.get_e2b_task_session", fake_get_session)
    monkeypatch.setattr("openharness.tools.imagegen_cli_tool.run_media_subprocess", fake_run_media_subprocess)
    monkeypatch.setattr("openharness.tools.imagegen_cli_tool._read_image_dimensions", lambda path: (32, 32))
    monkeypatch.setenv("OPENHARNESS_MEDIA_GATEWAY_API_KEY", "test-image-key")

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
                "tool_use_id": "call-image",
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
    assert "D:\\home\\user" not in result.output
    assert "IMAGEGEN_METADATA:" not in result.output
    assert "Published artifact paths:" in result.output
    assert seen_env["OPENHARNESS_MEDIA_GATEWAY_API_KEY"] == "test-image-key"
    assert "OPENHARNESS_IMAGEGEN_METADATA_PATH" in seen_env
    assert hook.calls == [
        {
            "file_path": hook.calls[0]["file_path"],
            "reason": "Generated image via imagegen CLI: imagegen_output.png",
            "source_tool": "imagegen_cli",
            "tool_use_id": "call-image",
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
async def test_imagegen_cli_e2b_materializes_artifact_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = FakeE2BSession()
    sandbox.files["/home/user/tasks/thread-1/inputs/materialized/cat-art_123.png"] = b"cat"
    seen_argv: list[str] = []
    seen_input = b""

    async def fake_get_session(context):
        del context
        return sandbox

    async def fake_materializer(raw, *, sandbox_session):
        assert raw == "artifact:art_123"
        assert sandbox_session is sandbox
        return {"sandbox_path": "/home/user/tasks/thread-1/inputs/materialized/cat-art_123.png"}

    async def fake_run_media_subprocess(*, argv, cwd, env, timeout_seconds, context, kind):
        nonlocal seen_input
        del cwd, env, timeout_seconds, context, kind
        seen_argv[:] = list(argv)
        seen_input = Path(argv[argv.index("--image") + 1]).read_bytes()
        out_index = argv.index("--out") + 1
        local_path = Path(argv[out_index])
        _write_test_png(local_path)
        output = f"IMAGEGEN_METADATA:{__import__('json').dumps({'artifact_paths': [str(local_path)]})}"
        return MediaSubprocessResult(0, output, {})

    monkeypatch.setattr("openharness.tools.imagegen_cli_tool.get_e2b_task_session", fake_get_session)
    monkeypatch.setattr("openharness.tools.imagegen_cli_tool.run_media_subprocess", fake_run_media_subprocess)
    monkeypatch.setattr("openharness.tools.imagegen_cli_tool._read_image_dimensions", lambda path: (32, 32))

    result = await ImagegenCliTool().execute(
        ImagegenCliInput(command="edit", prompt="hat", images=["artifact:art_123"], out="output/imagegen/hat.png"),
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
    assert seen_input == b"cat"


@pytest.mark.asyncio
async def test_imagegen_cli_e2b_copies_host_image_and_mask_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = FakeE2BSession()
    image_path = tmp_path / "uploads" / "source.png"
    mask_path = tmp_path / "uploads" / "mask.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"source-image")
    mask_path.write_bytes(b"mask-image")
    seen_argv: list[str] = []

    async def fake_get_session(context):
        del context
        return sandbox

    async def fake_run_media_subprocess(*, argv, cwd, env, timeout_seconds, context, kind):
        del cwd, env, timeout_seconds, context, kind
        seen_argv[:] = list(argv)
        assert Path(argv[argv.index("--image") + 1]).read_bytes() == b"source-image"
        assert Path(argv[argv.index("--mask") + 1]).read_bytes() == b"mask-image"
        out_index = argv.index("--out") + 1
        local_path = Path(argv[out_index])
        _write_test_png(local_path)
        output = f"IMAGEGEN_METADATA:{__import__('json').dumps({'artifact_paths': [str(local_path)]})}"
        return MediaSubprocessResult(0, output, {})

    monkeypatch.setattr("openharness.tools.imagegen_cli_tool.get_e2b_task_session", fake_get_session)
    monkeypatch.setattr("openharness.tools.imagegen_cli_tool.run_media_subprocess", fake_run_media_subprocess)
    monkeypatch.setattr("openharness.tools.imagegen_cli_tool._read_image_dimensions", lambda path: (32, 32))

    result = await ImagegenCliTool().execute(
        ImagegenCliInput(
            command="edit",
            prompt="put a cat",
            model="gpt-image-2",
            images=[str(image_path)],
            mask=str(mask_path),
            out="output/imagegen/cat.png",
        ),
        ToolExecutionContext(
            cwd=tmp_path,
            metadata={
                "workspace_backend": "e2b",
                "primary_workspace": "/home/user/tasks/thread-1",
                "settings": object(),
                "user_id": 1,
                "thread_id": "thread-1",
            },
        ),
    )

    assert not result.is_error
    assert seen_argv[seen_argv.index("--image") + 1].endswith("image_1.png")
    assert seen_argv[seen_argv.index("--mask") + 1].endswith("mask.png")
    assert sandbox.files == {}
