from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from openharness.engine.query import _format_tool_validation_error
from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext
from openharness.tools.create_handdraw_story_video_tool import (
    CreateHanddrawStoryVideoInput,
    CreateHanddrawStoryVideoTool,
)


class FakeHanddrawHook:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict]] = []

    async def create_handdraw_story_video(self, request: dict, context_metadata: dict) -> dict:
        self.calls.append((request, context_metadata))
        return {
            "media_billing_status": "skipped",
            "artifact_payloads": [
                {
                    "artifact_id": "artifact-video-1",
                    "url": "/artifacts/video/thread/story.mp4",
                    "type": "video",
                    "file_path": "D:/internal/story.mp4",
                }
            ],
        }


def _valid_scenes() -> list[dict]:
    return [
        {
            "id": f"scene-{index:02d}",
            "duration": 5,
            "caption_lines": [f"第{index}幕开始"],
            "color_image_ref": f"artifact:scene-{index}",
        }
        for index in range(1, 8)
    ]


def _valid_input(**overrides) -> dict:
    payload = {
        "title": "凌晨豆浆",
        "topic": "早餐摊的一次善意",
        "scenes": _valid_scenes(),
        "output": {},
        "caption_policy": {},
    }
    payload.update(overrides)
    return payload


def test_default_registry_includes_handdraw_story_video_tool() -> None:
    registry = create_default_tool_registry()

    assert registry.get("create_handdraw_story_video") is not None


def test_handdraw_story_video_schema_uses_canonical_fields() -> None:
    input_schema = CreateHanddrawStoryVideoTool().to_api_schema()["input_schema"]
    schema = input_schema["properties"]

    assert "title" in schema
    assert "topic" in schema
    assert "scenes" in schema
    assert "output" in schema
    assert "caption_policy" in schema
    assert "bgm" in schema
    assert "bgm_ref" in schema
    assert "style_notes" in schema
    for legacy in (
        "provider",
        "base_url",
        "api_key",
        "model",
        "price",
        "billing_units",
        "output_path",
        "command",
        "config",
    ):
        assert legacy not in schema
    assert "$defs" not in input_schema
    assert "$ref" not in str(input_schema)
    assert set(input_schema["required"]) >= {"title", "topic", "scenes", "output", "caption_policy"}
    assert schema["output"]["type"] == "object"
    assert schema["caption_policy"]["type"] == "object"
    bgm_object_schema = next(item for item in schema["bgm"]["anyOf"] if item.get("type") == "object")
    assert bgm_object_schema["type"] == "object"
    assert set(bgm_object_schema["properties"]) >= {"mode", "mood", "ref", "volume", "loop"}
    assert "Never pass a quoted JSON string" in schema["output"]["description"]
    assert "Never pass a quoted JSON string" in schema["caption_policy"]["description"]
    assert "Never pass a quoted JSON string" in schema["bgm"]["description"]


@pytest.mark.parametrize(
    "legacy_field",
    ["provider", "base_url", "api_key", "model", "price", "billing_units", "output_path", "command"],
)
def test_handdraw_story_video_rejects_legacy_fields(legacy_field: str) -> None:
    with pytest.raises(ValidationError):
        CreateHanddrawStoryVideoInput(**_valid_input(**{legacy_field: "legacy"}))


@pytest.mark.parametrize(
    "bad_ref",
    [
        r"C:\Users\Administrator\secret.png",
        "/home/user/tasks/thread/image.png",
        "file:///tmp/image.png",
        "data:image/png;base64,AAAA",
        "blob:http://localhost/image",
        "https://cdn.example.com/image.png",
        "https://app.example.com/artifacts/video/thread/image.png",
        "artifacts/video/thread/image.png",
        "/artifacts/../uploads/7/image.png",
        "artifact:../secret",
    ],
)
def test_handdraw_story_video_rejects_unsafe_image_refs(bad_ref: str) -> None:
    payload = _valid_input()
    payload["scenes"][0] = {**payload["scenes"][0], "color_image_ref": bad_ref}

    with pytest.raises(ValidationError):
        CreateHanddrawStoryVideoInput(**payload)


def test_handdraw_story_video_accepts_controlled_bgm_modes() -> None:
    library = CreateHanddrawStoryVideoInput(**_valid_input(bgm={"mode": "library", "mood": "warm"}))
    upload = CreateHanddrawStoryVideoInput(
        **_valid_input(bgm={"mode": "upload", "ref": "artifact:audio-1", "volume": "normal"})
    )
    legacy = CreateHanddrawStoryVideoInput(**_valid_input(bgm_ref="artifact:audio-legacy"))

    assert library.bgm is not None
    assert library.bgm.mode == "library"
    assert library.bgm.mood == "warm"
    assert upload.bgm is not None
    assert upload.bgm.ref == "artifact:audio-1"
    assert legacy.bgm_ref == "artifact:audio-legacy"


