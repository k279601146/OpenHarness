"""Tests for the OpenAI-compatible API client."""

from __future__ import annotations

import json

import httpx

import pytest
from openai import APITimeoutError

import openharness.api.openai_client as openai_client_module
from openharness.api.client import (
    ApiMessageRequest,
    ApiRetryEvent,
    ApiToolCallCompletedEvent,
    ApiToolCallProgressEvent,
    ApiToolCallStartedEvent,
)
from openharness.api.openai_client import (
    OpenAICompatibleClient,
    _convert_assistant_message,
    _convert_messages_to_openai,
    _convert_messages_to_responses_input,
    _convert_tools_to_responses,
    _convert_tools_to_openai,
    _normalize_openai_base_url,
    _looks_like_prompt_cache_unsupported,
    _looks_like_service_tier_unsupported,
    _prompt_cache_params_for_request,
    _reasoning_effort_param_for_model,
    _responses_reasoning_param_for_model,
    _service_tier_param,
    _strip_service_tier_param,
    _strip_prompt_cache_params,
    _usage_snapshot_from_openai_usage,
    _strip_think_blocks,
    _token_limit_param_for_model,
)
from openharness.api.errors import AuthenticationFailure, RateLimitFailure, RequestFailure
from openharness.engine.messages import (
    ConversationMessage,
    ImageBlock,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


class TestConvertToolsToOpenai:
    """Test Anthropic → OpenAI tool schema conversion."""

    def test_basic_tool(self):
        anthropic_tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                    },
                    "required": ["path"],
                },
            }
        ]
        result = _convert_tools_to_openai(anthropic_tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "read_file"
        assert result[0]["function"]["description"] == "Read a file"
        assert result[0]["function"]["parameters"]["properties"]["path"]["type"] == "string"

    def test_empty_tools(self):
        assert _convert_tools_to_openai([]) == []

    def test_multiple_tools(self):
        tools = [
            {"name": "tool_a", "description": "A", "input_schema": {}},
            {"name": "tool_b", "description": "B", "input_schema": {}},
        ]
        result = _convert_tools_to_openai(tools)
        assert len(result) == 2
        assert result[0]["function"]["name"] == "tool_a"
        assert result[1]["function"]["name"] == "tool_b"

    def test_responses_tool_schema(self):
        result = _convert_tools_to_responses([
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {"type": "object", "properties": {}},
            }
        ])

        assert result == [
            {
                "type": "function",
                "name": "read_file",
                "description": "Read a file",
                "parameters": {"type": "object", "properties": {}},
            }
        ]


