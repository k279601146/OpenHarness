from __future__ import annotations

import pytest

from openharness.tools import create_default_tool_registry
from openharness.tools.ask_user_form_tool import AskUserFormTool, AskUserFormToolInput


def test_ask_user_form_tool_is_registered_and_exposed():
    registry = create_default_tool_registry()
    tool = registry.get("ask_user_form")

    assert isinstance(tool, AskUserFormTool)
    assert "ask_user_form" in {schema["name"] for schema in registry.to_api_schema()}


def test_ask_user_form_input_defaults_and_duplicate_ids():
    form = AskUserFormToolInput.model_validate(
        {
            "title": "Creative brief",
            "sections": [
                {
                    "id": "media",
                    "title": "Media",
                    "fields": [
                        {"id": "ratio", "label": "Aspect ratio", "type": "aspect_ratio"},
                        {"id": "reference", "label": "Reference", "type": "image_reference", "required": True},
                    ],
                }
            ],
        }
    )

    assert [option.label for option in form.sections[0].fields[0].options] == [
        "1:1",
        "4:5",
        "9:16",
        "16:9",
        "21:9",
    ]
    constraints = form.sections[0].fields[1].file_constraints
    assert constraints is not None
    assert constraints.allowed_mime_types == ["image/*"]

    with pytest.raises(ValueError, match="duplicate field id"):
        AskUserFormToolInput.model_validate(
            {
                "title": "Creative brief",
                "sections": [
                    {
                        "id": "media",
                        "title": "Media",
                        "fields": [
                            {"id": "ratio", "label": "Aspect ratio", "type": "aspect_ratio"},
                            {"id": "ratio", "label": "Duplicate", "type": "text"},
                        ],
                    }
                ],
            }
        )


def test_ask_user_form_select_can_accept_custom_input():
    form = AskUserFormToolInput.model_validate(
        {
            "title": "Creative brief",
            "sections": [
                {
                    "id": "market",
                    "title": "Market",
                    "fields": [
                        {
                            "id": "market_language",
                            "label": "Market and language",
                            "type": "select",
                            "allow_custom": True,
                            "custom_placeholder": "Enter another market",
                            "default_value": "Latin America / Spanish",
                            "options": [{"label": "US / English", "value": "us_en"}],
                        }
                    ],
                }
            ],
        }
    )

    field = form.sections[0].fields[0]
    assert field.allow_custom is True
    assert field.custom_placeholder == "Enter another market"
    assert field.default_value == "Latin America / Spanish"
