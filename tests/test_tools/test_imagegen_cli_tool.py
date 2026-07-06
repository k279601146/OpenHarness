"""Tests for the unified imagegen_cli tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.imagegen_cli_tool import ImagegenCliInput, ImagegenCliTool, _build_argv, _build_output_paths


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
    assert result.metadata["official_cost"] == 0.134
    assert result.metadata["pricing_multiplier"] == 1.0
    assert result.metadata["billing_units"] == 3.35


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
    assert result.metadata["official_currency"] == "CNY"
    assert result.metadata["billing_units"] == 1.4


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
            background="opaque",
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
        "--background": "opaque",
        "--output-format": "webp",
        "--output-compression": "82",
        "--moderation": "low",
    }.items():
        assert flag in argv
        assert argv[argv.index(flag) + 1] == value


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
async def test_imagegen_cli_e2b_uploads_artifact_and_returns_sandbox_path(
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
    monkeypatch.setenv("GPT_IMAGEGEN_API_KEY", "test-image-key")

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
    assert result.metadata["artifact_paths"] == ["/home/user/projects/deck/images/cover_bg.png"]
    assert result.metadata["sandbox_path_role"] == "workspace_mirror"
    assert result.metadata["publish_state"] == "published"
    assert result.metadata["delivery_required"] is False
    assert result.metadata["do_not_deliver_artifact"] is True
    assert sandbox.files["/home/user/projects/deck/images/cover_bg.png"] == b"png-bytes"
    assert "D:\\home\\user" not in result.output
    assert "/home/user/projects/deck/images/cover_bg.png" in result.output
    assert "Do not call deliver_artifact" in result.output
    assert seen_env["GPT_IMAGEGEN_API_KEY"] == "test-image-key"
    assert hook.calls == [
        {
            "file_path": hook.calls[0]["file_path"],
            "reason": "Generated image via imagegen CLI: imagegen_output.png",
            "source_tool": "imagegen_cli",
            "tool_use_id": "call-image",
            "origin": "host_generated",
            "sandbox_path": "/home/user/projects/deck/images/cover_bg.png",
            "sandbox_path_role": "workspace_mirror",
            "metadata": {
                "publish_state": "published",
                "published_artifact": True,
                "delivery_required": False,
                "do_not_deliver_artifact": True,
            },
        }
    ]