class TestConvertMessagesToOpenai:
    """Test Anthropic → OpenAI message format conversion."""

    def test_system_prompt(self):
        messages: list[ConversationMessage] = []
        result = _convert_messages_to_openai(messages, "You are helpful.")
        assert len(result) == 1
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are helpful."

    def test_no_system_prompt(self):
        messages = [ConversationMessage.from_user_text("hi")]
        result = _convert_messages_to_openai(messages, None)
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "hi"

    def test_user_text_message(self):
        messages = [ConversationMessage.from_user_text("hello")]
        result = _convert_messages_to_openai(messages, None)
        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "hello"}

    def test_user_multimodal_message(self):
        messages = [
            ConversationMessage(
                role="user",
                content=[
                    TextBlock(text="Please describe this image."),
                    ImageBlock(media_type="image/png", data="YWJj", source_path="/tmp/example.png"),
                ],
            )
        ]
        result = _convert_messages_to_openai(messages, None)
        assert result[0]["role"] == "user"
        assert isinstance(result[0]["content"], list)
        assert result[0]["content"][0] == {"type": "text", "text": "Please describe this image."}
        assert result[0]["content"][1] == {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,YWJj"},
        }

    def test_assistant_text_message(self):
        msg = ConversationMessage(
            role="assistant", content=[TextBlock(text="I'll help you.")]
        )
        result = _convert_messages_to_openai([msg], None)
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "I'll help you."
        assert "tool_calls" not in result[0]

    def test_assistant_with_tool_calls(self):
        msg = ConversationMessage(
            role="assistant",
            content=[
                TextBlock(text="Let me read that file."),
                ToolUseBlock(id="call_1", name="read_file", input={"path": "/tmp/x"}),
            ],
        )
        result = _convert_messages_to_openai([msg], None)
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Let me read that file."
        assert len(result[0]["tool_calls"]) == 1
        tc = result[0]["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "read_file"
        assert json.loads(tc["function"]["arguments"]) == {"path": "/tmp/x"}

    def test_tool_result_messages(self):
        # User message containing tool results
        msg = ConversationMessage(
            role="user",
            content=[
                ToolResultBlock(
                    tool_use_id="call_1", content="file contents here", is_error=False
                ),
            ],
        )
        result = _convert_messages_to_openai([msg], None)
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call_1"
        assert result[0]["content"] == "file contents here"

    def test_full_conversation_round_trip(self):
        """Test a complete user → assistant(tool_call) → user(tool_result) → assistant flow."""
        messages = [
            ConversationMessage.from_user_text("Read /tmp/test.txt"),
            ConversationMessage(
                role="assistant",
                content=[
                    TextBlock(text="I'll read that."),
                    ToolUseBlock(
                        id="call_abc", name="read_file", input={"path": "/tmp/test.txt"}
                    ),
                ],
            ),
            ConversationMessage(
                role="user",
                content=[
                    ToolResultBlock(
                        tool_use_id="call_abc", content="hello world", is_error=False
                    )
                ],
            ),
            ConversationMessage(
                role="assistant",
                content=[TextBlock(text="The file contains: hello world")],
            ),
        ]
        result = _convert_messages_to_openai(messages, "Be helpful")
        assert result[0] == {"role": "system", "content": "Be helpful"}
        assert result[1] == {"role": "user", "content": "Read /tmp/test.txt"}
        assert result[2]["role"] == "assistant"
        assert len(result[2]["tool_calls"]) == 1
        assert result[3]["role"] == "tool"
        assert result[3]["tool_call_id"] == "call_abc"
        assert result[4]["role"] == "assistant"
        assert result[4]["content"] == "The file contains: hello world"

    def test_multiple_tool_results(self):
        msg = ConversationMessage(
            role="user",
            content=[
                ToolResultBlock(tool_use_id="c1", content="result1", is_error=False),
                ToolResultBlock(tool_use_id="c2", content="result2", is_error=True),
            ],
        )
        result = _convert_messages_to_openai([msg], None)
        assert len(result) == 2
        assert result[0]["tool_call_id"] == "c1"
        assert result[1]["tool_call_id"] == "c2"

    def test_responses_input_with_tool_round_trip(self):
        messages = [
            ConversationMessage.from_user_text("Read /tmp/test.txt"),
            ConversationMessage(
                role="assistant",
                content=[
                    TextBlock(text="I'll read that."),
                    ToolUseBlock(id="call_abc", name="read_file", input={"path": "/tmp/test.txt"}),
                ],
            ),
            ConversationMessage(
                role="user",
                content=[ToolResultBlock(tool_use_id="call_abc", content="hello world")],
            ),
        ]

        result = _convert_messages_to_responses_input(messages)

        assert result[0] == {
            "role": "user",
            "content": [{"type": "input_text", "text": "Read /tmp/test.txt"}],
        }
        assert result[1] == {
            "role": "assistant",
            "content": [{"type": "output_text", "text": "I'll read that."}],
        }
        assert result[2]["type"] == "function_call"
        assert result[2]["call_id"] == "call_abc"
        assert result[2]["name"] == "read_file"
        assert json.loads(result[2]["arguments"]) == {"path": "/tmp/test.txt"}
        assert result[3] == {
            "type": "function_call_output",
            "call_id": "call_abc",
            "output": "hello world",
        }


class TestNormalizeOpenAIBaseUrl:
    def test_preserves_explicit_v1_path(self):
        assert _normalize_openai_base_url("https://jarodfund.xyz/openai/v1") == "https://jarodfund.xyz/openai/v1"

    def test_adds_default_v1_when_path_missing(self):
        assert _normalize_openai_base_url("https://api.example.com") == "https://api.example.com/v1"

    def test_strips_trailing_slash_without_dropping_path(self):
        assert _normalize_openai_base_url("https://api.example.com/openai/v1/") == "https://api.example.com/openai/v1"


class TestTokenLimitParams:
    def test_gpt5_uses_max_completion_tokens(self):
        assert _token_limit_param_for_model("gpt-5.4", 4096) == {"max_completion_tokens": 4096}

    def test_legacy_chat_models_keep_max_tokens(self):
        assert _token_limit_param_for_model("gpt-4o", 4096) == {"max_tokens": 4096}


class TestReasoningEffortParams:
    def test_gpt5_defaults_to_low_reasoning_effort(self):
        assert _reasoning_effort_param_for_model("gpt-5.4", None) == {"reasoning_effort": "low"}

    def test_gpt5_passes_supported_reasoning_effort(self):
        assert _reasoning_effort_param_for_model("gpt-5.4", "medium") == {"reasoning_effort": "medium"}

    def test_gpt5_chat_allows_none_reasoning_effort(self):
        assert _reasoning_effort_param_for_model("gpt-5.4", "none") == {"reasoning_effort": "none"}

    def test_gpt5_maps_xhigh_to_high_for_chat_completions(self):
        assert _reasoning_effort_param_for_model("gpt-5.4", "xhigh") == {"reasoning_effort": "high"}

    def test_legacy_chat_models_omit_reasoning_effort(self):
        assert _reasoning_effort_param_for_model("gpt-4o", "low") == {}

    def test_responses_reasoning_shape(self):
        assert _responses_reasoning_param_for_model("gpt-5.4", "medium") == {
            "reasoning": {"effort": "medium"}
        }

    def test_responses_reasoning_allows_minimal(self):
        assert _responses_reasoning_param_for_model("gpt-5.4", "minimal") == {
            "reasoning": {"effort": "minimal"}
        }

    def test_responses_reasoning_allows_none_and_xhigh(self):
        assert _responses_reasoning_param_for_model("gpt-5.5", "none") == {
            "reasoning": {"effort": "none"}
        }
        assert _responses_reasoning_param_for_model("gpt-5.5", "xhigh") == {
            "reasoning": {"effort": "xhigh"}
        }


class _FakeUsage:
    prompt_tokens = 11
    completion_tokens = 7


class _FakeChunk:
    def __init__(self) -> None:
        self.choices = []
        self.usage = _FakeUsage()


class TestOpenAIUsageParsing:
    def test_parses_cached_tokens_from_prompt_details_object(self):
        class _PromptDetails:
            cached_tokens = 8

        class _Usage:
            prompt_tokens = 20
            completion_tokens = 4
            prompt_tokens_details = _PromptDetails()

        usage = _usage_snapshot_from_openai_usage(_Usage())

        assert usage.input_tokens == 20
        assert usage.output_tokens == 4
        assert usage.cache_read_input_tokens == 8

    def test_parses_cached_tokens_from_dict_usage(self):
        usage = _usage_snapshot_from_openai_usage(
            {
                "prompt_tokens": 20,
                "completion_tokens": 4,
                "prompt_tokens_details": {
                    "cached_tokens": 8,
                    "cache_creation_tokens": 12,
                },
            }
        )

        assert usage.input_tokens == 20
        assert usage.output_tokens == 4
        assert usage.cache_read_input_tokens == 8
        assert usage.cache_creation_input_tokens == 12


class TestOpenAIPromptCaching:
    def test_builds_stable_prompt_cache_params_for_gpt5(self, monkeypatch):
        monkeypatch.delenv("OPENHARNESS_OPENAI_DISABLE_PROMPT_CACHE", raising=False)
        monkeypatch.delenv("OPENHARNESS_OPENAI_PROMPT_CACHE_KEY", raising=False)
        monkeypatch.delenv("OPENHARNESS_OPENAI_PROMPT_CACHE_RETENTION", raising=False)

        tools = [{"type": "function", "name": "read_file", "description": "Read a file"}]
        first = _prompt_cache_params_for_request(model="gpt-5.5", instructions="static prompt", tools=tools)
        second = _prompt_cache_params_for_request(model="gpt-5.5", instructions="static prompt", tools=tools)

        assert first == second
        assert first["prompt_cache_key"].startswith("openharness:gpt-5.5:")
        assert first["prompt_cache_retention"] == "24h"

    def test_prompt_cache_env_overrides(self, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_OPENAI_PROMPT_CACHE_KEY", "shared-agent-prefix")
        monkeypatch.setenv("OPENHARNESS_OPENAI_PROMPT_CACHE_RETENTION", "off")

        params = _prompt_cache_params_for_request(model="gpt-5.5", instructions="static prompt", tools=[])

        assert params == {"prompt_cache_key": "shared-agent-prefix"}

    def test_prompt_cache_can_be_disabled(self, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_OPENAI_DISABLE_PROMPT_CACHE", "true")

        assert _prompt_cache_params_for_request(model="gpt-5.5", instructions="static prompt", tools=[]) == {}

    def test_strip_prompt_cache_params(self):
        params = {"model": "gpt-5.5", "prompt_cache_key": "x", "prompt_cache_retention": "24h"}

        assert _strip_prompt_cache_params(params) is True
        assert params == {"model": "gpt-5.5"}

    def test_detects_prompt_cache_unsupported_error(self):
        exc = ValueError("Unknown parameter: prompt_cache_retention")

        assert _looks_like_prompt_cache_unsupported(exc)


class TestOpenAIServiceTier:
    def test_service_tier_env_param(self, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_OPENAI_SERVICE_TIER", "priority")

        assert _service_tier_param() == {"service_tier": "priority"}

    def test_strip_service_tier_param(self):
        params = {"model": "gpt-5.5", "service_tier": "priority"}

        assert _strip_service_tier_param(params) is True
        assert params == {"model": "gpt-5.5"}

    def test_detects_service_tier_unsupported_error(self):
        exc = ValueError("Unknown parameter: service_tier")

        assert _looks_like_service_tier_unsupported(exc)


class _FakeResponses:
    def __init__(self, events: list[dict[str, object]] | None = None) -> None:
        self.last_kwargs: dict[str, object] | None = None
        self.events = events

    async def create(self, **kwargs):
        self.last_kwargs = kwargs

        async def _stream():
            if self.events is not None:
                for event in self.events:
                    yield event
            else:
                yield {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    },
                }

        return _stream()


class _FakeOpenAIClient:
    def __init__(self, events: list[dict[str, object]] | None = None) -> None:
        self.responses = _FakeResponses(events)


@pytest.mark.asyncio
async def test_responses_empty_stream_falls_back_to_non_stream():
    class _FallbackResponses:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("stream"):
                async def _empty_stream():
                    if False:
                        yield {}

                return _empty_stream()

            return {
                "status": "completed",
                "usage": {"input_tokens": 2, "output_tokens": 3},
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "hello"}],
                    }
                ],
            }

    class _FallbackClient:
        def __init__(self) -> None:
            self.responses = _FallbackResponses()

    client = OpenAICompatibleClient(api_key="test-key")
    fake_sdk = _FallbackClient()
    client._client = fake_sdk

    request = ApiMessageRequest(
        model="gpt-5.5",
        messages=[ConversationMessage.from_user_text("Say hi")],
    )

    events = [event async for event in client.stream_message(request)]

    assert [call["stream"] for call in fake_sdk.responses.calls] == [True, False]
    assert events[0].text == "hello"
    assert events[-1].message.text == "hello"
    assert events[-1].usage.input_tokens == 2
    assert events[-1].usage.output_tokens == 3


