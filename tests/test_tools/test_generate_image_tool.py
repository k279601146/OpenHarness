from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from openharness.engine.query import _format_tool_validation_error
from openharness.tools import create_default_tool_registry
from openharness.tools.base import ToolExecutionContext
from openharness.tools.generate_image_tool import GenerateImageInput, GenerateImageTool


class FakeImageHook:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict]] = []

    async def generate_image(self, request: dict, context_metadata: dict) -> dict:
        self.calls.append((request, context_metadata))
        return {
            "media_billing_status": "recorded",
            "artifact_payloads": [{"artifact_id": "artifact-1", "url": "/artifacts/thread/image.png"}],
        }


def test_default_registry_uses_generate_image_not_legacy_cli() -> None:
    registry = create_default_tool_registry()
    legacy_tool_name = "imagegen" + "_cli"

    assert registry.get("generate_image") is not None
    assert registry.get(legacy_tool_name) is None


def test_generate_image_schema_uses_high_level_fields() -> None:
    schema = GenerateImageTool().to_api_schema()["input_schema"]["properties"]

    assert "intent" in schema
    assert "scenario" in schema
    assert "brief" in schema
    assert "output" in schema
    assert "edit_policy" in schema
    assert "text_policy" in schema
    assert "references" in schema
    assert "model_id" in schema
    assert "purpose" not in schema
    assert "command" not in schema
    assert "provider" not in schema
    assert "aspect_ratio" not in schema
    assert "size" not in schema
    assert "resolution" not in schema
    assert "quality" not in schema
    assert "transparent_background" not in schema
    assert "output_count" not in schema


def test_generate_image_schema_rejects_provider_execution_fields() -> None:
    with pytest.raises(ValidationError):
        GenerateImageInput(
            prompt="Draw an image.",
            provider="gpt_image",
        )


def test_generate_image_rejects_json_string_brief() -> None:
    with pytest.raises(ValidationError):
        GenerateImageInput(
            prompt="Draw an image.",
            brief='{"purpose":"poster"}',
        )


def test_generate_image_validation_error_is_canonical() -> None:
    with pytest.raises(ValidationError) as exc:
        GenerateImageInput(
            prompt="Draw an image.",
            brief='{"purpose":"poster"}',
        )

    message = _format_tool_validation_error("generate_image", exc.value)

    assert message.startswith("invalid_canonical_request:")
    assert "`brief` must be an object" in message
    assert "pydantic.dev" not in message
    assert "ValidationError" not in message


@pytest.mark.asyncio
async def test_generate_image_delegates_to_backend_hook(tmp_path: Path) -> None:
    hook = FakeImageHook()
    tool = GenerateImageTool()

    result = await tool.execute(
        GenerateImageInput(
            intent="edit",
            prompt="Edit the referenced product image.",
            model_id="gpt-image-2",
            references=[{"input_ref": "artifact:abc", "role": "edit_target"}],
            output={"count": 1},
        ),
        ToolExecutionContext(cwd=tmp_path, metadata={"hook": hook, "tool_use_id": "tool-1"}),
    )

    assert not result.is_error
    assert result.metadata["media_billing_status"] == "recorded"
    assert result.metadata["delivery_required"] is False
    assert len(hook.calls) == 1
    request, metadata = hook.calls[0]
    assert request["intent"] == "edit"
    assert request["model_id"] == "gpt-image-2"
    assert request["references"][0]["input_ref"] == "artifact:abc"
    assert metadata["cwd"] == str(tmp_path)


@pytest.mark.asyncio
async def test_generate_image_requires_saas_backend(tmp_path: Path) -> None:
    result = await GenerateImageTool().execute(
        GenerateImageInput(prompt="Draw a product hero image."),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error
    assert result.metadata["media_billing_status"] == "skipped"
