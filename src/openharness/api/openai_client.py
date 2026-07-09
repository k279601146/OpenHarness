"""OpenAI-compatible API client for providers like Alibaba DashScope, GitHub Models, etc."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
import re
import uuid
from typing import Any, AsyncIterator
from urllib.parse import urlsplit, urlunsplit

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI

from openharness.api.client import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiReasoningDeltaEvent,
    ApiRetryEvent,
    ApiStreamEvent,
    ApiTextDeltaEvent,
)
from openharness.api.errors import (
    AuthenticationFailure,
    OpenHarnessApiError,
    RateLimitFailure,
    RequestFailure,
)
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import (
    ConversationMessage,
    ContentBlock,
    ImageBlock,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

log = logging.getLogger(__name__)

MAX_RETRIES = 10
BASE_DELAY = 0.5
MAX_DELAY = 60.0
# Watchdog configuration
STREAM_IDLE_TIMEOUT_MS = 120_000
STREAM_STALL_THRESHOLD_MS = 30_000
HEARTBEAT_INTERVAL = 30.0

_MAX_COMPLETION_TOKEN_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")
_REASONING_EFFORT_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")
_EXTENDED_PROMPT_CACHE_MODEL_PREFIXES = ("gpt-5", "gpt-4.1")
_DISABLE_STREAMING_ENV = "OPENHARNESS_OPENAI_DISABLE_STREAMING"
_DISABLE_STREAM_USAGE_ENV = "OPENHARNESS_OPENAI_DISABLE_STREAM_USAGE"
_DISABLE_PROMPT_CACHE_ENV = "OPENHARNESS_OPENAI_DISABLE_PROMPT_CACHE"
_PROMPT_CACHE_KEY_ENV = "OPENHARNESS_OPENAI_PROMPT_CACHE_KEY"
_PROMPT_CACHE_RETENTION_ENV = "OPENHARNESS_OPENAI_PROMPT_CACHE_RETENTION"
_SERVICE_TIER_ENV = "OPENHARNESS_OPENAI_SERVICE_TIER"


def _token_limit_param_for_model(model: str, max_tokens: int) -> dict[str, int]:
    """Return the correct token limit field for the target OpenAI model.

    GPT-5 and the current reasoning-model families reject ``max_tokens`` and
    require ``max_completion_tokens`` instead.
    """
    normalized = model.strip().lower()
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    if normalized.startswith(_MAX_COMPLETION_TOKEN_MODEL_PREFIXES):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}


def _responses_token_limit_param(max_tokens: int) -> dict[str, int]:
    return {"max_output_tokens": max_tokens}


def _normalized_model_name(model: str) -> str:
    normalized = model.strip().lower()
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def _reasoning_effort_param_for_model(model: str, effort: str | None) -> dict[str, str]:
    normalized_model = _normalized_model_name(model)
    if not normalized_model.startswith(_REASONING_EFFORT_MODEL_PREFIXES):
        return {}

    normalized_effort = (effort or "low").strip().lower()
    if normalized_effort == "none":
        return {"reasoning_effort": "none"}
    if normalized_effort == "max":
        normalized_effort = "high"
    if normalized_effort == "xhigh":
        normalized_effort = "high"
    if normalized_effort not in {"low", "medium", "high"}:
        normalized_effort = "low"
    return {"reasoning_effort": normalized_effort}


def _responses_reasoning_param_for_model(model: str, effort: str | None) -> dict[str, dict[str, str]]:
    normalized_model = _normalized_model_name(model)
    if not normalized_model.startswith(_REASONING_EFFORT_MODEL_PREFIXES):
        return {}

    normalized_effort = (effort or "low").strip().lower()
    if normalized_effort == "max":
        normalized_effort = "xhigh"
    if normalized_effort not in {"none", "minimal", "low", "medium", "high", "xhigh"}:
        normalized_effort = "low"
    return {"reasoning": {"effort": normalized_effort}}


def _openai_streaming_disabled() -> bool:
    raw = os.environ.get(_DISABLE_STREAMING_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _openai_stream_usage_disabled() -> bool:
    raw = os.environ.get(_DISABLE_STREAM_USAGE_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _openai_prompt_cache_disabled() -> bool:
    raw = os.environ.get(_DISABLE_PROMPT_CACHE_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _supports_extended_prompt_cache(model: str) -> bool:
    return _normalized_model_name(model).startswith(_EXTENDED_PROMPT_CACHE_MODEL_PREFIXES)


def _prompt_cache_params_for_request(
    *,
    model: str,
    instructions: str | None,
    tools: list[dict[str, Any]] | None,
) -> dict[str, str]:
    if _openai_prompt_cache_disabled():
        return {}

    explicit_key = os.environ.get(_PROMPT_CACHE_KEY_ENV, "").strip()
    if explicit_key:
        cache_key = explicit_key[:64]
    else:
        tool_fingerprint_source = [
            {
                "type": tool.get("type"),
                "name": tool.get("name") or _usage_attr(tool.get("function"), "name"),
                "description": tool.get("description") or _usage_attr(tool.get("function"), "description"),
            }
            for tool in tools or []
        ]
        prefix_source = json.dumps(
            {
                "model": _normalized_model_name(model),
                "instructions_prefix": (instructions or "")[:8192],
                "tools": tool_fingerprint_source,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(prefix_source.encode("utf-8")).hexdigest()[:24]
        cache_key = f"openharness:{_normalized_model_name(model)}:{digest}"[:64]

    params = {"prompt_cache_key": cache_key}
    explicit_retention = os.environ.get(_PROMPT_CACHE_RETENTION_ENV, "").strip().lower()
    if explicit_retention in {"off", "none", "false", "0"}:
        return params
    if explicit_retention:
        params["prompt_cache_retention"] = explicit_retention
    elif _supports_extended_prompt_cache(model):
        params["prompt_cache_retention"] = "24h"
    return params


def _strip_prompt_cache_params(params: dict[str, Any]) -> bool:
    removed = False
    for key in ("prompt_cache_key", "prompt_cache_retention"):
        if key in params:
            params.pop(key, None)
            removed = True
    return removed


def _looks_like_prompt_cache_unsupported(exc: Exception) -> bool:
    text = " ".join(
        str(part)
        for part in (
            exc,
            getattr(exc, "body", None),
            getattr(exc, "response", None),
        )
        if part is not None
    ).lower()
    if "prompt_cache_key" not in text and "prompt_cache_retention" not in text:
        return False
    return any(
        term in text
        for term in (
            "unknown",
            "unsupported",
            "unrecognized",
            "invalid",
            "extra",
            "not permitted",
            "not supported",
        )
    )


def _service_tier_param() -> dict[str, str]:
    service_tier = os.environ.get(_SERVICE_TIER_ENV, "").strip()
    return {"service_tier": service_tier} if service_tier else {}


def _strip_service_tier_param(params: dict[str, Any]) -> bool:
    if "service_tier" not in params:
        return False
    params.pop("service_tier", None)
    return True


def _looks_like_service_tier_unsupported(exc: Exception) -> bool:
    text = " ".join(
        str(part)
        for part in (
            exc,
            getattr(exc, "body", None),
            getattr(exc, "response", None),
        )
        if part is not None
    ).lower()
    if "service_tier" not in text:
        return False
    return any(
        term in text
        for term in (
            "unknown",
            "unsupported",
            "unrecognized",
            "invalid",
            "extra",
            "not permitted",
            "not supported",
        )
    )


def _usage_attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _usage_detail_int(details: Any, *names: str) -> int | None:
    for name in names:
        value = _usage_attr(details, name)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _usage_snapshot_from_openai_usage(usage: Any) -> UsageSnapshot:
    prompt_details = _usage_attr(usage, "prompt_tokens_details")
    if prompt_details is None:
        prompt_details = _usage_attr(usage, "input_tokens_details")

    return UsageSnapshot(
        input_tokens=int(_usage_attr(usage, "prompt_tokens", 0) or _usage_attr(usage, "input_tokens", 0) or 0),
        output_tokens=int(_usage_attr(usage, "completion_tokens", 0) or _usage_attr(usage, "output_tokens", 0) or 0),
        cache_read_input_tokens=_usage_detail_int(
            prompt_details,
            "cached_tokens",
            "cache_read_input_tokens",
            "cached_input_tokens",
        ),
        cache_creation_input_tokens=_usage_detail_int(
            prompt_details,
            "cache_creation_input_tokens",
            "cache_creation_tokens",
        ),
    )


def _convert_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic tool schemas to OpenAI function-calling format.

    Anthropic format:
        {"name": "...", "description": "...", "input_schema": {...}}
    OpenAI format:
        {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
    """
    result = []
    for tool in tools:
        result.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        })
    return result