@pytest.mark.asyncio
async def test_openai_client_uses_full_base_url_path_for_requests():
    seen_urls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "gpt-4o-mini",
                "choices": [],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    transport = httpx.MockTransport(_handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://jarodfund.xyz/openai/v1",
    )
    client._client._client = http_client

    request = ApiMessageRequest(
        model="gpt-4o-mini",
        messages=[ConversationMessage.from_user_text("Explain the codebase")],
    )
    events = [event async for event in client.stream_message(request)]

    assert events
    assert seen_urls
    assert all(url == "https://jarodfund.xyz/openai/v1/responses" for url in seen_urls)
    await http_client.aclose()


def test_openai_client_init_normalizes_base_url(monkeypatch):
    captured: dict[str, object] = {}

    class _StubAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openharness.api.openai_client.AsyncOpenAI", _StubAsyncOpenAI)
    OpenAICompatibleClient(api_key="test-key", base_url="https://jarodfund.xyz/openai/v1/")

    assert captured["base_url"] == "https://jarodfund.xyz/openai/v1"


def test_openai_client_init_passes_timeout(monkeypatch):
    captured: dict[str, object] = {}

    class _StubAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openharness.api.openai_client.AsyncOpenAI", _StubAsyncOpenAI)
    OpenAICompatibleClient(api_key="test-key", timeout=45.0)

    assert captured["timeout"] == 45.0


