"""Tests for the query engine."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pytest

from openharness.api.client import (
    ApiMessageCompleteEvent,
    ApiRetryEvent,
    ApiTextDeltaEvent,
    ApiToolCallCompletedEvent,
    ApiToolCallProgressEvent,
    ApiToolCallStartedEvent,
)
from openharness.api.errors import RequestFailure
from openharness.api.usage import UsageSnapshot
from openharness.config.settings import PermissionSettings, Settings
from openharness.engine.messages import ConversationMessage, TextBlock, ToolUseBlock
from openharness.engine.query_engine import QueryEngine
from openharness.prompts.context import build_runtime_system_prompt
from openharness.engine.stream_events import (
    AgentProgressEvent,
    AssistantTextDelta,
    AssistantTurnComplete,
    CompactProgressEvent,
    ErrorEvent,
    StatusEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from openharness.permissions import PermissionChecker, PermissionMode
from openharness.tasks import get_task_manager
from openharness.tools import create_default_tool_registry
from openharness.tools.ask_user_question_tool import AskUserQuestionPaused
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolRegistry, ToolResult
from openharness.services.session_storage import load_session_events
from openharness.tools.glob_tool import GlobTool
from openharness.tools.grep_tool import GrepTool
from pydantic import BaseModel
from openharness.engine.messages import ToolResultBlock
from openharness.hooks import HookExecutionContext, HookExecutor, HookEvent
from openharness.hooks.loader import HookRegistry
from openharness.hooks.schemas import PromptHookDefinition
from openharness.engine.query import (
    QueryContext,
    _execute_tool_call,
    _is_prompt_too_long_error,
    _prepare_tool_call,
    _resolve_permission_file_path,
    _run_tool_with_progress,
    _tool_schemas_for_context,
)


@dataclass
class _FakeResponse:
    message: ConversationMessage
    usage: UsageSnapshot


class FakeApiClient:
    """Deterministic streaming client used by query tests."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)

    async def stream_message(self, request):
        del request
        response = self._responses.pop(0)
        for block in response.message.content:
            if isinstance(block, TextBlock) and block.text:
                yield ApiTextDeltaEvent(text=block.text)
        yield ApiMessageCompleteEvent(
            message=response.message,
            usage=response.usage,
            stop_reason=None,
        )


