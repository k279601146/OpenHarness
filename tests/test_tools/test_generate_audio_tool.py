from __future__ import annotations

import pytest
from pydantic import ValidationError

from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext
from openharness.tools.generate_audio_tool import (
    AudioGenerationBrief,
    AudioGenerationOutput,
    GenerateAudioInput,
    GenerateAudioTool,
)


class FakeAudioHook:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict]] = []

    async def generate_audio(self, request: dict, context_metadata: dict) -> dict:
        self.calls.append((request, context_metadata))
        return {
            "media_billing_status": "recorded",
            "artifact_payloads": [
                {
                    "artifact_id": "audio-art-1",
                    "url": "/artifacts/thread/speech_123.mp3",
                }
            ],
        }


def test_default_registry_includes_generate_audio() -> None:
    registry = create_default_tool_registry()
    tool = registry.get("generate_audio")
    assert tool is not None
    assert isinstance(tool, GenerateAudioTool)


def test_generate_audio_schema_uses_canonical_fields() -> None:
    input_schema = GenerateAudioTool().to_api_schema()["input_schema"]
    props = input_schema["properties"]

    assert "intent" in props
    assert "prompt" in props
    assert "voice_id" in props
    assert "brief" in props
    assert "output" in props
    assert "language" in props
    assert "instructions" in props
    assert "model_id" in props

    for legacy in ("api_key", "base_url", "upstream_model_id", "secret", "token"):
        assert legacy not in props

    assert "prompt" in input_schema["required"]


def test_generate_audio_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        GenerateAudioInput(
            prompt="Hello world",
            unknown_random_field="unexpected",
        )


@pytest.mark.asyncio
async def test_generate_audio_tool_execution(tmp_path) -> None:
    tool = GenerateAudioTool()
    hook = FakeAudioHook()
    ctx = ToolExecutionContext(
        cwd=tmp_path,
        metadata={
            "hook": hook,
            "tool_use_id": "tool-use-audio-1",
        },
    )

    args = GenerateAudioInput(
        prompt="You are an announcer: Welcome everyone to today's show!",
        voice_id="59cb5986671546eaa6ca8ae6f29f6d22",
        output=AudioGenerationOutput(speed=1.1, format="mp3"),
    )

    result = await tool.execute(args, ctx)

    assert not result.is_error
    assert "generate_audio completed and published 1 audio artifact(s)" in result.output
    assert "artifact:audio-art-1" in result.output
    assert len(hook.calls) == 1
    req, meta = hook.calls[0]
    assert req["prompt"] == "You are an announcer: Welcome everyone to today's show!"
    assert req["voice_id"] == "59cb5986671546eaa6ca8ae6f29f6d22"
    assert req["output"]["speed"] == 1.1
    assert req["output"]["format"] == "mp3"