def test_openai_client_uses_bearer_authorization_header():
    client = OpenAICompatibleClient(api_key="test-key", base_url="https://example.com/v1")

    assert client._client.default_headers["Authorization"] == "Bearer test-key"


def test_openai_client_overrides_sdk_user_agent():
    client = OpenAICompatibleClient(api_key="test-key", base_url="https://example.com/v1")

    assert client._client.default_headers["User-Agent"] == "OpenHarness/1.0"


@pytest.mark.asyncio
async def test_openai_client_aclose_closes_underlying_sdk_client():
    class _StubAsyncOpenAI:
        def __init__(self, **kwargs):
            self.closed = False

        async def close(self):
            self.closed = True

    client = OpenAICompatibleClient(api_key="test-key")
    client._client = _StubAsyncOpenAI()

    await client.aclose()

    assert client._client.closed is True


@pytest.mark.asyncio
async def test_openai_client_retries_openai_sdk_timeout(monkeypatch):
    class _TimeoutThenSuccessResponses:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                request = httpx.Request("POST", "https://example.com/v1/responses")
                raise APITimeoutError(request)

            async def _stream():
                yield {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    },
                }

            return _stream()

    class _TimeoutThenSuccessClient:
        def __init__(self) -> None:
            self.responses = _TimeoutThenSuccessResponses()

    monkeypatch.setattr(openai_client_module, "MAX_RETRIES", 1)
    monkeypatch.setattr(openai_client_module, "BASE_DELAY", 0)

    client = OpenAICompatibleClient(api_key="test-key", base_url="https://example.com/v1")
    fake_sdk = _TimeoutThenSuccessClient()
    client._client = fake_sdk

    request = ApiMessageRequest(
        model="gpt-5.4",
        messages=[ConversationMessage.from_user_text("Say hi")],
    )

    events = [event async for event in client.stream_message(request)]

    assert fake_sdk.responses.calls == 2
    assert any(isinstance(event, ApiRetryEvent) for event in events)