class StaticApiClient:
    """Fake client that always returns one fixed assistant message."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def stream_message(self, request):
        del request
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text=self._text)]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class RetryThenSuccessApiClient:
    async def stream_message(self, request):
        del request
        yield ApiRetryEvent(message="rate limited", attempt=1, max_attempts=4, delay_seconds=1.5)
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="after retry")]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class HostedToolThenSuccessApiClient:
    async def stream_message(self, request):
        del request
        yield ApiToolCallStartedEvent(
            tool_name="web_search",
            tool_use_id="ws_1",
            tool_input={"query": "today AI news"},
            message="正在准备网页搜索...",
            metadata={"provider_event_type": "response.web_search_call.in_progress"},
        )
        yield ApiToolCallProgressEvent(
            tool_name="web_search",
            tool_use_id="ws_1",
            message="正在搜索网页...",
            metadata={"provider_event_type": "response.web_search_call.searching"},
        )
        yield ApiToolCallCompletedEvent(
            tool_name="web_search",
            tool_use_id="ws_1",
            message="网页搜索完成",
            metadata={"result_count": 2},
        )
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="done")]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class _ImageGenerationHook:
    async def generate_image(self, request: dict, context_metadata: dict) -> dict:
        del request, context_metadata
        return {
            "media_billing_status": "recorded",
            "artifact_payloads": [{"artifact_id": "artifact-1", "url": "/artifacts/thread/image.png"}],
        }


class PromptTooLongThenSuccessApiClient:
    def __init__(self) -> None:
        self._calls = 0

    async def stream_message(self, request):
        self._calls += 1
        if self._calls == 1:
            raise RequestFailure("prompt too long")
        if self._calls == 2:
            yield ApiMessageCompleteEvent(
                message=ConversationMessage(role="assistant", content=[TextBlock(text="<summary>compressed</summary>")]),
                usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                stop_reason=None,
            )
            return
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="after reactive compact")]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class RecordingApiClient:
    def __init__(self, text: str = "ok") -> None:
        self.requests = []
        self._text = text

    async def stream_message(self, request):
        self.requests.append(request)
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text=self._text)]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class MaxTokensTooLargeThenSuccessApiClient:
    def __init__(self) -> None:
        self.requests = []

    async def stream_message(self, request):
        self.requests.append(request)
        if len(self.requests) == 1:
            raise RequestFailure(
                "max_tokens is too large: 120000. This model supports at most "
                "32000 completion tokens, whereas you provided 120000."
            )
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="after token clamp")]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class EmptyAssistantApiClient:
    async def stream_message(self, request):
        del request
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[]),
            usage=UsageSnapshot(input_tokens=1, output_tokens=1),
            stop_reason=None,
        )


class CoordinatorLoopApiClient:
    def __init__(self) -> None:
        self.requests = []
        self._calls = 0

    async def stream_message(self, request):
        self.requests.append(request)
        self._calls += 1
        if self._calls == 1:
            yield ApiMessageCompleteEvent(
                message=ConversationMessage(
                    role="assistant",
                    content=[
                        TextBlock(text="Launching a worker."),
                        ToolUseBlock(
                            id="toolu_agent_1",
                            name="agent",
                            input={
                                "description": "inspect coordinator wiring",
                                "prompt": "check whether coordinator mode is active",
                                "subagent_type": "worker",
                                "mode": "in_process_teammate",
                            },
                        ),
                    ],
                ),
                usage=UsageSnapshot(input_tokens=2, output_tokens=2),
                stop_reason=None,
            )
            return
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text="Worker launched; coordinator mode is active.")]),
            usage=UsageSnapshot(input_tokens=2, output_tokens=2),
            stop_reason=None,
        )


class _NoopApiClient:
    async def stream_message(self, request):
        del request
        if False:
            yield None


class HangingApiClient:
    """Fake client that keeps the model stream open until cancelled."""

    async def stream_message(self, request):
        del request
        try:
            while True:
                await asyncio.sleep(60)
        finally:
            return
        if False:
            yield None


def test_query_prompt_too_long_detection_handles_llama_cpp_errors():
    assert _is_prompt_too_long_error(
        RequestFailure("exceed_context_size_error: prompt exceeds the available context size")
    )


def test_query_prompt_too_long_detection_handles_openai_context_length_errors():
    assert _is_prompt_too_long_error(
        RequestFailure(
            "Input tokens exceed the configured limit of 922000 tokens. "
            "Your messages resulted in 3591869 tokens. Please reduce the length of the messages. "
            "code='context_length_exceeded'"
        )
    )


@pytest.mark.asyncio
async def test_query_engine_plain_text_reply(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="Hello from the model.")],
                    ),
                    usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                )
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("hello")]

    text_event = next(event for event in events if isinstance(event, AssistantTextDelta))
    assert text_event.text == "Hello from the model."
    assert isinstance(events[-1], AssistantTurnComplete)
    assert engine.total_usage.input_tokens == 10
    assert engine.total_usage.output_tokens == 5
    assert len(engine.messages) == 2


@pytest.mark.asyncio
async def test_query_engine_appends_session_event_log(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="Hello from the model.")],
                    ),
                    usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                )
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        tool_metadata={"session_id": "session-event-test"},
    )

    events = [event async for event in engine.submit_message("hello Authorization: Bearer abcdefghijklmnopqrstuvwxyz")]

    assert any(isinstance(event, AssistantTurnComplete) for event in events)
    records = load_session_events(tmp_path, "session-event-test")
    event_types = [record["event_type"] for record in records]
    serialized = json.dumps(records, ensure_ascii=False)
    assert "user_message_submitted" in event_types
    assert "assistant_text_delta" in event_types
    assert "assistant_turn_complete" in event_types
    assert "hello Authorization" not in serialized
    assert "Hello from the model." not in serialized
    assert "abcdefghijklmnopqrstuvwxyz" not in serialized
    turn_ids = {
        record["turn_id"]
        for record in records
        if record["event_type"] in {"assistant_text_delta", "assistant_turn_complete"}
    }
    assert len(turn_ids) == 1
    assert next(iter(turn_ids))


@pytest.mark.asyncio
async def test_query_engine_maps_provider_hosted_tool_events(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    engine = QueryEngine(
        api_client=HostedToolThenSuccessApiClient(),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="gpt-5.5",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("search")]

    started = next(event for event in events if isinstance(event, ToolExecutionStarted) and event.tool_name == "web_search")
    progress = [event for event in events if isinstance(event, AgentProgressEvent) and event.tool_name == "web_search"]
    completed = next(event for event in events if isinstance(event, ToolExecutionCompleted) and event.tool_name == "web_search")

    assert started.tool_use_id == "ws_1"
    assert started.tool_input == {"query": "today AI news"}
    assert any(event.message == "正在搜索网页..." for event in progress)
    assert completed.tool_use_id == "ws_1"
    assert completed.output == "网页搜索完成"
    assert completed.metadata == {"result_count": 2}
    assert isinstance(events[-1], AssistantTurnComplete)
    assert events[-1].message.text == "done"


@pytest.mark.asyncio
async def test_query_engine_splits_tool_rationale_from_undeclared_input(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    tool_call = ToolUseBlock(
        id="tool_image_1",
        name="generate_image",
        input={
            "purpose": "我会生成一张 3:4 的小猫图片，方便你查看生成结果。",
            "prompt": "Create a cute kitten photo.",
            "brief": {},
            "output": {"aspect_ratio": "3:4", "count": 1},
            "edit_policy": {},
            "text_policy": {},
        },
    )
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[tool_call]),
                    usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                ),
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="done")]),
                    usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("draw kitten")]

    started = next(event for event in events if isinstance(event, ToolExecutionStarted) and event.tool_name == "generate_image")
    completed = next(event for event in events if isinstance(event, ToolExecutionCompleted) and event.tool_name == "generate_image")
    saved_tool_call = engine.messages[1].tool_uses[0]

    assert started.rationale == "我会生成一张 3:4 的小猫图片，方便你查看生成结果。"
    assert "purpose" not in started.tool_input
    assert "purpose" not in saved_tool_call.input
    assert "invalid_canonical_request" not in completed.output


@pytest.mark.asyncio
async def test_query_engine_uses_assistant_text_as_tool_rationale(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    tool_call = ToolUseBlock(
        id="tool_image_2",
        name="generate_image",
        input={
            "prompt": "Create a product hero image.",
            "brief": {},
            "output": {"aspect_ratio": "16:9", "count": 1},
            "edit_policy": {},
            "text_policy": {},
        },
    )
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            TextBlock(text="我会生成一张产品主视觉图，方便你直接预览构图和风格。"),
                            tool_call,
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                ),
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="done")]),
                    usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("draw product hero")]

    started = next(event for event in events if isinstance(event, ToolExecutionStarted) and event.tool_name == "generate_image")

    assert started.rationale == "我会生成一张产品主视觉图，方便你直接预览构图和风格。"
    assert "purpose" not in started.tool_input


def test_tool_rationale_split_preserves_declared_purpose_field(tmp_path: Path):
    class PurposeInput(BaseModel):
        purpose: str

    class PurposeTool(BaseTool):
        name = "purpose_tool"
        description = "Tool with a real purpose input."
        input_model = PurposeInput

        async def execute(self, arguments, context):
            del context
            return ToolResult(arguments.purpose)

    registry = ToolRegistry()
    registry.register(PurposeTool())
    context = QueryContext(
        api_client=StaticApiClient("done"),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        max_tokens=1024,
    )
    tool_call = ToolUseBlock(name="purpose_tool", input={"purpose": "business value"})

    prepared = _prepare_tool_call(context, tool_call)

    assert prepared.rationale == "business value"
    assert prepared.tool_input == {"purpose": "business value"}
    assert tool_call.input == {"purpose": "business value"}


@pytest.mark.asyncio
async def test_query_engine_allows_generate_image_retry_after_canonical_object_error(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    bad_tool_call = ToolUseBlock(
        id="tool_image_bad",
        name="generate_image",
        input={
            "prompt": "Create a Facebook fan page banner.",
            "scenario": "marketing_or_social",
            "brief": {},
            "output": '{"width": 1200, "height": 628}',
            "edit_policy": {},
            "text_policy": '{"mode": "exact", "exact_text": "大航海时代"}',
        },
    )
    repaired_tool_call = ToolUseBlock(
        id="tool_image_fixed",
        name="generate_image",
        input={
            "prompt": "Create a Facebook fan page banner.",
            "scenario": "marketing_or_social",
            "brief": {},
            "output": {"width": 1200, "height": 628},
            "edit_policy": {},
            "text_policy": {"mode": "exact", "exact_text": "大航海时代"},
        },
    )
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[bad_tool_call]),
                    usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                ),
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[repaired_tool_call]),
                    usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                ),
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="done")]),
                    usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        tool_metadata={"hook": _ImageGenerationHook()},
    )

    events = [event async for event in engine.submit_message("draw banner")]

    completed = [event for event in events if isinstance(event, ToolExecutionCompleted) and event.tool_name == "generate_image"]
    assert len(completed) == 2
    assert completed[0].is_error is True
    assert "`output` must be an object, not a JSON string" in completed[0].output
    assert "Retry by calling generate_image again" in completed[0].output
    assert completed[1].is_error is False
    assert isinstance(events[-1], AssistantTurnComplete)
    assert events[-1].message.text == "done"


@pytest.mark.asyncio
async def test_query_engine_clamps_oversized_max_tokens_before_request(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    client = RecordingApiClient()
    engine = QueryEngine(
        api_client=client,
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="openai-compatible-model",
        system_prompt="system",
        max_tokens=400_000,
    )

    events = [event async for event in engine.submit_message("hello")]

    assert client.requests[0].max_tokens == 128_000
    assert any(isinstance(event, StatusEvent) and "safe per-request output cap" in event.message for event in events)
    assert isinstance(events[-1], AssistantTurnComplete)


@pytest.mark.asyncio
async def test_query_engine_retries_with_provider_completion_token_limit(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    client = MaxTokensTooLargeThenSuccessApiClient()
    engine = QueryEngine(
        api_client=client,
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="openai-compatible-model",
        system_prompt="system",
        max_tokens=120_000,
        max_turns=1,
    )

    events = [event async for event in engine.submit_message("hello")]

    assert [request.max_tokens for request in client.requests] == [120_000, 32_000]
    assert any(isinstance(event, StatusEvent) and "provider limit 32000" in event.message for event in events)
    assert isinstance(events[-1], AssistantTurnComplete)


@pytest.mark.asyncio
async def test_query_engine_executes_tool_calls(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    sample = tmp_path / "hello.txt"
    sample.write_text("alpha\nbeta\n", encoding="utf-8")

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            TextBlock(text="I will inspect the file."),
                            ToolUseBlock(
                                id="toolu_123",
                                name="read_file",
                                input={"path": str(sample), "offset": 0, "limit": 2},
                            ),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=4, output_tokens=3),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="The file contains alpha and beta.")],
                    ),
                    usage=UsageSnapshot(input_tokens=8, output_tokens=6),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("read the file")]

    assert any(isinstance(event, ToolExecutionStarted) for event in events)
    tool_results = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert len(tool_results) == 1
    assert "alpha" in tool_results[0].output
    assert isinstance(events[-1], AssistantTurnComplete)
    assert "alpha and beta" in events[-1].message.text
    assert len(engine.messages) == 4


@pytest.mark.asyncio
async def test_query_engine_coordinator_mode_uses_coordinator_prompt_and_runs_agent_loop(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_CODE_COORDINATOR_MODE", "1")

    api_client = CoordinatorLoopApiClient()
    system_prompt = build_runtime_system_prompt(Settings(), cwd=tmp_path, latest_user_prompt="investigate issue")
    engine = QueryEngine(
        api_client=api_client,
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt=system_prompt,
    )

    events = [event async for event in engine.submit_message("investigate issue")]

    assert len(api_client.requests) == 2
    assert "You are a **coordinator**." in api_client.requests[0].system_prompt
    assert "Coordinator User Context" not in api_client.requests[0].system_prompt
    coordinator_context_messages = [
        msg for msg in api_client.requests[0].messages if msg.role == "user" and "Coordinator User Context" in msg.text
    ]
    assert len(coordinator_context_messages) == 1
    assert "Workers spawned via the agent tool have access to these tools" in coordinator_context_messages[0].text
    assert any(isinstance(event, ToolExecutionStarted) and event.tool_name == "agent" for event in events)
    agent_results = [event for event in events if isinstance(event, ToolExecutionCompleted) and event.tool_name == "agent"]
    assert len(agent_results) == 1
    assert isinstance(events[-1], AssistantTurnComplete)
    assert "coordinator mode is active" in events[-1].message.text


@pytest.mark.asyncio
async def test_query_engine_allows_unbounded_turns_when_max_turns_is_none(tmp_path: Path):
    sample = tmp_path / "hello.txt"
    sample.write_text("alpha\nbeta\n", encoding="utf-8")

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            TextBlock(text="I will inspect the file."),
                            ToolUseBlock(
                                id="toolu_123",
                                name="read_file",
                                input={"path": str(sample), "offset": 0, "limit": 2},
                            ),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=4, output_tokens=3),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="The file contains alpha and beta.")],
                    ),
                    usage=UsageSnapshot(input_tokens=8, output_tokens=6),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        max_turns=None,
    )

    events = [event async for event in engine.submit_message("read the file")]

    assert isinstance(events[-1], AssistantTurnComplete)
    assert "alpha and beta" in events[-1].message.text
    assert engine.max_turns is None


@pytest.mark.asyncio
async def test_query_engine_surfaces_retry_status_events(tmp_path: Path):
    engine = QueryEngine(
        api_client=RetryThenSuccessApiClient(),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("hello")]

    assert any(isinstance(event, StatusEvent) and "retrying in 1.5s" in event.message for event in events)
    assert isinstance(events[-1], AssistantTurnComplete)


@pytest.mark.asyncio
async def test_query_engine_emits_compact_progress_before_reply(tmp_path: Path, monkeypatch):
    long_text = "alpha " * 50000
    monkeypatch.setattr("openharness.services.compact.try_session_memory_compaction", lambda *args, **kwargs: None)
    monkeypatch.setattr("openharness.services.compact.should_autocompact", lambda *args, **kwargs: True)
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="<summary>trimmed</summary>")]),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="after compact")]),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-sonnet-4-6",
        system_prompt="system",
    )
    engine.load_messages(
        [
            ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="user", content=[TextBlock(text=long_text)]),
            ConversationMessage(role="assistant", content=[TextBlock(text=long_text)]),
        ]
    )

    events = [event async for event in engine.submit_message("hello")]

    hooks_start_index = next(i for i, event in enumerate(events) if isinstance(event, CompactProgressEvent) and event.phase == "hooks_start")
    compact_start_index = next(i for i, event in enumerate(events) if isinstance(event, CompactProgressEvent) and event.phase == "compact_start")
    final_index = next(i for i, event in enumerate(events) if isinstance(event, AssistantTurnComplete))
    assert hooks_start_index < compact_start_index
    assert compact_start_index < final_index
    assert any(isinstance(event, CompactProgressEvent) and event.phase == "compact_end" for event in events)


@pytest.mark.asyncio
async def test_query_engine_reactive_compacts_after_prompt_too_long(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("openharness.services.compact.try_session_memory_compaction", lambda *args, **kwargs: None)
    monkeypatch.setattr("openharness.services.compact.should_autocompact", lambda *args, **kwargs: False)
    engine = QueryEngine(
        api_client=PromptTooLongThenSuccessApiClient(),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )
    engine.load_messages(
        [
            ConversationMessage(role="user", content=[TextBlock(text="one")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="two")]),
            ConversationMessage(role="user", content=[TextBlock(text="three")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="four")]),
            ConversationMessage(role="user", content=[TextBlock(text="five")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="six")]),
            ConversationMessage(role="user", content=[TextBlock(text="seven")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="eight")]),
        ]
    )

    events = [event async for event in engine.submit_message("nine")]

    assert any(
        isinstance(event, CompactProgressEvent)
        and event.trigger == "reactive"
        and event.phase == "compact_start"
        for event in events
    )
    assert isinstance(events[-1], AssistantTurnComplete)
    assert events[-1].message.text == "after reactive compact"


@pytest.mark.asyncio
async def test_query_engine_tracks_recent_read_files_and_skills(tmp_path: Path):
    sample = tmp_path / "hello.txt"
    sample.write_text("alpha\nbeta\n", encoding="utf-8")
    registry = create_default_tool_registry()
    skill_tool = registry.get("skill")
    assert skill_tool is not None

    async def _fake_skill_execute(arguments, context):
        del context
        return ToolResult(output=f"Loaded skill: {arguments.name}")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(skill_tool, "execute", _fake_skill_execute)

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(name="read_file", input={"path": str(sample)}),
                            ToolUseBlock(name="skill", input={"name": "demo-skill"}),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="done")]),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        tool_metadata={},
    )

    try:
        events = [event async for event in engine.submit_message("track context")]
    finally:
        monkeypatch.undo()

    assert isinstance(events[-1], AssistantTurnComplete)
    read_state = engine._tool_metadata.get("read_file_state")
    assert isinstance(read_state, list) and read_state
    assert read_state[-1]["path"] == str(sample.resolve())
    assert "alpha" in read_state[-1]["preview"]
    task_focus = engine.tool_metadata.get("task_focus_state")
    assert isinstance(task_focus, dict)
    assert "track context" in task_focus.get("goal", "")
    assert str(sample.resolve()) in task_focus.get("active_artifacts", [])
    invoked_skills = engine._tool_metadata.get("invoked_skills")
    assert isinstance(invoked_skills, list)
    assert invoked_skills[-1] == "demo-skill"
    verified = engine.tool_metadata.get("recent_verified_work")
    assert isinstance(verified, list)
    assert any("Inspected file" in entry for entry in verified)
    assert any("Loaded skill demo-skill" in entry for entry in verified)


@pytest.mark.asyncio
async def test_query_engine_tracks_async_agent_activity(tmp_path: Path, monkeypatch):
    registry = create_default_tool_registry()
    agent_tool = registry.get("agent")
    assert agent_tool is not None

    async def _fake_execute(arguments, context):
        del arguments, context
        return ToolResult(output="Spawned agent worker@team (task_id=task_123, backend=subprocess)")

    monkeypatch.setattr(agent_tool, "execute", _fake_execute)
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                name="agent",
                                input={"description": "Inspect CI", "prompt": "Inspect CI"},
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="spawned")]),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        tool_metadata={},
    )

    events = [event async for event in engine.submit_message("spawn helper")]

    assert isinstance(events[-1], AssistantTurnComplete)
    async_state = engine._tool_metadata.get("async_agent_state")
    assert isinstance(async_state, list)
    assert async_state[-1].startswith("Spawned async agent")
    async_tasks = engine._tool_metadata.get("async_agent_tasks")
    assert isinstance(async_tasks, list)
    assert async_tasks[-1]["agent_id"] == "worker@team"
    assert async_tasks[-1]["task_id"] == "task_123"
    assert async_tasks[-1]["notification_sent"] is False


@pytest.mark.asyncio
async def test_query_engine_respects_pre_tool_hook_blocks(tmp_path: Path):
    sample = tmp_path / "hello.txt"
    sample.write_text("alpha\n", encoding="utf-8")
    registry = HookRegistry()
    registry.register(
        HookEvent.PRE_TOOL_USE,
        PromptHookDefinition(prompt="reject", matcher="read_file"),
    )

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_999",
                                name="read_file",
                                input={"path": str(sample)},
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="blocked")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        hook_executor=HookExecutor(
            registry,
            HookExecutionContext(
                cwd=tmp_path,
                api_client=StaticApiClient('{"ok": false, "reason": "no reading"}'),
                default_model="claude-test",
            ),
        ),
    )

    events = [event async for event in engine.submit_message("read file")]

    tool_results = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert tool_results
    assert tool_results[0].is_error is True
    assert "no reading" in tool_results[0].output


class _RecordingHookExecutor:
    """Duck-typed hook executor that records every fired event + payload."""

    def __init__(self) -> None:
        self.calls: list[tuple[HookEvent, dict]] = []

    async def execute(self, event: HookEvent, payload: dict):
        from openharness.hooks.types import AggregatedHookResult

        self.calls.append((event, dict(payload)))
        return AggregatedHookResult(results=[])


@pytest.mark.asyncio
async def test_user_prompt_submit_hook_fires(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    recorder = _RecordingHookExecutor()
    engine = QueryEngine(
        api_client=StaticApiClient("done"),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        hook_executor=recorder,  # type: ignore[arg-type]
    )

    _ = [event async for event in engine.submit_message("hello world")]

    user_prompt_calls = [c for c in recorder.calls if c[0] == HookEvent.USER_PROMPT_SUBMIT]
    assert len(user_prompt_calls) == 1
    assert user_prompt_calls[0][1]["event"] == "user_prompt_submit"
    assert user_prompt_calls[0][1]["prompt"] == "hello world"


@pytest.mark.asyncio
async def test_stop_hook_fires_on_clean_turn(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    recorder = _RecordingHookExecutor()
    engine = QueryEngine(
        api_client=StaticApiClient("all done"),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        hook_executor=recorder,  # type: ignore[arg-type]
    )

    _ = [event async for event in engine.submit_message("hi")]

    stop_calls = [c for c in recorder.calls if c[0] == HookEvent.STOP]
    assert len(stop_calls) == 1
    assert stop_calls[0][1]["event"] == "stop"
    assert stop_calls[0][1]["stop_reason"] == "tool_uses_empty"


@pytest.mark.asyncio
async def test_stop_hook_does_not_fire_when_tool_uses_present(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    sample = tmp_path / "hello.txt"
    sample.write_text("alpha\n", encoding="utf-8")
    recorder = _RecordingHookExecutor()
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_1",
                                name="read_file",
                                input={"path": str(sample), "offset": 0, "limit": 1},
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="wrapped up")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        hook_executor=recorder,  # type: ignore[arg-type]
    )

    _ = [event async for event in engine.submit_message("read the file")]

    stop_calls = [c for c in recorder.calls if c[0] == HookEvent.STOP]
    # STOP fires exactly once — at the end of the second turn (no tool_uses),
    # NOT after the first turn that contained a tool_use.
    assert len(stop_calls) == 1


@pytest.mark.asyncio
async def test_notification_hook_fires_on_permission_prompt(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    recorder = _RecordingHookExecutor()
    prompt_tool_calls: list[tuple[str, str]] = []

    async def _permission_prompt(tool_name: str, reason: str) -> bool:
        prompt_tool_calls.append((tool_name, reason))
        # Assert the NOTIFICATION hook fired before this callback was invoked.
        notif = [c for c in recorder.calls if c[0] == HookEvent.NOTIFICATION]
        assert notif, "notification hook must fire before permission prompt"
        return False  # deny — keeps the turn short

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_bash_1",
                                name="bash",
                                input={"command": "echo hi"},
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="denied")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.DEFAULT)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        permission_prompt=_permission_prompt,
        hook_executor=recorder,  # type: ignore[arg-type]
    )

    _ = [event async for event in engine.submit_message("run something")]

    notification_calls = [c for c in recorder.calls if c[0] == HookEvent.NOTIFICATION]
    assert len(notification_calls) == 1
    payload = notification_calls[0][1]
    assert payload["event"] == "notification"
    assert payload["notification_type"] == "permission_prompt"
    assert payload["tool_name"] == "bash"
    # The permission prompt callback was invoked (confirms the hook fired on the
    # correct branch, not on the silently-denied branch).
    assert prompt_tool_calls


@pytest.mark.asyncio
async def test_subagent_stop_hook_fires_when_spawned_agent_finishes(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    recorder = _RecordingHookExecutor()
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_agent_1",
                                name="agent",
                                input={
                                    "description": "quick worker run",
                                    "prompt": "ready",
                                    "subagent_type": "worker",
                                    "mode": "local_agent",
                                    "command": 'python -u -c "import sys; print(sys.stdin.readline().strip())"',
                                },
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=2, output_tokens=2),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="worker done")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        hook_executor=recorder,  # type: ignore[arg-type]
    )

    _ = [event async for event in engine.submit_message("run a worker")]

    manager = get_task_manager()
    deadline = asyncio.get_running_loop().time() + 2.0
    while asyncio.get_running_loop().time() < deadline:
        subagent_stop_calls = [c for c in recorder.calls if c[0] == HookEvent.SUBAGENT_STOP]
        if subagent_stop_calls:
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("subagent_stop hook did not fire")

    subagent_stop_calls = [c for c in recorder.calls if c[0] == HookEvent.SUBAGENT_STOP]
    assert len(subagent_stop_calls) == 1
    payload = subagent_stop_calls[0][1]
    assert payload["event"] == "subagent_stop"
    assert payload["agent_id"] == "worker@default"
    assert payload["subagent_type"] == "worker"
    assert payload["mode"] == "local_agent"
    assert payload["status"] == "completed"
    assert payload["return_code"] == 0

    task = manager.get_task(payload["task_id"])
    assert task is not None
    assert task.status == "completed"


def _tool_context(
    tmp_path: Path,
    registry: ToolRegistry,
    settings: PermissionSettings,
    tool_metadata: dict[str, object] | None = None,
) -> QueryContext:
    return QueryContext(
        api_client=_NoopApiClient(),
        tool_registry=registry,
        permission_checker=PermissionChecker(settings),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        max_tokens=1,
        max_turns=1,
        tool_metadata=tool_metadata,
    )


def _schema_names_for_context(context: QueryContext) -> set[str]:
    return {str(schema.get("name") or "") for schema in _tool_schemas_for_context(context)}


@pytest.mark.asyncio
async def test_run_tool_with_progress_returns_without_waiting_for_heartbeat(tmp_path: Path, monkeypatch, caplog):
    async def _fake_execute_tool_call(
        context: QueryContext,
        tool_name: str,
        tool_use_id: str,
        tool_input: dict[str, object],
        *,
        progress_callback=None,
    ) -> ToolResultBlock:
        del context, tool_input
        assert progress_callback is not None
        await progress_callback(
            {
                "phase": "tool_progress",
                "message": "started",
                "tool_name": tool_name,
                "tool_use_id": tool_use_id,
            }
        )
        await asyncio.sleep(0)
        return ToolResultBlock(tool_use_id=tool_use_id, content="ok", is_error=False)

    monkeypatch.setattr("openharness.engine.query._execute_tool_call", _fake_execute_tool_call)
    monkeypatch.setattr("openharness.engine.query.AGENT_PROGRESS_HEARTBEAT_SECONDS", 60.0)
    caplog.set_level(logging.DEBUG, logger="openharness.engine.query")

    context = _tool_context(tmp_path, ToolRegistry(), PermissionSettings(mode=PermissionMode.FULL_AUTO))

    async def _collect():
        events = []
        async for event, result in _run_tool_with_progress(context, "fast_tool", "toolu_fast", {}):
            events.append((event, result))
        return events

    events = await asyncio.wait_for(_collect(), timeout=0.5)

    progress_events = [event for event, result in events if isinstance(event, AgentProgressEvent)]
    results = [result for event, result in events if isinstance(result, ToolResultBlock)]
    assert [event.phase for event in progress_events] == ["tool_progress"]
    assert progress_events[0].message == "started"
    assert len(results) == 1
    assert results[0].content == "ok"
    assert results[0].result_metadata == {}
    assert any(
        record.message.startswith("tool progress wait complete: name=fast_tool")
        and "heartbeats=0" in record.message
        and "progress_events=1" in record.message
        and "pending_progress=0" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_run_tool_with_progress_emits_observable_heartbeat_metadata(tmp_path: Path, monkeypatch, caplog):
    async def _fake_execute_tool_call(
        context: QueryContext,
        tool_name: str,
        tool_use_id: str,
        tool_input: dict[str, object],
        *,
        progress_callback=None,
    ) -> ToolResultBlock:
        del context, tool_name, tool_input, progress_callback
        await asyncio.sleep(0.1)
        return ToolResultBlock(tool_use_id=tool_use_id, content="ok", is_error=False)

    monkeypatch.setattr("openharness.engine.query._execute_tool_call", _fake_execute_tool_call)
    monkeypatch.setattr("openharness.engine.query.AGENT_PROGRESS_HEARTBEAT_SECONDS", 0.02)
    caplog.set_level(logging.DEBUG, logger="openharness.engine.query")

    context = _tool_context(tmp_path, ToolRegistry(), PermissionSettings(mode=PermissionMode.FULL_AUTO))

    events = []
    async for event, result in _run_tool_with_progress(context, "slow_tool", "toolu_slow", {}):
        events.append((event, result))

    heartbeat_events = [
        event for event, result in events if isinstance(event, AgentProgressEvent) and event.phase == "heartbeat"
    ]
    results = [result for event, result in events if isinstance(result, ToolResultBlock)]
    assert heartbeat_events
    assert heartbeat_events[0].metadata is not None
    assert heartbeat_events[0].metadata["engine_heartbeat_count"] == 1
    assert heartbeat_events[0].metadata["engine_elapsed_seconds"] >= 0
    assert len(results) == 1
    assert results[0].result_metadata == {}
    assert any(
        record.message.startswith("tool progress wait complete: name=slow_tool")
        and f"heartbeats={len(heartbeat_events)}" in record.message
        and "progress_events=0" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_query_engine_agent_progress_includes_turn_timing_metadata(tmp_path: Path):
    engine = QueryEngine(
        api_client=StaticApiClient("done"),
        tool_registry=ToolRegistry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("hello")]

    progress = [event for event in events if isinstance(event, AgentProgressEvent)]
    phases = {event.phase for event in progress}
    assert {"turn_start", "model_request", "model_response", "turn_complete"}.issubset(phases)
    turn_complete = next(event for event in progress if event.phase == "turn_complete")
    assert turn_complete.metadata is not None
    assert str(turn_complete.metadata["turn_id"]).startswith("turn_")
    assert turn_complete.metadata["turn_index"] == 1
    assert turn_complete.metadata["event_seq"] >= 1
    assert turn_complete.metadata["elapsed_ms"] >= 0
    assert turn_complete.metadata["usage"]["output_tokens"] == 1


@pytest.mark.asyncio
async def test_query_engine_request_cancel_aborts_waiting_model_stream(tmp_path: Path):
    engine = QueryEngine(
        api_client=HangingApiClient(),
        tool_registry=ToolRegistry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )
    events: list[object] = []

    async def _collect() -> None:
        async for event in engine.submit_message("wait"):
            events.append(event)

    task = asyncio.create_task(_collect())
    deadline = asyncio.get_running_loop().time() + 1.0
    while asyncio.get_running_loop().time() < deadline:
        if any(isinstance(event, AgentProgressEvent) and event.phase == "model_request" for event in events):
            break
        await asyncio.sleep(0.01)
    else:
        task.cancel()
        raise AssertionError("model_request progress was not emitted")

    engine.request_cancel("user requested stop")
    await asyncio.wait_for(task, timeout=1.0)

    aborted = [event for event in events if isinstance(event, AgentProgressEvent) and event.phase == "turn_aborted"]
    assert aborted
    assert aborted[-1].metadata is not None
    assert aborted[-1].metadata["reason"] == "user requested stop"
    assert aborted[-1].metadata["stage"] == "model_stream"


@pytest.mark.asyncio
async def test_query_engine_serializes_workspace_write_tools_with_execution_group(tmp_path: Path):
    class DelayInput(BaseModel):
        label: str

    class SerialWriteTool(BaseTool):
        name = "write_file"
        description = "Synthetic write tool used to test dispatch serialization."
        input_model = DelayInput

        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0

        async def execute(self, arguments, context):
            del context
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.05)
            self.active -= 1
            return ToolResult(arguments.label, metadata={"label": arguments.label})

    tool = SerialWriteTool()
    registry = ToolRegistry()
    registry.register(tool)
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(id="toolu_write_a", name="write_file", input={"label": "a"}),
                            ToolUseBlock(id="toolu_write_b", name="write_file", input={"label": "b"}),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="done")]),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("write twice")]

    assert tool.max_active == 1
    dispatch_events = [
        event for event in events if isinstance(event, AgentProgressEvent) and event.phase == "tool_dispatch"
    ]
    assert len(dispatch_events) == 2
    assert all(event.metadata and event.metadata["execution_group"] == "workspace_write" for event in dispatch_events)


def test_tool_schemas_for_context_prunes_heavy_default_tools(tmp_path: Path):
    registry = create_default_tool_registry()
    context = _tool_context(tmp_path, registry, PermissionSettings(mode=PermissionMode.DEFAULT))

    names = _schema_names_for_context(context)

    assert {"bash", "read_file", "write_file", "edit_file", "deliver_artifact", "skill"}.issubset(names)
    assert "ask_user_form" in names
    assert "ask_user_question" in names
    assert "generate_image" not in names
    assert "generate_video" not in names
    assert "canvas_get_state" not in names
    assert "cron_create" not in names
    assert "task_create" not in names
    assert "agent" not in names


def test_tool_schemas_for_context_includes_media_for_explicit_skill(tmp_path: Path):
    registry = create_default_tool_registry()
    context = _tool_context(
        tmp_path,
        registry,
        PermissionSettings(mode=PermissionMode.DEFAULT),
        tool_metadata={"selected_skill_ids": ["imagegen"]},
    )

    names = _schema_names_for_context(context)

    assert "generate_image" in names
    assert "generate_video" in names
    assert "canvas_get_state" not in names


def test_tool_schemas_for_context_includes_media_after_video_skill_invocation(tmp_path: Path):
    registry = create_default_tool_registry()
    context = _tool_context(
        tmp_path,
        registry,
        PermissionSettings(mode=PermissionMode.DEFAULT),
        tool_metadata={"invoked_skills": ["video_gen"]},
    )

    names = _schema_names_for_context(context)

    assert "generate_video" in names
    assert "generate_image" in names
    assert "tool_search" in names
    assert "canvas_generate_video" not in names


def test_tool_schemas_for_context_includes_connector_tools_only_when_selected(tmp_path: Path):
    class ConnectorArgs(BaseModel):
        value: str = ""

    class ConnectorTool(BaseTool):
        name = "connector__feishu__read_doc"
        description = "Read a Feishu doc."
        input_model = ConnectorArgs

        async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
            return ToolResult("ok")

    registry = ToolRegistry()
    registry.register(ConnectorTool())

    hidden = _schema_names_for_context(
        _tool_context(tmp_path, registry, PermissionSettings(mode=PermissionMode.DEFAULT))
    )
    visible = _schema_names_for_context(
        _tool_context(
            tmp_path,
            registry,
            PermissionSettings(mode=PermissionMode.DEFAULT),
            tool_metadata={"selected_connector_ids": ["feishu"]},
        )
    )

    assert "connector__feishu__read_doc" not in hidden
    assert "connector__feishu__read_doc" in visible


def test_tool_schemas_for_context_blocks_schedule_tools_during_scheduled_run(tmp_path: Path):
    registry = create_default_tool_registry()
    context = _tool_context(
        tmp_path,
        registry,
        PermissionSettings(mode=PermissionMode.DEFAULT),
        tool_metadata={
            "selected_skill_ids": ["automation-and-scheduling"],
            "scheduled_run": {"scheduled_run_id": "run_1", "allow_schedule_management": False},
        },
    )

    names = _schema_names_for_context(context)

    assert "cron_create" not in names
    assert "cron_list" not in names
    assert "cron_delete" not in names
    assert "cron_toggle" not in names
    assert "remote_trigger" not in names


@pytest.mark.asyncio
async def test_execute_tool_call_blocks_sensitive_directory_roots(tmp_path: Path):
    sensitive_dir = tmp_path / ".ssh"
    sensitive_dir.mkdir()
    (sensitive_dir / "id_rsa").write_text("PRIVATE KEY MATERIAL\n", encoding="utf-8")

    registry = ToolRegistry()
    registry.register(GrepTool())

    result = await _execute_tool_call(
        _tool_context(tmp_path, registry, PermissionSettings(mode=PermissionMode.DEFAULT)),
        "grep",
        "toolu_grep",
        {"pattern": "PRIVATE", "root": str(sensitive_dir), "file_glob": "*"},
    )

    assert result.is_error is True
    assert "sensitive credential path" in result.content


@pytest.mark.asyncio
async def test_execute_tool_call_applies_path_rules_to_directory_roots(tmp_path: Path):
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    (blocked_dir / "secret.txt").write_text("classified\n", encoding="utf-8")

    registry = ToolRegistry()
    registry.register(GlobTool())

    result = await _execute_tool_call(
        _tool_context(
            tmp_path,
            registry,
            PermissionSettings(
                mode=PermissionMode.DEFAULT,
                path_rules=[{"pattern": str(blocked_dir) + "/*", "allow": False}],
            ),
        ),
        "glob",
        "toolu_glob",
        {"pattern": "*", "root": str(blocked_dir)},
    )

    assert result.is_error is True
    assert str(blocked_dir) in result.content


@pytest.mark.asyncio
async def test_execute_tool_call_returns_actionable_reason_when_user_denies_confirmation(tmp_path: Path):
    async def _deny(_tool_name: str, _reason: str) -> bool:
        return False

    result = await _execute_tool_call(
        QueryContext(
            api_client=_NoopApiClient(),
            tool_registry=create_default_tool_registry(),
            permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.DEFAULT)),
            cwd=tmp_path,
            model="claude-test",
            system_prompt="system",
            max_tokens=1,
            max_turns=1,
            permission_prompt=_deny,
        ),
        "bash",
        "toolu_bash",
        {"command": "mkdir -p scratch-dir"},
    )

    assert result.is_error is True
    assert "Mutating tools require user confirmation" in result.content
    assert "/permissions full_auto" in result.content


@pytest.mark.asyncio
async def test_query_engine_executes_ask_user_tool(tmp_path: Path):
    async def _answer(question: str) -> str:
        assert question == "Which color?"
        return "green"

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_ask",
                                name="ask_user_question",
                                input={"question": "Which color?"},
                            ),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="Picked green.")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        ask_user_prompt=_answer,
    )

    events = [event async for event in engine.submit_message("pick a color")]

    tool_results = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert tool_results
    assert tool_results[0].output == "green"
    assert isinstance(events[-1], AssistantTurnComplete)
    assert events[-1].message.text == "Picked green."


@pytest.mark.asyncio
async def test_query_engine_normalizes_ask_user_question_option_values(tmp_path: Path):
    async def _answer(payload):
        assert payload["questions"][1]["options"][0]["value"] == "5"
        assert payload["questions"][2]["options"][0]["value"] == "true"
        return "5"

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_ask",
                                name="ask_user_question",
                                input={
                                    "questions": [
                                        {
                                            "id": "aspect_ratio",
                                            "question": "Which aspect ratio?",
                                            "options": [
                                                {"label": "Portrait", "value": "9:16", "recommended": True},
                                                {"label": "Landscape", "value": "16:9"},
                                            ],
                                        },
                                        {
                                            "id": "duration",
                                            "question": "How long?",
                                            "options": [
                                                {"label": "Short", "value": 5, "recommended": True},
                                                {"label": "Long", "value": 10},
                                            ],
                                        },
                                        {
                                            "id": "audio",
                                            "question": "Need audio?",
                                            "options": [
                                                {"label": "Yes", "value": True, "recommended": True},
                                                {"label": "No", "value": False},
                                            ],
                                        },
                                    ]
                                },
                            ),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="Done.")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        ask_user_prompt=_answer,
        tool_metadata={"ask_user_prompt_accepts_structured": True},
    )

    events = [event async for event in engine.submit_message("pick video options")]

    tool_results = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert tool_results
    assert tool_results[0].output == "5"
    assert isinstance(events[-1], AssistantTurnComplete)
    assert events[-1].message.text == "Done."


@pytest.mark.asyncio
async def test_query_engine_propagates_ask_user_pause(tmp_path: Path):
    async def _pause(_payload):
        raise AskUserQuestionPaused("paused")

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_ask",
                                name="ask_user_question",
                                input={"question": "Which color?"},
                            ),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        ask_user_prompt=_pause,
        tool_metadata={"ask_user_prompt_accepts_structured": True},
    )

    events = []
    with pytest.raises(AskUserQuestionPaused):
        async for event in engine.submit_message("pick a color"):
            events.append(event)

    assert any(isinstance(event, ToolExecutionStarted) for event in events)
    assert not any(isinstance(event, ToolExecutionCompleted) for event in events)


@pytest.mark.asyncio
async def test_query_engine_emits_completed_parallel_tools_before_ask_user_pause(tmp_path: Path):
    sample = tmp_path / "context.txt"
    sample.write_text("artifact delivered\n", encoding="utf-8")

    async def _pause(_payload):
        raise AskUserQuestionPaused("paused")

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_read",
                                name="read_file",
                                input={"path": str(sample), "offset": 0, "limit": 10},
                            ),
                            ToolUseBlock(
                                id="toolu_ask",
                                name="ask_user_question",
                                input={"question": "Continue?"},
                            ),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings()),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        ask_user_prompt=_pause,
        tool_metadata={"ask_user_prompt_accepts_structured": True},
    )

    events = []
    with pytest.raises(AskUserQuestionPaused):
        async for event in engine.submit_message("read then ask"):
            events.append(event)

    completed = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert len(completed) == 1
    assert completed[0].tool_name == "read_file"
    assert "artifact delivered" in completed[0].output


@pytest.mark.asyncio
async def test_query_engine_applies_path_rules_to_relative_read_file_targets(tmp_path: Path):
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    secret = blocked_dir / "secret.txt"
    secret.write_text("top-secret\n", encoding="utf-8")

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_blocked_read",
                                name="read_file",
                                input={"path": "blocked/secret.txt", "offset": 0, "limit": 1},
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="blocked")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(
            PermissionSettings(
                mode=PermissionMode.DEFAULT,
                path_rules=[{"pattern": str((blocked_dir / "*").resolve()), "allow": False}],
            )
        ),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("read blocked file")]

    tool_results = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert tool_results
    assert tool_results[0].is_error is True
    assert "matches deny rule" in tool_results[0].output


def test_permission_path_resolution_accepts_posix_cwd_on_windows():
    cwd = PurePosixPath("D:/workspace/project")

    resolved = _resolve_permission_file_path(
        cwd,
        {"path": "uploads/example.log"},
        object(),
    )

    assert resolved == str((Path("D:/workspace/project") / "uploads/example.log").resolve())


def test_permission_path_resolution_accepts_posix_root_on_windows():
    cwd = PurePosixPath("D:/workspace/project")

    resolved = _resolve_permission_file_path(
        cwd,
        {"root": "uploads"},
        object(),
    )

    assert resolved == str((Path("D:/workspace/project") / "uploads").resolve())


@pytest.mark.asyncio
async def test_tool_execution_accepts_posix_cwd_on_windows(tmp_path: Path):
    sample = tmp_path / "uploads" / "example.log"
    sample.parent.mkdir()
    sample.write_text("image generation complete\n", encoding="utf-8")
    context = QueryContext(
        api_client=FakeApiClient([]),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=PurePosixPath(str(tmp_path).replace("\\", "/")),
        model="claude-test",
        system_prompt="system",
        max_tokens=128,
    )

    result = await _execute_tool_call(
        context,
        "read_file",
        "toolu_read",
        {"path": "uploads/example.log", "offset": 0, "limit": 1},
    )

    assert result.is_error is False
    assert "image generation complete" in result.content


@pytest.mark.asyncio
async def test_query_engine_applies_path_rules_to_write_file_targets_in_full_auto(tmp_path: Path):
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    target = blocked_dir / "output.txt"

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_blocked_write",
                                name="write_file",
                                input={"path": "blocked/output.txt", "content": "poc"},
                            )
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="blocked")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(
            PermissionSettings(
                mode=PermissionMode.FULL_AUTO,
                path_rules=[{"pattern": str((blocked_dir / "*").resolve()), "allow": False}],
            )
        ),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("write blocked file")]

    tool_results = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert tool_results
    assert tool_results[0].is_error is True
    assert "matches deny rule" in tool_results[0].output
    assert target.exists() is False


class _OkInput(BaseModel):
    pass


class _OkTool(BaseTool):
    name = "ok_tool"
    description = "Returns success."
    input_model = _OkInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        del arguments, context
        return ToolResult(output="ok", metadata={"sentinel": "metadata"})


class _BoomTool(BaseTool):
    name = "boom_tool"
    description = "Always raises."
    input_model = _OkInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        del arguments, context
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_query_engine_synthesizes_tool_result_when_single_tool_raises(tmp_path: Path):
    registry = ToolRegistry()
    registry.register(_BoomTool())

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            TextBlock(text="Running one tool."),
                            ToolUseBlock(id="toolu_boom", name="boom_tool", input={}),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="Recovered from the failure.")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("run one tool")]

    completed = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert len(completed) == 1
    assert completed[0].tool_name == "boom_tool"
    assert completed[0].is_error is True
    assert "RuntimeError" in completed[0].output
    assert "boom" in completed[0].output

    user_tool_messages = [
        msg
        for msg in engine.messages
        if msg.role == "user" and any(isinstance(block, ToolResultBlock) for block in msg.content)
    ]
    assert len(user_tool_messages) == 1
    result_blocks = [
        block for block in user_tool_messages[0].content if isinstance(block, ToolResultBlock)
    ]
    assert result_blocks[0].tool_use_id == "toolu_boom"

    assert isinstance(events[-1], AssistantTurnComplete)
    assert events[-1].message.text == "Recovered from the failure."


class _LargeOutputTool(BaseTool):
    name = "mcp__playwright__browser_snapshot"
    description = "Returns a large browser snapshot."
    input_model = _OkInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        del arguments, context
        return ToolResult(output="snapshot-line\n" * 40)


@pytest.mark.asyncio
async def test_query_engine_persists_compacted_tool_turn_history(tmp_path: Path, monkeypatch):
    """Compaction must not make a completed tool turn disappear from engine history."""

    monkeypatch.delenv("CLAUDE_CODE_COORDINATOR_MODE", raising=False)
    monkeypatch.setattr("openharness.services.compact.try_session_memory_compaction", lambda *args, **kwargs: None)
    should_calls = {"count": 0}

    def _should_compact_once(*args, **kwargs):
        del args, kwargs
        should_calls["count"] += 1
        return should_calls["count"] == 1

    monkeypatch.setattr("openharness.services.compact.should_autocompact", _should_compact_once)

    registry = ToolRegistry()
    registry.register(_OkTool())
    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="<summary>Earlier setup was completed.</summary>")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            TextBlock(text="I will verify with a tool."),
                            ToolUseBlock(id="toolu_ok_after_compact", name="ok_tool", input={}),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="Tool finished after compact.")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )
    engine.load_messages(
        [
            ConversationMessage.from_user_text(f"historical user request {index}")
            if index % 2 == 0
            else ConversationMessage(role="assistant", content=[TextBlock(text=f"historical answer {index}")])
            for index in range(8)
        ]
    )

    events = [event async for event in engine.submit_message("new request after compact")]

    assert any(isinstance(event, CompactProgressEvent) and event.phase == "compact_end" for event in events)
    assert any("This session is being continued" in message.text for message in engine.messages)
    assert any(
        isinstance(block, ToolUseBlock) and block.id == "toolu_ok_after_compact"
        for message in engine.messages
        for block in message.content
    )
    assert any(
        isinstance(block, ToolResultBlock) and block.tool_use_id == "toolu_ok_after_compact"
        for message in engine.messages
        for block in message.content
    )
    assert engine.messages[-1].text == "Tool finished after compact."


@pytest.mark.asyncio
async def test_query_engine_synthesizes_tool_result_when_parallel_tool_raises(tmp_path: Path):
    """Parallel tool calls must each yield a tool_result even when one tool raises.

    Regression for the case where ``asyncio.gather`` (without
    ``return_exceptions=True``) propagated the first exception, abandoned the
    sibling coroutines, and left the conversation with un-replied ``tool_use``
    blocks — Anthropic's API then rejects the next request on the session.
    """

    registry = ToolRegistry()
    registry.register(_OkTool())
    registry.register(_BoomTool())

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            TextBlock(text="Running two tools."),
                            ToolUseBlock(id="toolu_ok", name="ok_tool", input={}),
                            ToolUseBlock(id="toolu_boom", name="boom_tool", input={}),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[TextBlock(text="Recovered from the failure.")],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("run both tools")]

    completed = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    completed_by_name = {event.tool_name: event for event in completed}
    assert set(completed_by_name) == {"ok_tool", "boom_tool"}
    assert completed_by_name["ok_tool"].is_error is False
    assert completed_by_name["ok_tool"].output == "ok"
    assert completed_by_name["ok_tool"].metadata == {"sentinel": "metadata"}
    assert completed_by_name["boom_tool"].is_error is True
    assert "RuntimeError" in completed_by_name["boom_tool"].output
    assert "boom" in completed_by_name["boom_tool"].output

    user_tool_messages = [
        msg for msg in engine.messages if msg.role == "user" and any(isinstance(block, ToolResultBlock) for block in msg.content)
    ]
    assert len(user_tool_messages) == 1
    result_blocks = [block for block in user_tool_messages[0].content if isinstance(block, ToolResultBlock)]
    assert {block.tool_use_id for block in result_blocks} == {"toolu_ok", "toolu_boom"}

    assert isinstance(events[-1], AssistantTurnComplete)
    assert events[-1].message.text == "Recovered from the failure."


@pytest.mark.asyncio
async def test_query_engine_sanitizes_dangling_tool_use_before_new_prompt(tmp_path: Path):
    engine = QueryEngine(
        api_client=StaticApiClient("fresh reply"),
        tool_registry=ToolRegistry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )
    engine.load_messages([
        ConversationMessage.from_user_text("previous request"),
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="call_missing_output", name="ok_tool", input={})],
        ),
    ])

    events = [event async for event in engine.submit_message("new prompt")]

    assert isinstance(events[-1], AssistantTurnComplete)
    assert events[-1].message.text == "fresh reply"
    assert not any(
        isinstance(block, ToolUseBlock) and block.id == "call_missing_output"
        for message in engine.messages
        for block in message.content
    )


@pytest.mark.asyncio
async def test_query_engine_continue_pending_sanitizes_dangling_tool_use(tmp_path: Path):
    engine = QueryEngine(
        api_client=StaticApiClient("continued reply"),
        tool_registry=ToolRegistry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )
    engine.load_messages([
        ConversationMessage.from_user_text("previous request"),
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="call_missing_output", name="ok_tool", input={})],
        ),
    ])

    events = [event async for event in engine.continue_pending()]

    assert isinstance(events[-1], AssistantTurnComplete)
    assert events[-1].message.text == "continued reply"
    assert not any(
        isinstance(block, ToolUseBlock) and block.id == "call_missing_output"
        for message in engine.messages
        for block in message.content
    )


@pytest.mark.asyncio
async def test_query_engine_offloads_large_tool_result_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENHARNESS_TOOL_OUTPUT_INLINE_CHARS", "256")
    monkeypatch.setenv("OPENHARNESS_TOOL_OUTPUT_PREVIEW_CHARS", "128")
    registry = ToolRegistry()
    registry.register(_LargeOutputTool())

    engine = QueryEngine(
        api_client=FakeApiClient(
            [
                _FakeResponse(
                    message=ConversationMessage(
                        role="assistant",
                        content=[
                            ToolUseBlock(
                                id="toolu_snapshot",
                                name="mcp__playwright__browser_snapshot",
                                input={},
                            ),
                        ],
                    ),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
                _FakeResponse(
                    message=ConversationMessage(role="assistant", content=[TextBlock(text="done")]),
                    usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                ),
            ]
        ),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
        tool_metadata={},
    )

    events = [event async for event in engine.submit_message("snapshot")]

    completed = [event for event in events if isinstance(event, ToolExecutionCompleted)]
    assert len(completed) == 1
    assert completed[0].output.startswith("[Tool output truncated]")
    assert "snapshot-line" in completed[0].output

    user_tool_messages = [
        msg for msg in engine.messages if msg.role == "user" and any(isinstance(block, ToolResultBlock) for block in msg.content)
    ]
    result_blocks = [block for block in user_tool_messages[0].content if isinstance(block, ToolResultBlock)]
    inline = result_blocks[0].content
    assert "Full output saved to:" in inline
    assert "Original size:" in inline
    assert inline.count("snapshot-line") < 40
    artifact_line = next(line for line in inline.splitlines() if line.startswith("Full output saved to:"))
    artifact_path = Path(artifact_line.removeprefix("Full output saved to:").strip())
    assert artifact_path.exists()
    assert artifact_path.read_text(encoding="utf-8") == "snapshot-line\n" * 40
    assert str(artifact_path) in engine.tool_metadata["task_focus_state"]["active_artifacts"]


@pytest.mark.asyncio
async def test_query_engine_drops_empty_assistant_messages(tmp_path: Path):
    engine = QueryEngine(
        api_client=EmptyAssistantApiClient(),
        tool_registry=ToolRegistry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="system",
    )

    events = [event async for event in engine.submit_message("hello")]

    assert any(isinstance(event, ErrorEvent) for event in events)
    assert not any(isinstance(event, AssistantTurnComplete) for event in events)
    assert len(engine.messages) == 1
    assert engine.messages[0].role == "user"