def _convert_tools_to_responses(
    tools: list[dict[str, Any]],
    *,
    include_hosted_web_search: bool = True,
) -> list[dict[str, Any]]:
    result = []
    use_hosted_web_search = include_hosted_web_search and _should_register_hosted_web_search(tools)
    if use_hosted_web_search:
        result.append({"type": "web_search"})
    for tool in tools:
        if use_hosted_web_search and tool.get("name") == "web_search":
            continue
        result.append({
            "type": "function",
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {}),
        })
    return result


def _should_register_hosted_web_search(tools: list[dict[str, Any]]) -> bool:
    if os.environ.get("OPENHARNESS_DISABLE_HOSTED_WEB_SEARCH", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    return any(tool.get("name") == "web_search" for tool in tools)


def _without_hosted_web_search(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return tools
    return [tool for tool in tools if tool.get("type") != "web_search"]


def _has_hosted_web_search(tools: list[dict[str, Any]] | None) -> bool:
    return any(tool.get("type") == "web_search" for tool in tools or [])


def _convert_tools_to_responses_local_web_search_fallback(
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if not tools:
        return tools
    return _convert_tools_to_responses(tools, include_hosted_web_search=False)


def _looks_like_hosted_web_search_unsupported(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code not in {400, 404, 422}:
        return False
    body = getattr(exc, "body", None)
    text = f"{body or ''} {exc}".lower()
    if "web_search" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "unsupported",
            "not supported",
            "invalid",
            "unknown",
            "unrecognized",
            "extra_forbidden",
        )
    )


def _looks_like_endpoint_unsupported(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    text = f"{body or ''} {exc}".lower()
    if status_code in {404, 405}:
        return True
    if status_code not in {400, 422}:
        return False
    return any(
        marker in text
        for marker in (
            "no route",
            "route not found",
            "unknown endpoint",
            "unsupported endpoint",
            "endpoint not found",
            "unsupported api",
            "unsupported route",
            "wrong_api_format",
            "api format",
            "responses api is not",
            "responses endpoint",
            "chat/completions endpoint",
        )
    )


def _looks_like_stream_options_unsupported(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code not in {400, 422}:
        return False
    body = getattr(exc, "body", None)
    text = f"{body or ''} {exc}".lower()
    if "stream_options" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "unsupported",
            "not supported",
            "unknown",
            "unrecognized",
            "invalid",
            "extra_forbidden",
        )
    )


def _convert_messages_to_openai(
    messages: list[ConversationMessage],
    system_prompt: Any,
) -> list[dict[str, Any]]:
    """Convert Anthropic-style messages to OpenAI chat format.

    Key differences:
    - Anthropic: system prompt is a separate parameter
    - OpenAI: system prompt is a message with role="system"
    - Anthropic: tool_use / tool_result are content blocks
    - OpenAI: tool_calls on assistant message, tool results are separate messages
    """
    openai_messages: list[dict[str, Any]] = []

    # Merge consecutive messages with the same role to satisfy strict provider requirements
    merged_messages: list[dict[str, Any]] = []
    if system_prompt:
        if isinstance(system_prompt, list):
            # Flatten block-style system prompt (Anthropic style) into string
            text_parts = []
            for block in system_prompt:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            system_text = "\n\n".join(text_parts)
        else:
            system_text = str(system_prompt)
            
        if system_text.strip():
            merged_messages.append({"role": "system", "content": system_text})

    raw_openai_messages: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "assistant":
            openai_msg = _convert_assistant_message(msg)
            raw_openai_messages.append(openai_msg)
        elif msg.role == "user":
            # User messages may contain text or tool_result blocks
            tool_results = [b for b in msg.content if isinstance(b, ToolResultBlock)]
            user_blocks = [b for b in msg.content if isinstance(b, (TextBlock, ImageBlock))]

            if tool_results:
                # Each tool result becomes a separate message with role="tool"
                for tr in tool_results:
                    raw_openai_messages.append({
                        "role": "tool",
                        "tool_call_id": tr.tool_use_id,
                        "content": tr.content,
                    })
            if user_blocks:
                content = _convert_user_content_to_openai(user_blocks)
                if isinstance(content, str):
                    if content.strip():
                        raw_openai_messages.append({"role": "user", "content": content})
                elif content:
                    raw_openai_messages.append({"role": "user", "content": content})
            if not tool_results and not user_blocks:
                # Empty user message (shouldn't happen, but handle gracefully)
                raw_openai_messages.append({"role": "user", "content": ""})

    # Perform merging
    for msg in raw_openai_messages:
        if not merged_messages or merged_messages[-1]["role"] != msg["role"] or msg["role"] == "tool":
            # Note: role="tool" messages must remain separate in OpenAI spec, 
            # each corresponding to a tool_call_id.
            merged_messages.append(msg)
        else:
            # Merge content
            prev = merged_messages[-1]
            if isinstance(prev["content"], str) and isinstance(msg.get("content"), str):
                prev["content"] = prev["content"] + "\n\n" + msg["content"]
            elif isinstance(prev["content"], list) or isinstance(msg.get("content"), list):
                # Convert both to list if needed
                p_content = prev["content"] if isinstance(prev["content"], list) else [{"type": "text", "text": prev["content"]}]
                m_content = msg["content"] if isinstance(msg["content"], list) else [{"type": "text", "text": msg["content"]}]
                prev["content"] = p_content + m_content
            
            # For assistant messages, also merge tool_calls if present
            if msg["role"] == "assistant":
                if "tool_calls" in msg:
                    prev.setdefault("tool_calls", []).extend(msg["tool_calls"])
                if "reasoning_content" in msg:
                    prev["reasoning_content"] = (prev.get("reasoning_content") or "") + "\n" + msg["reasoning_content"]

    return merged_messages


def _convert_messages_to_responses_input(messages: list[ConversationMessage]) -> list[dict[str, Any]]:
    responses_items: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == "assistant":
            text_parts = [b.text for b in msg.content if isinstance(b, TextBlock)]
            text = "".join(text_parts)
            if text:
                responses_items.append({
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                })
            for tool_use in [b for b in msg.content if isinstance(b, ToolUseBlock)]:
                responses_items.append({
                    "type": "function_call",
                    "call_id": tool_use.id,
                    "name": tool_use.name,
                    "arguments": json.dumps(tool_use.input),
                })
        elif msg.role == "user":
            user_blocks = [b for b in msg.content if isinstance(b, (TextBlock, ImageBlock))]
            tool_results = [b for b in msg.content if isinstance(b, ToolResultBlock)]

            if user_blocks:
                content = _convert_user_content_to_responses(user_blocks)
                if content:
                    responses_items.append({"role": "user", "content": content})

            for tool_result in tool_results:
                responses_items.append({
                    "type": "function_call_output",
                    "call_id": tool_result.tool_use_id,
                    "output": tool_result.content,
                })

            if not user_blocks and not tool_results:
                responses_items.append({
                    "role": "user",
                    "content": [{"type": "input_text", "text": ""}],
                })

    return responses_items


def _convert_user_content_to_responses(blocks: list[ContentBlock]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for block in blocks:
        if isinstance(block, TextBlock) and block.text:
            content.append({"type": "input_text", "text": block.text})
        elif isinstance(block, ImageBlock):
            content.append({
                "type": "input_image",
                "image_url": f"data:{block.media_type};base64,{block.data}",
            })
    return content


def _system_prompt_to_responses_instructions(system_prompt: Any) -> str | None:
    if not system_prompt:
        return None
    if isinstance(system_prompt, list):
        parts = []
        for block in system_prompt:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        text = "\n\n".join(parts)
    else:
        text = str(system_prompt)
    return text if text.strip() else None


def _convert_user_content_to_openai(blocks: list[ContentBlock]) -> str | list[dict[str, Any]]:
    """Convert user text/image blocks into OpenAI chat content."""
    has_image = any(isinstance(block, ImageBlock) for block in blocks)
    if not has_image:
        return "".join(block.text for block in blocks if isinstance(block, TextBlock))

    content: list[dict[str, Any]] = []
    for block in blocks:
        if isinstance(block, TextBlock) and block.text:
            content.append({"type": "text", "text": block.text})
        elif isinstance(block, ImageBlock):
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{block.media_type};base64,{block.data}",
                },
            })
    return content