class TestStreamMessageTokenParams:
    @pytest.mark.asyncio
    async def test_stream_uses_responses_max_output_tokens(self):
        client = OpenAICompatibleClient(api_key="test-key")
        fake_sdk = _FakeOpenAIClient()
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-5.4",
            messages=[ConversationMessage.from_user_text("Explain the codebase")],
        )

        events = [event async for event in client.stream_message(request)]

        assert events
        assert fake_sdk.responses.last_kwargs is not None
        assert fake_sdk.responses.last_kwargs["max_output_tokens"] == 4096
        assert "max_completion_tokens" not in fake_sdk.responses.last_kwargs
        assert "max_tokens" not in fake_sdk.responses.last_kwargs

    @pytest.mark.asyncio
    async def test_gpt5_stream_includes_responses_reasoning(self):
        client = OpenAICompatibleClient(api_key="test-key")
        fake_sdk = _FakeOpenAIClient()
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-5.4",
            messages=[ConversationMessage.from_user_text("Explain the codebase")],
            effort="medium",
        )

        events = [event async for event in client.stream_message(request)]

        assert events
        assert fake_sdk.responses.last_kwargs is not None
        assert fake_sdk.responses.last_kwargs["reasoning"] == {"effort": "medium"}

    @pytest.mark.asyncio
    async def test_gpt5_stream_includes_prompt_cache_params(self, monkeypatch):
        monkeypatch.delenv("OPENHARNESS_OPENAI_DISABLE_PROMPT_CACHE", raising=False)
        monkeypatch.delenv("OPENHARNESS_OPENAI_PROMPT_CACHE_KEY", raising=False)
        monkeypatch.delenv("OPENHARNESS_OPENAI_PROMPT_CACHE_RETENTION", raising=False)
        client = OpenAICompatibleClient(api_key="test-key")
        fake_sdk = _FakeOpenAIClient()
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-5.5",
            messages=[ConversationMessage.from_user_text("Explain the codebase")],
            system_prompt="static prompt",
        )

        events = [event async for event in client.stream_message(request)]

        assert events
        assert fake_sdk.responses.last_kwargs is not None
        assert fake_sdk.responses.last_kwargs["prompt_cache_key"].startswith("openharness:gpt-5.5:")
        assert fake_sdk.responses.last_kwargs["prompt_cache_retention"] == "24h"

    @pytest.mark.asyncio
    async def test_stream_uses_responses_tool_schema(self):
        client = OpenAICompatibleClient(api_key="test-key")
        fake_sdk = _FakeOpenAIClient()
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-5.4",
            messages=[ConversationMessage.from_user_text("Read a file")],
            tools=[
                {
                    "name": "read_file",
                    "description": "Read a file",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
        )

        events = [event async for event in client.stream_message(request)]

        assert events
        assert fake_sdk.responses.last_kwargs is not None
        assert fake_sdk.responses.last_kwargs["tools"][0]["type"] == "function"
        assert fake_sdk.responses.last_kwargs["tools"][0]["name"] == "read_file"
        assert fake_sdk.responses.last_kwargs["tool_choice"] == "auto"
        assert fake_sdk.responses.last_kwargs["parallel_tool_calls"] is True

    @pytest.mark.asyncio
    async def test_stream_collects_responses_tool_argument_events(self):
        client = OpenAICompatibleClient(api_key="test-key")
        fake_sdk = _FakeOpenAIClient([
            {
                "type": "response.output_item.added",
                "item": {
                    "id": "fc_1",
                    "type": "function_call",
                    "arguments": "",
                    "call_id": "call_abc",
                    "name": "bash",
                },
            },
            {
                "type": "response.function_call_arguments.delta",
                "item_id": "fc_1",
                "delta": '{"command":',
            },
            {
                "type": "response.function_call_arguments.delta",
                "item_id": "fc_1",
                "delta": '"echo hi"}',
            },
            {
                "type": "response.output_item.done",
                "item": {
                    "id": "fc_1",
                    "type": "function_call",
                    "arguments": "",
                    "call_id": "call_abc",
                    "name": "bash",
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            },
        ])
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-5.4",
            messages=[ConversationMessage.from_user_text("Run a command")],
            tools=[
                {
                    "name": "bash",
                    "description": "Run shell",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
        )

        events = [event async for event in client.stream_message(request)]

        complete = events[-1]
        assert complete.message.tool_uses[0].input == {"command": "echo hi"}

    @pytest.mark.asyncio
    async def test_stream_collects_tool_arguments_by_output_index(self):
        client = OpenAICompatibleClient(api_key="test-key")
        fake_sdk = _FakeOpenAIClient([
            {
                "type": "response.function_call_arguments.delta",
                "output_index": 0,
                "delta": '{"query":"weather"}',
            },
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": {
                    "id": "fc_1",
                    "type": "function_call",
                    "arguments": "",
                    "call_id": "call_abc",
                    "name": "web_search",
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            },
        ])
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-5.4",
            messages=[ConversationMessage.from_user_text("Search")],
            tools=[{"name": "web_search", "description": "Search", "input_schema": {"type": "object"}}],
        )

        events = [event async for event in client.stream_message(request)]

        complete = events[-1]
        assert complete.message.tool_uses[0].input == {"query": "weather"}

    @pytest.mark.asyncio
    async def test_gpt4o_stream_omits_reasoning(self):
        client = OpenAICompatibleClient(api_key="test-key")
        fake_sdk = _FakeOpenAIClient()
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-4o",
            messages=[ConversationMessage.from_user_text("Explain the codebase")],
        )

        events = [event async for event in client.stream_message(request)]

        assert events
        assert fake_sdk.responses.last_kwargs is not None
        assert "reasoning" not in fake_sdk.responses.last_kwargs
        assert fake_sdk.responses.last_kwargs["max_output_tokens"] == 4096

    @pytest.mark.asyncio
    async def test_local_proxy_uses_responses_with_hosted_search_first(self):
        client = OpenAICompatibleClient(api_key="test-key", base_url="http://localhost:3000/v1")
        fake_sdk = _FakeOpenAIClient([
            {
                "type": "response.output_item.done",
                "item": {"type": "function_call", "call_id": "call_abc", "name": "web_search"},
            },
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call_abc",
                "arguments": '{"query":"today AI news"}',
            },
            {
                "type": "response.completed",
                "response": {"status": "completed", "usage": {"input_tokens": 5, "output_tokens": 3}},
            },
        ])
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-5.5",
            messages=[ConversationMessage.from_user_text("Search")],
            tools=[
                {
                    "name": "web_search",
                    "description": "Search",
                    "input_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                }
            ],
        )

        events = [event async for event in client.stream_message(request)]

        complete = events[-1]
        assert complete.message.tool_uses[0].input == {"query": "today AI news"}
        assert fake_sdk.responses.last_kwargs["tools"] == [{"type": "web_search"}]

    @pytest.mark.asyncio
    async def test_hosted_web_search_create_failure_falls_back_to_local_function(self):
        class _UnsupportedWebSearchError(Exception):
            status_code = 400
            body = {"error": {"message": "Unsupported tool type web_search"}}

        class _FallbackResponses:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def create(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    raise _UnsupportedWebSearchError("unsupported web_search")

                async def _stream():
                    yield {
                        "type": "response.output_item.done",
                        "item": {"type": "function_call", "call_id": "call_abc", "name": "web_search"},
                    }
                    yield {
                        "type": "response.function_call_arguments.done",
                        "call_id": "call_abc",
                        "arguments": '{"query":"fallback"}',
                    }
                    yield {
                        "type": "response.completed",
                        "response": {"status": "completed", "usage": {"input_tokens": 5, "output_tokens": 3}},
                    }

                return _stream()

        class _FallbackClient:
            def __init__(self) -> None:
                self.responses = _FallbackResponses()

        client = OpenAICompatibleClient(api_key="test-key", base_url="http://localhost:3000/v1")
        fake_sdk = _FallbackClient()
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-5.5",
            messages=[ConversationMessage.from_user_text("Search")],
            tools=[
                {
                    "name": "web_search",
                    "description": "Search",
                    "input_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                }
            ],
        )

        events = [event async for event in client.stream_message(request)]

        complete = events[-1]
        assert complete.message.tool_uses[0].input == {"query": "fallback"}
        assert fake_sdk.responses.calls[0]["tools"][0] == {"type": "web_search"}
        assert all(tool.get("type") != "web_search" for tool in fake_sdk.responses.calls[1]["tools"])
        assert fake_sdk.responses.calls[1]["tools"][0]["name"] == "web_search"

    @pytest.mark.asyncio
    async def test_stream_translates_hosted_web_search_events(self):
        client = OpenAICompatibleClient(api_key="test-key", base_url="http://localhost:3000/v1")
        fake_sdk = _FakeOpenAIClient([
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "id": "ws_1",
                    "type": "web_search_call",
                    "status": "in_progress",
                    "action": {"query": "today AI news"},
                },
            },
            {"type": "response.web_search_call.searching", "item_id": "ws_1"},
            {
                "type": "response.web_search_call.completed",
                "item_id": "ws_1",
                "results": [
                    {"title": "AI News", "url": "https://example.com/news", "snippet": "not persisted"},
                    {"title": "OpenAI", "url": "https://example.com/openai"},
                ],
            },
            {
                "type": "response.completed",
                "response": {"status": "completed", "usage": {"input_tokens": 5, "output_tokens": 3}},
            },
        ])
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-5.5",
            messages=[ConversationMessage.from_user_text("Search")],
            tools=[{"name": "web_search", "description": "Search", "input_schema": {"type": "object"}}],
        )

        events = [event async for event in client.stream_message(request)]

        starts = [event for event in events if isinstance(event, ApiToolCallStartedEvent)]
        progresses = [event for event in events if isinstance(event, ApiToolCallProgressEvent)]
        completes = [event for event in events if isinstance(event, ApiToolCallCompletedEvent)]

        assert len(starts) == 1
        assert starts[0].tool_name == "web_search"
        assert starts[0].tool_use_id == "ws_1"
        assert starts[0].tool_input == {"query": "today AI news"}
        assert any(event.message == "正在搜索网页..." for event in progresses)
        assert len(completes) == 1
        assert completes[0].tool_name == "web_search"
        assert completes[0].status == "success"
        assert completes[0].metadata["result_count"] == 2
        assert completes[0].metadata["results"] == [
            {"title": "AI News", "url": "https://example.com/news"},
            {"title": "OpenAI", "url": "https://example.com/openai"},
        ]
        assert "snippet" not in json.dumps(completes[0].metadata)
        assert events[-1].message.tool_uses == []

    @pytest.mark.asyncio
    async def test_stream_translates_hosted_non_function_tools_without_local_tool_calls(self):
        client = OpenAICompatibleClient(api_key="test-key", base_url="http://localhost:3000/v1")
        fake_sdk = _FakeOpenAIClient([
            {"type": "response.file_search_call.searching", "item_id": "fs_1"},
            {
                "type": "response.output_item.done",
                "item": {"id": "fs_1", "type": "file_search_call", "status": "completed"},
            },
            {"type": "response.code_interpreter_call.in_progress", "item_id": "ci_1"},
            {"type": "response.code_interpreter_call.interpreting", "item_id": "ci_1"},
            {"type": "response.mcp_call.in_progress", "item_id": "mcp_1"},
            {"type": "response.mcp_call.failed", "item_id": "mcp_1"},
            {
                "type": "response.completed",
                "response": {"status": "completed", "usage": {"input_tokens": 5, "output_tokens": 3}},
            },
        ])
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-5.5",
            messages=[ConversationMessage.from_user_text("Use hosted tools")],
        )

        events = [event async for event in client.stream_message(request)]

        starts = [event for event in events if isinstance(event, ApiToolCallStartedEvent)]
        completes = [event for event in events if isinstance(event, ApiToolCallCompletedEvent)]

        assert {event.tool_name for event in starts} == {"file_search", "code_interpreter", "mcp_call"}
        assert any(event.tool_name == "file_search" and event.status == "success" for event in completes)
        assert any(event.tool_name == "mcp_call" and event.status == "error" for event in completes)
        assert events[-1].message.tool_uses == []

    @pytest.mark.asyncio
    async def test_stream_observes_unknown_response_events_without_payload_leak(self, caplog):
        client = OpenAICompatibleClient(api_key="test-key", base_url="http://localhost:3000/v1")
        fake_sdk = _FakeOpenAIClient([
            {
                "type": "response.future_tool.secret",
                "item_id": "future_1",
                "output_index": 7,
                "secret_payload": "do-not-log-this",
            },
            {
                "type": "response.completed",
                "response": {"status": "completed", "usage": {"input_tokens": 5, "output_tokens": 3}},
            },
        ])
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="gpt-5.5",
            messages=[ConversationMessage.from_user_text("Unknown event")],
        )

        with caplog.at_level("INFO"):
            events = [event async for event in client.stream_message(request)]

        assert events[-1].message.tool_uses == []
        assert "response.future_tool.secret" in caplog.text
        assert "future_1" in caplog.text
        assert "do-not-log-this" not in caplog.text

    @pytest.mark.asyncio
    async def test_responses_endpoint_unsupported_falls_back_to_chat_stream(self):
        class _ResponsesNotFound(Exception):
            status_code = 404
            body = {"error": {"message": "NOT_FOUND"}}

        class _FallbackResponses:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def create(self, **kwargs):
                self.calls.append(kwargs)
                raise _ResponsesNotFound("responses endpoint not found")

        class _FallbackChatCompletions:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def create(self, **kwargs):
                self.calls.append(kwargs)

                async def _stream():
                    yield {
                        "id": "chatcmpl_fallback",
                        "choices": [{"delta": {"content": "hello"}, "finish_reason": None}],
                    }
                    yield {
                        "id": "chatcmpl_fallback",
                        "choices": [{"delta": {}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 2, "completion_tokens": 3},
                    }

                return _stream()

        class _FallbackChat:
            def __init__(self) -> None:
                self.completions = _FallbackChatCompletions()

        class _FallbackClient:
            def __init__(self) -> None:
                self.responses = _FallbackResponses()
                self.chat = _FallbackChat()

        client = OpenAICompatibleClient(api_key="test-key", base_url="http://localhost:3000/v1")
        fake_sdk = _FallbackClient()
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="deepseek-v4-flash",
            messages=[ConversationMessage.from_user_text("Say hi")],
            tools=[{"name": "bash", "description": "Run shell", "input_schema": {"type": "object"}}],
        )

        events = [event async for event in client.stream_message(request)]

        complete = events[-1]
        assert complete.message.text == "hello"
        assert complete.usage.input_tokens == 2
        assert complete.usage.output_tokens == 3
        assert fake_sdk.responses.calls[0]["input"][0]["content"][0]["text"] == "Say hi"
        assert fake_sdk.chat.completions.calls[0]["messages"] == [{"role": "user", "content": "Say hi"}]
        assert fake_sdk.chat.completions.calls[0]["tools"][0]["function"]["name"] == "bash"
        assert fake_sdk.chat.completions.calls[0]["stream_options"] == {"include_usage": True}

    @pytest.mark.asyncio
    async def test_responses_model_not_found_does_not_fallback_to_chat_stream(self):
        class _ModelNotFound(Exception):
            status_code = 400
            body = {"error": {"code": "model_not_found", "message": "model not found"}}

        class _ResponsesModelNotFound:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def create(self, **kwargs):
                self.calls.append(kwargs)
                raise _ModelNotFound("model_not_found: model not found")

        class _UnexpectedChatCompletions:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def create(self, **kwargs):
                self.calls.append(kwargs)
                raise AssertionError("chat fallback should not be called for model_not_found")

        class _UnexpectedChat:
            def __init__(self) -> None:
                self.completions = _UnexpectedChatCompletions()

        class _FallbackClient:
            def __init__(self) -> None:
                self.responses = _ResponsesModelNotFound()
                self.chat = _UnexpectedChat()

        client = OpenAICompatibleClient(api_key="test-key", base_url="http://localhost:3000/v1")
        fake_sdk = _FallbackClient()
        client._client = fake_sdk

        request = ApiMessageRequest(
            model="missing-model",
            messages=[ConversationMessage.from_user_text("Say hi")],
        )

        with pytest.raises(RequestFailure):
            [event async for event in client.stream_message(request)]

        assert len(fake_sdk.responses.calls) == 1
        assert fake_sdk.chat.completions.calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [401, 429])
    async def test_chat_stream_options_text_does_not_retry_on_auth_or_rate_limit(self, monkeypatch, status_code):
        class _ResponsesNotFound(Exception):
            status_code = 404
            body = {"error": {"message": "responses endpoint not found"}}

        class _ChatStreamOptionsError(Exception):
            def __init__(self, code: int) -> None:
                self.status_code = code
                self.body = {"error": {"message": "stream_options unsupported but request is not retryable"}}
                super().__init__("stream_options unsupported but request is not retryable")

        class _FallbackResponses:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def create(self, **kwargs):
                self.calls.append(kwargs)
                raise _ResponsesNotFound("responses endpoint not found")

        class _FallbackChatCompletions:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def create(self, **kwargs):
                self.calls.append(kwargs)
                raise _ChatStreamOptionsError(status_code)

        class _FallbackChat:
            def __init__(self) -> None:
                self.completions = _FallbackChatCompletions()

        class _FallbackClient:
            def __init__(self) -> None:
                self.responses = _FallbackResponses()
                self.chat = _FallbackChat()

        client = OpenAICompatibleClient(api_key="test-key", base_url="http://localhost:3000/v1")
        fake_sdk = _FallbackClient()
        client._client = fake_sdk
        monkeypatch.setattr(OpenAICompatibleClient, "_is_retryable", staticmethod(lambda exc: False))

        request = ApiMessageRequest(
            model="deepseek-v4-flash",
            messages=[ConversationMessage.from_user_text("Say hi")],
        )

        expected_error = AuthenticationFailure if status_code == 401 else RateLimitFailure
        with pytest.raises(expected_error):
            [event async for event in client.stream_message(request)]

        assert len(fake_sdk.responses.calls) == 1
        assert len(fake_sdk.chat.completions.calls) == 1
        assert fake_sdk.chat.completions.calls[0]["stream_options"] == {"include_usage": True}


