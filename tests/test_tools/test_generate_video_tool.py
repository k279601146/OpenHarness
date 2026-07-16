from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from openharness.engine.query import _format_tool_validation_error, _media_output_count, _media_subtask_input
from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext
from openharness.tools.generate_video_tool import GenerateVideoInput, GenerateVideoTool


class FakeVideoHook:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict]] = []

    async def generate_video(self, request: dict, context_metadata: dict) -> dict:
        self.calls.append((request, context_metadata))
        return {
            "media_billing_status": "recorded",
            "artifact_payloads": [{"artifact_id": "artifact-1", "url": "/artifacts/thread/video.mp4"}],
        }


def test_default_registry_uses_generate_video_not_legacy_cli() -> None:
    registry = create_default_tool_registry()

    assert registry.get("generate_video") is not None
    assert registry.get("videogen_cli") is None


def test_generate_video_schema_uses_canonical_fields() -> None:
    input_schema = GenerateVideoTool().to_api_schema()["input_schema"]
    schema = input_schema["properties"]

    assert "intent" in schema
    assert "prompt" in schema
    assert "brief" in schema
    assert "output" in schema
    assert "references" in schema
    assert "model_id" in schema
    for legacy in (
        "command",
        "model",
        "provider",
        "images",
        "videos",
        "first_frame",
        "last_frame",
        "reference_files",
        "n",
        "num_videos",
        "out",
        "out_dir",
        "dry_run",
        "force",
        "timeout_seconds",
    ):
        assert legacy not in schema
    assert "$defs" not in input_schema
    assert "$ref" not in schema["output"]
    assert set(input_schema["required"]) >= {"prompt", "brief", "output"}
    assert schema["brief"]["type"] == "object"
    assert schema["output"]["type"] == "object"
    assert "Never pass a quoted JSON string" in schema["brief"]["description"]
    assert "Never pass a quoted JSON string" in schema["output"]["description"]


@pytest.mark.parametrize(
    "legacy_field",
    [
        "command",
        "model",
        "provider",
        "images",
        "videos",
        "first_frame",
        "last_frame",
        "reference_files",
        "n",
        "num_videos",
        "out",
        "out_dir",
        "dry_run",
        "force",
        "timeout_seconds",
    ],
)
def test_generate_video_schema_rejects_legacy_fields(legacy_field: str) -> None:
    with pytest.raises(ValidationError):
        GenerateVideoInput(
            prompt="Create a video.",
            brief={},
            output={},
            **{legacy_field: "legacy"},
        )


def test_generate_video_batch_logic_ignores_legacy_count_fields_for_detection_and_keeps_them_visible() -> None:
    tool_input = {
        "prompt": "Create a video.",
        "brief": {},
        "output": {"count": 2},
        "num_videos": 4,
        "n": 4,
        "batch_size": 4,
        "out_dir": "/tmp/video",
    }

    assert _media_output_count("generate_video", tool_input) == 2
    sub_input = _media_subtask_input(tool_input, index=1, kind="video")
    assert sub_input["output"]["count"] == 1
    assert sub_input["num_videos"] == 4
    assert sub_input["n"] == 4
    assert sub_input["batch_size"] == 4
    assert sub_input["out_dir"] == "/tmp/video"


def test_generate_video_rejects_json_string_objects() -> None:
    with pytest.raises(ValidationError) as exc:
        GenerateVideoInput(
            prompt="Create a video.",
            brief='{"subject":"product"}',
            output='{"duration_seconds":5}',  # type: ignore[arg-type]
        )

    message = _format_tool_validation_error("generate_video", exc.value)

    assert message.startswith("invalid_canonical_request:")
    assert "`brief` must be an object, not a JSON string" in message
    assert "`output` must be an object, not a JSON string" in message
    assert "Retry by calling generate_video again" in message
    assert "pydantic.dev" not in message
    assert "ValidationError" not in message


def test_generate_video_rejects_missing_canonical_objects() -> None:
    with pytest.raises(ValidationError) as exc:
        GenerateVideoInput(prompt="Create a video.")

    message = _format_tool_validation_error("generate_video", exc.value)

    assert "`brief` is required and must be an object" in message
    assert "`output` is required and must be an object" in message


@pytest.mark.asyncio
async def test_generate_video_delegates_to_backend_hook(tmp_path: Path) -> None:
    hook = FakeVideoHook()

    result = await GenerateVideoTool().execute(
        GenerateVideoInput(
            intent="animate",
            prompt="Animate the product image with a slow turntable motion.",
            brief={},
            output={"duration_seconds": 5, "aspect_ratio": "16:9", "count": 1},
            references=[{"input_ref": "artifact:abc", "role": "first_frame"}],
            model_id="doubao-seedance-2-0-260128",
        ),
        ToolExecutionContext(cwd=tmp_path, metadata={"hook": hook, "tool_use_id": "tool-1"}),
    )

    assert not result.is_error
    assert result.metadata["media_billing_status"] == "recorded"
    assert result.metadata["delivery_required"] is False
    assert len(hook.calls) == 1
    request, metadata = hook.calls[0]
    assert request["intent"] == "animate"
    assert request["model_id"] == "doubao-seedance-2-0-260128"
    assert request["references"][0]["input_ref"] == "artifact:abc"
    assert metadata["cwd"] == str(tmp_path)


@pytest.mark.asyncio
async def test_generate_video_requires_saas_backend(tmp_path: Path) -> None:
    result = await GenerateVideoTool().execute(
        GenerateVideoInput(prompt="Create a product reveal video.", brief={}, output={}),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error
    assert result.metadata["media_billing_status"] == "skipped"
