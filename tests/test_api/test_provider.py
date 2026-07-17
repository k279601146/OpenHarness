"""Tests for provider capability helpers."""

from __future__ import annotations

import pytest

from openharness.api.provider import is_model_multimodal


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("claude-sonnet-4-6", True),
        ("claude-opus-4-6", True),
        ("claude-haiku-4-5", True),
        ("claude-3-5-sonnet-20241022", True),
        ("claude-3-opus-20240229", True),
        ("claude-3-haiku-20240307", True),
        ("gpt-4o", True),
        ("gpt-4o-mini", True),
        ("o1-mini", True),
        ("o3-mini", True),
        ("o4-mini", True),
        ("gpt-5.4", True),
        ("gemini-2.0-flash", True),
        ("gemini-pro-vision", True),
        ("qwen-vl-max", True),
        ("qwen2.5-vl-72b", True),
        ("qvq-72b-preview", True),
        ("deepseek-vl2", True),
        ("llava-v1.6-34b", True),
        ("pixtral-12b", True),
        ("step-2-16k", True),
        ("step-1v-32k", True),
        ("kimi-k2.5", True),
        ("claude-2.1", False),
        ("gpt-4", False),
        ("gpt-3.5-turbo", False),
        ("deepseek-chat", False),
        ("deepseek-reasoner", False),
        ("qwen-turbo", False),
        ("qwen-plus", False),
        ("kimi-k2", False),
        ("step-1-8k", False),
        ("glm-4", False),
        ("gemini-1.0-pro", False),
        ("unknown-model-123", False),
        ("", False),
        ("anthropic/claude-sonnet-4-6", True),
        ("openai/gpt-4o", True),
        ("openai/gpt-4", False),
    ],
)
def test_is_model_multimodal(model: str, expected: bool) -> None:
    assert is_model_multimodal(model) == expected