class TestStripThinkBlocks:
    """Unit tests for the _strip_think_blocks streaming helper."""

    def test_no_think_tags_passthrough(self):
        visible, leftover = _strip_think_blocks("Hello world")
        assert visible == "Hello world"
        assert leftover == ""

    def test_complete_think_block_removed(self):
        visible, leftover = _strip_think_blocks("<think>internal reasoning</think>answer")
        assert visible == "answer"
        assert leftover == ""

    def test_multiline_think_block_removed(self):
        buf = "<think>\nstep 1\nstep 2\n</think>final answer"
        visible, leftover = _strip_think_blocks(buf)
        assert visible == "final answer"
        assert leftover == ""

    def test_unclosed_think_held_in_leftover(self):
        # Streaming chunk ends before </think> arrives
        visible, leftover = _strip_think_blocks("prefix<think>partial reasoning")
        assert visible == "prefix"
        assert leftover == "<think>partial reasoning"

    def test_empty_string(self):
        visible, leftover = _strip_think_blocks("")
        assert visible == ""
        assert leftover == ""

    def test_only_think_block(self):
        visible, leftover = _strip_think_blocks("<think>all hidden</think>")
        assert visible == ""
        assert leftover == ""

    def test_multiple_think_blocks(self):
        buf = "<think>a</think>text1<think>b</think>text2"
        visible, leftover = _strip_think_blocks(buf)
        assert visible == "text1text2"
        assert leftover == ""

    def test_text_before_unclosed_think(self):
        visible, leftover = _strip_think_blocks("before<think>unclosed")
        assert visible == "before"
        assert leftover == "<think>unclosed"

    def test_closed_then_unclosed(self):
        # One complete block followed by a new unclosed one (cross-chunk scenario)
        buf = "<think>done</think>visible<think>still open"
        visible, leftover = _strip_think_blocks(buf)
        assert visible == "visible"
        assert leftover == "<think>still open"

    def test_partial_open_tag_is_held_for_next_chunk(self):
        visible, leftover = _strip_think_blocks("prefix<thi")
        assert visible == "prefix"
        assert leftover == "<thi"

    def test_partial_open_tag_after_closed_block_is_held(self):
        buf = "<think>done</think>visible<thi"
        visible, leftover = _strip_think_blocks(buf)
        assert visible == "visible"
        assert leftover == "<thi"

    def test_split_open_tag_across_chunks_does_not_leak_reasoning(self):
        buf = ""

        buf += "<thi"
        visible, buf = _strip_think_blocks(buf)
        assert visible == ""
        assert buf == "<thi"

        buf += "nk>secret</think>answer"
        visible, buf = _strip_think_blocks(buf)
        assert visible == "answer"
        assert buf == ""