@pytest.mark.parametrize(
    "bgm",
    [
        {"mode": "library", "ref": "artifact:audio-1"},
        {"mode": "library", "ref": "bgm:../secret"},
        {"mode": "upload", "ref": r"C:\Users\Administrator\secret.mp3"},
        {"mode": "upload", "ref": "file:///tmp/music.mp3"},
        {"mode": "upload", "ref": "data:audio/mp3;base64,AAAA"},
        {"mode": "upload", "ref": "blob:http://localhost/music"},
        {"mode": "upload", "ref": "https://cdn.example.com/music.mp3"},
        {"mode": "none", "mood": "warm"},
    ],
)
def test_handdraw_story_video_rejects_unsafe_bgm_refs(bgm: dict) -> None:
    with pytest.raises(ValidationError):
        CreateHanddrawStoryVideoInput(**_valid_input(bgm=bgm))


def test_handdraw_story_video_rejects_bgm_and_legacy_bgm_ref_conflict() -> None:
    with pytest.raises(ValidationError):
        CreateHanddrawStoryVideoInput(
            **_valid_input(
                bgm={"mode": "library", "mood": "warm"},
                bgm_ref="artifact:audio-legacy",
            )
        )


def test_handdraw_story_video_rejects_json_string_objects() -> None:
    with pytest.raises(ValidationError) as exc:
        CreateHanddrawStoryVideoInput(
            title="Story",
            topic="A helpful neighbor",
            scenes=_valid_scenes(),
            output='{"width":720}',  # type: ignore[arg-type]
            caption_policy='{"enabled":true}',  # type: ignore[arg-type]
            bgm='{"mode":"library"}',  # type: ignore[arg-type]
        )

    message = _format_tool_validation_error("create_handdraw_story_video", exc.value)

    assert message.startswith("invalid_canonical_request:")
    assert "`output` must be an object, not a JSON string" in message
    assert "`caption_policy` must be an object, not a JSON string" in message
    assert "`bgm` must be an object, not a JSON string" in message
    assert "Retry by calling create_handdraw_story_video again" in message
    assert "pydantic.dev" not in message
    assert "ValidationError" not in message


def test_handdraw_story_video_rejects_missing_required_objects() -> None:
    with pytest.raises(ValidationError) as exc:
        CreateHanddrawStoryVideoInput(title="Story", topic="A helpful neighbor", scenes=_valid_scenes())

    message = _format_tool_validation_error("create_handdraw_story_video", exc.value)

    assert "`output` is required and must be an object" in message
    assert "`caption_policy` is required and must be an object" in message


@pytest.mark.asyncio
async def test_handdraw_story_video_delegates_to_backend_hook(tmp_path: Path) -> None:
    hook = FakeHanddrawHook()

    result = await CreateHanddrawStoryVideoTool().execute(
        CreateHanddrawStoryVideoInput(**_valid_input()),
        ToolExecutionContext(cwd=tmp_path, metadata={"hook": hook, "tool_use_id": "tool-1"}),
    )

    assert not result.is_error
    assert result.metadata["media_billing_status"] == "skipped"
    assert result.metadata["delivery_required"] is False
    assert result.metadata["bgm_status"] == "none"
    assert result.metadata["artifact_id"] == "artifact-video-1"
    assert "file_path" not in str(result.metadata["artifact_payloads"])
    assert len(hook.calls) == 1
    request, metadata = hook.calls[0]
    assert request["title"] == "凌晨豆浆"
    assert request["scenes"][0]["color_image_ref"] == "artifact:scene-1"
    assert metadata["cwd"] == str(tmp_path)


@pytest.mark.asyncio
async def test_handdraw_story_video_sanitizes_backend_exceptions(tmp_path: Path) -> None:
    class LeakyHook:
        async def create_handdraw_story_video(self, request: dict, context_metadata: dict) -> dict:
            raise RuntimeError(r"D:\internal\secret\story.mp4")

    result = await CreateHanddrawStoryVideoTool().execute(
        CreateHanddrawStoryVideoInput(**_valid_input()),
        ToolExecutionContext(cwd=tmp_path, metadata={"hook": LeakyHook()}),
    )

    assert result.is_error
    assert result.metadata["handdraw_story_video_status"] == "failed"
    assert "D:\\internal" not in result.output
    assert "secret" not in result.output


@pytest.mark.asyncio
async def test_handdraw_story_video_requires_saas_backend(tmp_path: Path) -> None:
    result = await CreateHanddrawStoryVideoTool().execute(
        CreateHanddrawStoryVideoInput(**_valid_input()),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error
    assert result.metadata["media_billing_status"] == "skipped"
    assert result.metadata["handdraw_story_video_status"] == "skipped"