_EMPTY_REASONING_ENV = "OPENHARNESS_REQUIRE_EMPTY_REASONING_CONTENT"


def _empty_reasoning_required() -> bool:
    """True when the operator's provider requires an empty
    ``reasoning_content`` field on tool-using assistant messages
    (Kimi-on-Anthropic style). Default off — strict-OpenAI providers
    reject the field outright.
    """
    raw = os.environ.get(_EMPTY_REASONING_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _convert_assistant_message(msg: ConversationMessage) -> dict[str, Any]:
    """Convert an assistant ConversationMessage to OpenAI format.

    ``reasoning_content`` is a non-standard field used by thinking models
    (e.g. Kimi k2.5) to carry the model's internal chain-of-thought across
    turns. Some thinking-model providers require it on every assistant
    message with tool calls — even when empty — or they reject the request.
    Other OpenAI-compatible providers (Cerebras, OpenAI's own
    endpoint, etc.) reject the field outright with a 400
    ``wrong_api_format`` error.

    Behaviour:

    - When the streaming parser captured non-empty reasoning on
      ``msg._reasoning``, we always replay it. Models that emit reasoning
      tokens are by definition thinking models that round-trip them.
    - When there is no captured reasoning but the message has tool calls,
      we emit ``reasoning_content: ""`` only if the operator opts in via
      ``OPENHARNESS_REQUIRE_EMPTY_REASONING_CONTENT=1``. The default is
      omit, which matches strict-OpenAI providers.

    The opt-in default keeps strict-OpenAI providers (Cerebras, NVIDIA NIM,
    OpenAI direct, etc.) working out-of-the-box; Kimi-on-Anthropic users
    set the env var in their dotfiles or settings.
    """
    text_parts = [b.text for b in msg.content if isinstance(b, TextBlock)]
    tool_uses = [b for b in msg.content if isinstance(b, ToolUseBlock)]

    openai_msg: dict[str, Any] = {"role": "assistant"}

    content = "".join(text_parts)
    openai_msg["content"] = content if content else ""

    # Replay reasoning_content for thinking models (stored by streaming parser)
    reasoning = getattr(msg, "_reasoning", None)
    if reasoning:
        openai_msg["reasoning_content"] = reasoning
    elif tool_uses and _empty_reasoning_required():
        # Kimi-style providers reject tool_use messages without this field
        # even when there's nothing to put in it. Opt-in via env var.
        openai_msg["reasoning_content"] = ""

    if tool_uses:
        openai_msg["tool_calls"] = [
            {
                "id": tu.id,
                "type": "function",
                "function": {
                    "name": tu.name,
                    "arguments": json.dumps(tu.input),
                },
            }
            for tu in tool_uses
        ]

    return openai_msg


def _parse_assistant_response(response: Any) -> ConversationMessage:
    """Parse an OpenAI ChatCompletion response into a ConversationMessage."""
    choice = response.choices[0]
    message = choice.message
    content: list[ContentBlock] = []

    if message.content:
        content.append(TextBlock(text=message.content))

    if message.tool_calls:
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            content.append(ToolUseBlock(
                id=tc.id,
                name=tc.function.name,
                input=args,
            ))

    return ConversationMessage(role="assistant", content=content)


def _usage_snapshot_from_chat_response(response: Any) -> UsageSnapshot:
    return _usage_snapshot_from_openai_usage(getattr(response, "usage", None))


def _usage_snapshot_from_responses_response(response: Any) -> UsageSnapshot:
    return _usage_snapshot_from_openai_usage(_usage_attr(response, "usage"))


def _response_event_type(event: Any) -> str | None:
    return _usage_attr(event, "type")


def _response_event_attr(event: Any, name: str, default: Any = None) -> Any:
    return _usage_attr(event, name, default)


def _response_item_attr(item: Any, name: str, default: Any = None) -> Any:
    return _usage_attr(item, name, default)


def _text_from_response_message_item(item: Any) -> str:
    raw_content = _response_item_attr(item, "content", [])
    parts: list[str] = []
    if isinstance(raw_content, list):
        for block in raw_content:
            block_type = _usage_attr(block, "type")
            if block_type in {"output_text", "text"}:
                parts.append(str(_usage_attr(block, "text", "")))
            elif block_type == "refusal":
                parts.append(str(_usage_attr(block, "refusal", "")))
    return "".join(parts)


def _tool_use_from_response_item(item: Any) -> ToolUseBlock | None:
    item_type = _response_item_attr(item, "type")
    if item_type != "function_call":
        return None
    call_id = _response_item_attr(item, "call_id") or _response_item_attr(item, "id")
    name = _response_item_attr(item, "name")
    arguments = _response_item_attr(item, "arguments", "")
    if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
        return None
    if isinstance(arguments, str) and arguments:
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            parsed = {}
    elif isinstance(arguments, dict):
        parsed = arguments
    else:
        parsed = {}
    return ToolUseBlock(id=call_id, name=name, input=parsed if isinstance(parsed, dict) else {})


def _response_item_with_arguments(item: Any, arguments: str) -> Any:
    if isinstance(item, dict):
        merged = dict(item)
        merged["arguments"] = arguments
        return merged
    try:
        setattr(item, "arguments", arguments)
    except Exception:
        return item
    return item


def _function_argument_keys(*values: Any) -> list[str]:
    keys: list[str] = []
    for value in values:
        if value is None or value == "":
            continue
        keys.append(str(value))
    return keys


def _function_argument_for_item(item: Any, arguments_by_key: dict[str, str]) -> str | None:
    keys = _function_argument_keys(
        _response_item_attr(item, "id"),
        _response_item_attr(item, "call_id"),
        f"index:{_response_item_attr(item, 'output_index')}"
        if _response_item_attr(item, "output_index") is not None
        else None,
    )
    for key in keys:
        arguments = arguments_by_key.get(key)
        if arguments:
            return arguments
    return None


def _normalize_openai_base_url(base_url: str | None) -> str | None:
    """Normalize custom OpenAI-compatible base URLs without dropping API path segments."""
    if not base_url:
        return None
    trimmed = base_url.strip()
    if not trimmed:
        return None
    parts = urlsplit(trimmed)
    if not parts.scheme or not parts.netloc:
        return trimmed.rstrip("/")
    path = parts.path.rstrip("/")
    if not path:
        path = "/v1"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _chat_completion_params_for_request(request: ApiMessageRequest, *, stream: bool) -> dict[str, Any]:
    tools = _convert_tools_to_openai(request.tools) if request.tools else None
    params: dict[str, Any] = {
        "model": request.model,
        "messages": _convert_messages_to_openai(request.messages, request.system_prompt),
        "stream": stream,
    }
    params.update(_token_limit_param_for_model(request.model, request.max_tokens))
    params.update(_reasoning_effort_param_for_model(request.model, request.effort))
    params.update(_service_tier_param())
    if stream and not _openai_stream_usage_disabled():
        params["stream_options"] = {"include_usage": True}
    if tools:
        params["tools"] = tools
        params["tool_choice"] = "auto"
    return params


class OpenAICompatibleClient:
    """Client for OpenAI-compatible APIs (DashScope, GitHub Models, etc.).

    Implements the same SupportsStreamingMessages protocol as AnthropicApiClient
    so it can be used as a drop-in replacement in the agent loop.
    """

    def __init__(self, api_key: str, *, base_url: str | None = None, timeout: float | None = None) -> None:
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "default_headers": {
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "OpenHarness/1.0",
            },
        }
        normalized_base_url = _normalize_openai_base_url(base_url)
        self._base_url = normalized_base_url
        if normalized_base_url:
            kwargs["base_url"] = normalized_base_url
        if timeout is not None:
            kwargs["timeout"] = timeout
        kwargs["max_retries"] = 0
        self._client = AsyncOpenAI(**kwargs)

    async def aclose(self) -> None:
        """Close the underlying async SDK client before its event loop exits."""
        close = getattr(self._client, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """Yield text deltas and the final message, matching the Anthropic client interface."""
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                async for event in self._stream_once(request):
                    yield event
                return
            except OpenHarnessApiError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt >= MAX_RETRIES or not self._is_retryable(exc):
                    raise self._translate_error(exc) from exc

                delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
                log.warning(
                    "OpenAI API request failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, MAX_RETRIES + 1, delay, exc,
                )
                yield ApiRetryEvent(
                    message=str(exc),
                    attempt=attempt + 1,
                    max_attempts=MAX_RETRIES + 1,
                    delay_seconds=delay,
                )
                
                # Smart sleep/heartbeat
                remaining = delay
                while remaining > 0:
                    chunk = min(remaining, HEARTBEAT_INTERVAL)
                    await asyncio.sleep(chunk)
                    remaining -= chunk
                    if remaining > 0:
                        log.debug(f"Still waiting for OpenAI retry... (remaining {remaining:.1f}s)")

        if last_error is not None:
            raise self._translate_error(last_error) from last_error

    async def _stream_once(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """Single attempt: stream an OpenAI Responses API request."""
        responses_input = _convert_messages_to_responses_input(request.messages)
        responses_tools = _convert_tools_to_responses(request.tools) if request.tools else None
        request_id = f"oh-{uuid.uuid4().hex[:10]}"

        params: dict[str, Any] = {
            "model": request.model,
            "input": responses_input,
            "stream": True,
        }
        instructions = _system_prompt_to_responses_instructions(request.system_prompt)
        if instructions:
            params["instructions"] = instructions
        if _openai_streaming_disabled():
            params["stream"] = False
        params.update(_responses_token_limit_param(request.max_tokens))
        params.update(_responses_reasoning_param_for_model(request.model, request.effort))
        if responses_tools:
            params["tools"] = responses_tools
            params["tool_choice"] = "auto"
            params["parallel_tool_calls"] = True
        prompt_cache_params = _prompt_cache_params_for_request(
            model=request.model,
            instructions=instructions,
            tools=responses_tools,
        )
        params.update(prompt_cache_params)
        params.update(_service_tier_param())
        chat_params = _chat_completion_params_for_request(request, stream=bool(params.get("stream")))

        async def _create_response_with_optional_param_fallback(create_params: dict[str, Any]) -> Any:
            try:
                return await self._client.responses.create(**create_params)
            except Exception as exc:
                if _looks_like_prompt_cache_unsupported(exc) and _strip_prompt_cache_params(create_params):
                    log.warning(
                        "[OpenAICompat:%s] prompt cache params unsupported by upstream; retrying without them",
                        request_id,
                    )
                    return await self._client.responses.create(**create_params)
                if _looks_like_service_tier_unsupported(exc) and _strip_service_tier_param(create_params):
                    log.warning(
                        "[OpenAICompat:%s] service_tier unsupported by upstream; retrying without it",
                        request_id,
                    )
                    return await self._client.responses.create(**create_params)
                raise

        async def _create_chat_completion_with_optional_param_fallback(create_params: dict[str, Any]) -> Any:
            try:
                return await self._client.chat.completions.create(**create_params)
            except Exception as exc:
                if _looks_like_service_tier_unsupported(exc) and _strip_service_tier_param(create_params):
                    log.warning(
                        "[OpenAICompat:%s] chat service_tier unsupported by upstream; retrying without it",
                        request_id,
                    )
                    return await self._client.chat.completions.create(**create_params)
                if (
                    _usage_attr(create_params, "stream_options") is not None
                    and _looks_like_service_tier_unsupported(exc) is False
                    and _looks_like_stream_options_unsupported(exc)
                ):
                    create_params.pop("stream_options", None)
                    log.warning(
                        "[OpenAICompat:%s] chat stream_options unsupported by upstream; retrying without usage include flag",
                        request_id,
                    )
                    return await self._client.chat.completions.create(**create_params)
                raise

        async def _create_response_or_chat(create_params: dict[str, Any], chat_create_params: dict[str, Any]) -> tuple[str, Any]:
            try:
                return "responses", await _create_response_with_optional_param_fallback(create_params)
            except Exception as exc:
                if not _looks_like_endpoint_unsupported(exc):
                    raise
                log.warning(
                    "[OpenAICompat:%s] responses endpoint unsupported by upstream; retrying via chat/completions",
                    request_id,
                )
                return "chat/completions", await _create_chat_completion_with_optional_param_fallback(chat_create_params)

        log.info(
            "[OpenAICompat:%s] responses request model=%s stream=%s input_items=%d system=%s "
            "tools=%d tool_names=%s max_output_tokens=%s reasoning=%s prompt_cache=%s retention=%s service_tier=%s base_url=%s",
            request_id,
            request.model,
            params.get("stream"),
            len(responses_input),
            "yes" if instructions else "no",
            len(responses_tools or []),
            [tool.get("name") or tool.get("type") for tool in (responses_tools or [])[:8]],
            params.get("max_output_tokens"),
            params.get("reasoning"),
            "yes" if params.get("prompt_cache_key") else "no",
            params.get("prompt_cache_retention"),
            params.get("service_tier"),
            getattr(self._client, "base_url", None),
        )

        if not params.get("stream"):
            response: Any | None = None
            response_protocol = "responses"
            try:
                response_protocol, response = await _create_response_or_chat(params, chat_params)
            except Exception as exc:
                if _has_hosted_web_search(responses_tools) and _looks_like_hosted_web_search_unsupported(exc):
                    fallback_tools = _convert_tools_to_responses_local_web_search_fallback(request.tools)
                    if fallback_tools:
                        params["tools"] = fallback_tools
                        log.warning(
                            "[OpenAICompat:%s] hosted web_search unsupported; retrying non-stream with local web_search function fallback",
                            request_id,
                        )
                        chat_params["tools"] = _convert_tools_to_openai(request.tools)
                        response_protocol, response = await _create_response_or_chat(params, chat_params)
                    else:
                        raise
                else:
                    log.warning(
                        "[OpenAICompat:%s] responses non-stream create failed type=%s status=%s body=%s message=%s",
                        request_id,
                        exc.__class__.__name__,
                        getattr(exc, "status_code", None),
                        getattr(exc, "body", None),
                        exc,
                    )
                    raise
            except BaseException:
                raise
            else:
                pass

            if response is None:
                log.warning(
                    "[OpenAICompat:%s] responses non-stream create returned no response",
                    request_id,
                )
                raise RequestFailure("Responses API returned no response")

            content: list[ContentBlock] = []
            if response_protocol == "chat/completions":
                message = _parse_assistant_response(response)
                if message.text:
                    yield ApiTextDeltaEvent(text=message.text)
                log.info(
                    "[OpenAICompat:%s] chat non-stream complete content_chars=%d tools=%d",
                    request_id,
                    len(message.text),
                    len(message.tool_uses),
                )
                yield ApiMessageCompleteEvent(
                    message=message,
                    usage=_usage_snapshot_from_chat_response(response),
                    stop_reason=_usage_attr(_usage_attr(response, "choices", [None])[0], "finish_reason"),
                )
                return

            for item in _usage_attr(response, "output", []) or []:
                item_type = _response_item_attr(item, "type")
                if item_type == "message":
                    text = _text_from_response_message_item(item)
                    if text:
                        content.append(TextBlock(text=text))
                else:
                    tool_use = _tool_use_from_response_item(item)
                    if tool_use:
                        content.append(tool_use)

            message = ConversationMessage(role="assistant", content=content)
            if message.text:
                yield ApiTextDeltaEvent(text=message.text)
            log.info(
                "[OpenAICompat:%s] responses non-stream complete content_chars=%d tools=%d status=%s",
                request_id,
                len(message.text),
                len(message.tool_uses),
                _usage_attr(response, "status"),
            )
            yield ApiMessageCompleteEvent(
                message=message,
                usage=_usage_snapshot_from_responses_response(response),
                stop_reason=_usage_attr(response, "status"),
            )
            return

        collected_content = ""
        collected_reasoning = ""
        function_call_items: list[Any] = []
        function_call_arguments: dict[str, str] = {}
        chat_tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage = UsageSnapshot()
        _think_buf = ""

        request_started_at = asyncio.get_event_loop().time()
        response_protocol = "responses"
        try:
            response_protocol, response_stream = await _create_response_or_chat(params, chat_params)
            stream_opened_at = asyncio.get_event_loop().time()
            log.info(
                "[OpenAICompat:%s] stream_open latency=%.3fs protocol=%s",
                request_id,
                stream_opened_at - request_started_at,
                response_protocol,
            )
        except Exception as exc:
            if _has_hosted_web_search(responses_tools) and _looks_like_hosted_web_search_unsupported(exc):
                fallback_tools = _convert_tools_to_responses_local_web_search_fallback(request.tools)
                if fallback_tools:
                    params["tools"] = fallback_tools
                    chat_params["tools"] = _convert_tools_to_openai(request.tools)
                    log.warning(
                        "[OpenAICompat:%s] hosted web_search unsupported; retrying with local web_search function fallback",
                        request_id,
                    )
                    try:
                        response_protocol, response_stream = await _create_response_or_chat(params, chat_params)
                        stream_opened_at = asyncio.get_event_loop().time()
                        log.info(
                            "[OpenAICompat:%s] stream_open latency=%.3fs fallback=yes protocol=%s",
                            request_id,
                            stream_opened_at - request_started_at,
                            response_protocol,
                        )
                    except Exception as fallback_exc:
                        log.warning(
                            "[OpenAICompat:%s] responses fallback create failed type=%s status=%s body=%s message=%s",
                            request_id,
                            fallback_exc.__class__.__name__,
                            getattr(fallback_exc, "status_code", None),
                            getattr(fallback_exc, "body", None),
                            fallback_exc,
                        )
                        raise
                else:
                    raise
            else:
                log.warning(
                    "[OpenAICompat:%s] responses create failed type=%s status=%s body=%s message=%s",
                    request_id,
                    exc.__class__.__name__,
                    getattr(exc, "status_code", None),
                    getattr(exc, "body", None),
                    exc,
                )
                raise

        last_event_time = asyncio.get_event_loop().time()

        async def _watchdog_iterator():
            nonlocal last_event_time
            iterator = response_stream.__aiter__()
            while True:
                try:
                    event = await asyncio.wait_for(iterator.__anext__(), timeout=STREAM_IDLE_TIMEOUT_MS / 1000)
                    now = asyncio.get_event_loop().time()
                    gap = now - last_event_time
                    if gap > STREAM_STALL_THRESHOLD_MS / 1000:
                        log.warning(f"OpenAI Responses streaming stall detected: {gap:.1f}s gap.")
                    last_event_time = now
                    yield event
                except asyncio.TimeoutError:
                    log.error(f"OpenAI Responses streaming idle timeout after {STREAM_IDLE_TIMEOUT_MS}ms.")
                    raise TimeoutError("Streaming idle timeout")
                except StopAsyncIteration:
                    break

        try:
            first_visible_delta_at: float | None = None
            first_stream_event_at: float | None = None
            async for event in _watchdog_iterator():
                if first_stream_event_at is None:
                    first_stream_event_at = asyncio.get_event_loop().time()
                    log.info(
                        "[OpenAICompat:%s] first_stream_event total_latency=%.3fs stream_latency=%.3fs type=%s",
                        request_id,
                        first_stream_event_at - request_started_at,
                        first_stream_event_at - stream_opened_at,
                        _response_event_type(event),
                    )
                event_type = _response_event_type(event)

                if event_type == "response.output_text.delta":
                    delta = _response_event_attr(event, "delta", "")
                    if not isinstance(delta, str) or not delta:
                        continue
                    _think_buf += delta
                    visible, _think_buf = _strip_think_blocks(_think_buf)
                    if visible:
                        collected_content += visible
                        if first_visible_delta_at is None:
                            first_visible_delta_at = asyncio.get_event_loop().time()
                            log.info(
                                "[OpenAICompat:%s] first_visible_delta total_latency=%.3fs stream_latency=%.3fs chars=%d",
                                request_id,
                                first_visible_delta_at - request_started_at,
                                first_visible_delta_at - stream_opened_at,
                                len(visible),
                            )
                        yield ApiTextDeltaEvent(text=visible)
                    continue

                if event_type in {"response.reasoning.delta", "response.reasoning_text.delta"}:
                    reasoning_piece = (
                        _response_event_attr(event, "delta", "")
                        or _response_event_attr(event, "text", "")
                        or ""
                    )
                    if not isinstance(reasoning_piece, str):
                        reasoning_piece = str(reasoning_piece)
                    if reasoning_piece:
                        collected_reasoning += reasoning_piece
                        yield ApiReasoningDeltaEvent(text=reasoning_piece)
                    continue

                if event_type == "response.output_item.done":
                    item = _response_event_attr(event, "item")
                    if not item:
                        continue
                    item_type = _response_item_attr(item, "type")
                    if item_type == "message":
                        text = _text_from_response_message_item(item)
                        if text and not collected_content:
                            collected_content = text
                    else:
                        output_index = _response_event_attr(event, "output_index")
                        if output_index is not None and isinstance(item, dict):
                            item = {**item, "output_index": output_index}
                        function_call_items.append(item)
                    continue

                if event_type == "response.function_call_arguments.delta":
                    item_id = _response_event_attr(event, "item_id")
                    call_id = _response_event_attr(event, "call_id")
                    output_index = _response_event_attr(event, "output_index")
                    delta = _response_event_attr(event, "delta", "")
                    keys = _function_argument_keys(
                        item_id,
                        call_id,
                        f"index:{output_index}" if output_index is not None else None,
                    )
                    if keys and isinstance(delta, str):
                        key = keys[0]
                        function_call_arguments[key] = function_call_arguments.get(key, "") + delta
                    continue

                if event_type == "response.function_call_arguments.done":
                    item_id = _response_event_attr(event, "item_id")
                    call_id = _response_event_attr(event, "call_id")
                    output_index = _response_event_attr(event, "output_index")
                    arguments = _response_event_attr(event, "arguments", "")
                    keys = _function_argument_keys(
                        item_id,
                        call_id,
                        f"index:{output_index}" if output_index is not None else None,
                    )
                    if keys and isinstance(arguments, str):
                        for key in keys:
                            function_call_arguments[key] = arguments
                    continue

                if event_type == "response.completed":
                    response_payload = _response_event_attr(event, "response", {})
                    if response_payload:
                        usage = _usage_snapshot_from_responses_response(response_payload)
                        finish_reason = _usage_attr(response_payload, "status") or "completed"
                    continue

                if event_type in {"response.failed", "response.incomplete"}:
                    response_payload = _response_event_attr(event, "response", {})
                    error = _usage_attr(response_payload, "error") or _response_event_attr(event, "error")
                    raise RequestFailure(str(error or f"Responses API stream ended with {event_type}"))

                if event_type == "error":
                    raise RequestFailure(str(_response_event_attr(event, "message", event)))

                if _usage_attr(event, "usage") is not None and _usage_attr(event, "output") is not None:
                    usage = _usage_snapshot_from_responses_response(event)
                    finish_reason = _usage_attr(event, "status") or finish_reason
                    continue

                choices = _usage_attr(event, "choices")
                event_usage = _usage_attr(event, "usage")
                if event_usage:
                    usage = _usage_snapshot_from_openai_usage(event_usage)
                if not choices:
                    continue
                choice = choices[0]
                chunk_finish = _usage_attr(choice, "finish_reason")
                if chunk_finish:
                    finish_reason = chunk_finish
                delta = _usage_attr(choice, "delta")
                if not delta:
                    continue

                reasoning_piece = _usage_attr(delta, "reasoning_content", "") or ""
                if reasoning_piece:
                    collected_reasoning += reasoning_piece
                    yield ApiReasoningDeltaEvent(text=reasoning_piece)

                delta_tool_calls = _usage_attr(delta, "tool_calls")
                if delta_tool_calls:
                    for raw_tool_call in delta_tool_calls:
                        index = _usage_attr(raw_tool_call, "index", 0)
                        try:
                            index = int(index)
                        except (TypeError, ValueError):
                            index = len(chat_tool_calls)
                        entry = chat_tool_calls.setdefault(
                            index,
                            {
                                "type": "function_call",
                                "call_id": f"call_{index}",
                                "name": "",
                                "arguments": "",
                            },
                        )
                        call_id = _usage_attr(raw_tool_call, "id")
                        if isinstance(call_id, str) and call_id:
                            entry["call_id"] = call_id
                        function = _usage_attr(raw_tool_call, "function") or {}
                        name = _usage_attr(function, "name")
                        if isinstance(name, str) and name:
                            entry["name"] = name
                        arguments = _usage_attr(function, "arguments")
                        if isinstance(arguments, str) and arguments:
                            entry["arguments"] = str(entry.get("arguments") or "") + arguments

                delta_content = _usage_attr(delta, "content", "")
                if delta_content:
                    _think_buf += delta_content
                    visible, _think_buf = _strip_think_blocks(_think_buf)
                    if visible:
                        collected_content += visible
                        if first_visible_delta_at is None:
                            first_visible_delta_at = asyncio.get_event_loop().time()
                            log.info(
                                "[OpenAICompat:%s] first_visible_delta total_latency=%.3fs stream_latency=%.3fs chars=%d",
                                request_id,
                                first_visible_delta_at - request_started_at,
                                first_visible_delta_at - stream_opened_at,
                                len(visible),
                        )
                        yield ApiTextDeltaEvent(text=visible)
        except Exception as exc:
            log.warning(
                "[OpenAICompat:%s] responses stream failed type=%s status=%s body=%s "
                "content_chars=%d reasoning_chars=%d tool_calls=%d finish_reason=%s message=%s",
                request_id,
                exc.__class__.__name__,
                getattr(exc, "status_code", None),
                getattr(exc, "body", None),
                len(collected_content),
                len(collected_reasoning),
                len(function_call_items),
                finish_reason,
                exc,
            )
            raise

        function_call_items.extend(item for item in chat_tool_calls.values() if item.get("name"))
        collected_tool_calls: list[ToolUseBlock] = []
        for item in function_call_items:
            streamed_arguments = _function_argument_for_item(item, function_call_arguments)
            if streamed_arguments:
                item = _response_item_with_arguments(item, streamed_arguments)
            tool_use = _tool_use_from_response_item(item)
            if tool_use:
                collected_tool_calls.append(tool_use)

        content: list[ContentBlock] = []
        if collected_content:
            content.append(TextBlock(text=collected_content))
        content.extend(collected_tool_calls)

        final_message = ConversationMessage(role="assistant", content=content)
        if collected_reasoning:
            final_message._reasoning = collected_reasoning  # type: ignore[attr-defined]

        log.info(
            "[OpenAICompat:%s] responses complete content_chars=%d reasoning_chars=%d tools=%d "
            "finish_reason=%s usage=%s",
            request_id,
            len(collected_content),
            len(collected_reasoning),
            len(collected_tool_calls),
            finish_reason,
            usage.model_dump(),
        )

        yield ApiMessageCompleteEvent(
            message=final_message,
            usage=usage,
            stop_reason=finish_reason,
        )

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status and status in {429, 500, 502, 503}:
            return True
        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            return True
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return True
        return False

    @staticmethod
    def _translate_error(exc: Exception) -> OpenHarnessApiError:
        status = getattr(exc, "status_code", None)
        msg = str(exc)
        if status == 401 or status == 403:
            return AuthenticationFailure(msg)
        if status == 429:
            return RateLimitFailure(msg)
        return RequestFailure(msg)


# Matches complete <think>…</think> blocks (DOTALL so newlines are included).
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_THINK_OPEN_TAG = "<think>"


def _strip_think_blocks(buf: str) -> tuple[str, str]:
    """Strip complete ``<think>…</think>`` blocks and return ``(visible_text, leftover)``.

    Complete pairs are removed via regex.  An unclosed ``<think>`` is held in
    *leftover* so it can be re-evaluated once the closing tag arrives in the
    next streaming chunk.
    """
    # Remove fully-closed blocks.
    cleaned = _THINK_RE.sub("", buf)

    # Hold back any unclosed <think> for the next chunk.
    open_idx = cleaned.find(_THINK_OPEN_TAG)
    if open_idx != -1:
        return cleaned[:open_idx], cleaned[open_idx:]

    # Streaming providers may split the opening tag itself across chunk
    # boundaries (e.g. ``"<thi"`` then ``"nk>..."``). Hold back the longest
    # suffix that could still become ``<think>`` on the next chunk.
    max_prefix = min(len(cleaned), len(_THINK_OPEN_TAG) - 1)
    for prefix_len in range(max_prefix, 0, -1):
        if _THINK_OPEN_TAG.startswith(cleaned[-prefix_len:]):
            return cleaned[:-prefix_len], cleaned[-prefix_len:]

    return cleaned, ""