class TestReasoningContentEmission:
    """``reasoning_content`` is a non-standard field. It must round-trip
    when the streaming parser captured non-empty reasoning, but the
    legacy "emit empty string when there are tool calls" behaviour now
    requires opt-in via ``OPENHARNESS_REQUIRE_EMPTY_REASONING_CONTENT=1``.

    Strict-OpenAI providers (Cerebras, NVIDIA NIM, OpenAI direct) reject
    requests carrying the field with a ``wrong_api_format`` 400, so the
    default-off behaviour fixes them out-of-the-box; Kimi-on-Anthropic
    users opt in via env var.
    """

    def _msg_with_tool_use(self, *, reasoning: str | None = None) -> ConversationMessage:
        msg = ConversationMessage(
            role="assistant",
            content=[
                TextBlock(text="ok"),
                ToolUseBlock(id="tool_1", name="read_file", input={"path": "x"}),
            ],
        )
        if reasoning is not None:
            msg._reasoning = reasoning  # type: ignore[attr-defined]
        return msg

    def test_omits_reasoning_when_no_captured_text(self, monkeypatch):
        monkeypatch.delenv("OPENHARNESS_REQUIRE_EMPTY_REASONING_CONTENT", raising=False)
        out = _convert_assistant_message(self._msg_with_tool_use())
        assert "reasoning_content" not in out

    def test_replays_captured_reasoning(self, monkeypatch):
        monkeypatch.delenv("OPENHARNESS_REQUIRE_EMPTY_REASONING_CONTENT", raising=False)
        out = _convert_assistant_message(self._msg_with_tool_use(reasoning="thinking…"))
        assert out["reasoning_content"] == "thinking…"

    def test_emits_empty_when_opted_in(self, monkeypatch):
        monkeypatch.setenv("OPENHARNESS_REQUIRE_EMPTY_REASONING_CONTENT", "1")
        out = _convert_assistant_message(self._msg_with_tool_use())
        assert out["reasoning_content"] == ""

    def test_opt_in_truthy_values(self, monkeypatch):
        for v in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv("OPENHARNESS_REQUIRE_EMPTY_REASONING_CONTENT", v)
            out = _convert_assistant_message(self._msg_with_tool_use())
            assert out.get("reasoning_content") == "", f"value={v!r}"

    def test_opt_in_falsy_values(self, monkeypatch):
        for v in ("0", "false", "no", "off", ""):
            monkeypatch.setenv("OPENHARNESS_REQUIRE_EMPTY_REASONING_CONTENT", v)
            out = _convert_assistant_message(self._msg_with_tool_use())
            assert "reasoning_content" not in out, f"value={v!r} should not opt in"

    def test_no_tool_calls_never_emits_empty(self, monkeypatch):
        # Pure-text assistant messages have always omitted the field; the
        # opt-in is scoped to tool-use messages where Kimi specifically
        # demands the placeholder.
        monkeypatch.setenv("OPENHARNESS_REQUIRE_EMPTY_REASONING_CONTENT", "1")
        msg = ConversationMessage(role="assistant", content=[TextBlock(text="hi")])
        out = _convert_assistant_message(msg)
        assert "reasoning_content" not in out
