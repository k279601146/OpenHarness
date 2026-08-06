"""Model streaming step for a single query turn."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator

from openharness.api.client import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiRetryEvent,
    ApiTextDeltaEvent,
    ApiToolCallCompletedEvent,
    ApiToolCallProgressEvent,
    ApiToolCallStartedEvent,
)
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage
from openharness.engine.stream_events import (
    AssistantTextDelta,
    StatusEvent,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from openharness.engine.turn_state import RunTimingTrace, progress_event, query_cancel_reason


@dataclass(frozen=True)
class ModelTurnComplete:
    """Final model response from a streaming model turn."""

    message: ConversationMessage
    usage: UsageSnapshot


ModelTurnStreamItem = tuple[StreamEvent, UsageSnapshot | None] | ModelTurnComplete


async def stream_model_turn(
    *,
    context: Any,
    messages: list[ConversationMessage],
    effective_max_tokens: int,
    tool_schemas: list[dict[str, Any]],
    heartbeat_seconds: float,
    timing: RunTimingTrace,
) -> AsyncIterator[ModelTurnStreamItem]:
    """Stream one model request and surface progress events."""

    yield progress_event(
        "model_request",
        "正在请求模型...",
        workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
        metadata={"message_count": len(messages)},
        timing=timing,
    ), None
    model_queue: asyncio.Queue[Any] = asyncio.Queue()
    model_stream_reported = False

    async def _produce_model_events() -> None:
        try:
            async for stream_event in context.api_client.stream_message(
                ApiMessageRequest(
                    model=context.model,
                    messages=messages,
                    system_prompt=context.system_prompt,
                    max_tokens=effective_max_tokens,
                    tools=tool_schemas,
                    effort=context.effort,
                    openai_web_search=(context.tool_metadata or {}).get("openai_web_search")
                    if isinstance((context.tool_metadata or {}).get("openai_web_search"), dict)
                    else None,
                )
            ):
                await model_queue.put(stream_event)
        except BaseException as exc:
            await model_queue.put(exc)
        finally:
            await model_queue.put(None)

    model_task = asyncio.create_task(_produce_model_events())
    model_get_task: asyncio.Task[Any] | None = None
    heartbeat_task: asyncio.Task[None] | None = None
    cancel_task: asyncio.Task[None] | None = (
        asyncio.create_task(context.cancellation_token.wait())
        if context.cancellation_token is not None
        else None
    )
    try:
        while True:
            if model_get_task is None:
                model_get_task = asyncio.create_task(model_queue.get())
            if heartbeat_task is None:
                heartbeat_task = asyncio.create_task(asyncio.sleep(heartbeat_seconds))
            wait_tasks = {model_get_task, heartbeat_task}
            if cancel_task is not None:
                wait_tasks.add(cancel_task)
            done, _ = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)

            if cancel_task is not None and cancel_task in done:
                yield progress_event(
                    "turn_aborted",
                    "",
                    status="error",
                    workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                    metadata={"reason": query_cancel_reason(context), "stage": "model_stream"},
                    timing=timing,
                ), None
                return

            if model_get_task in done:
                event = model_get_task.result()
                model_get_task = None
            elif heartbeat_task in done:
                heartbeat_task = None
                yield progress_event(
                    "heartbeat",
                    "仍在等待模型响应...",
                    status="info",
                    workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                    timing=timing,
                ), None
                continue
            else:
                continue

            if event is None:
                break
            if isinstance(event, BaseException):
                raise event
            if isinstance(event, ApiTextDeltaEvent):
                if not model_stream_reported:
                    model_stream_reported = True
                    yield progress_event(
                        "model_stream",
                        "模型正在生成回复...",
                        status="info",
                        timing=timing,
                    ), None
                yield AssistantTextDelta(text=event.text), None
                continue
            if isinstance(event, ApiRetryEvent):
                yield StatusEvent(
                    message=(
                        f"Request failed; retrying in {event.delay_seconds:.1f}s "
                        f"(attempt {event.attempt + 1} of {event.max_attempts}): {event.message}"
                    ),
                    kind="model_retrying",
                    attempt=event.attempt + 1,
                    max_attempts=event.max_attempts,
                    delay_seconds=event.delay_seconds,
                    detail=event.message,
                ), None
                continue

            if isinstance(event, ApiToolCallStartedEvent):
                yield ToolExecutionStarted(
                    tool_name=event.tool_name,
                    tool_input=event.tool_input,
                    tool_use_id=event.tool_use_id,
                ), None
                yield progress_event(
                    "hosted_tool_start",
                    event.message or f"正在执行托管工具 {event.tool_name}...",
                    status=event.status,
                    tool_name=event.tool_name,
                    tool_use_id=event.tool_use_id,
                    metadata=event.metadata,
                    timing=timing,
                ), None
                continue

            if isinstance(event, ApiToolCallProgressEvent):
                yield progress_event(
                    "hosted_tool_progress",
                    event.message or f"托管工具 {event.tool_name} 正在执行...",
                    status=event.status,
                    tool_name=event.tool_name,
                    tool_use_id=event.tool_use_id,
                    metadata=event.metadata,
                    timing=timing,
                ), None
                continue

            if isinstance(event, ApiToolCallCompletedEvent):
                is_error = event.status == "error"
                yield ToolExecutionCompleted(
                    tool_name=event.tool_name,
                    output=event.message or f"Hosted tool {event.tool_name} completed.",
                    is_error=is_error,
                    metadata=event.metadata,
                    tool_use_id=event.tool_use_id,
                ), None
                yield progress_event(
                    "hosted_tool_complete",
                    event.message or f"托管工具 {event.tool_name} 执行{'失败' if is_error else '完成'}",
                    status="error" if is_error else "success",
                    tool_name=event.tool_name,
                    tool_use_id=event.tool_use_id,
                    metadata=event.metadata,
                    timing=timing,
                ), None
                continue

            if isinstance(event, ApiMessageCompleteEvent):
                yield progress_event(
                    "model_response",
                    "模型已规划下一步...",
                    status="success",
                    metadata={"stop_reason": event.stop_reason},
                    timing=timing,
                ), None
                yield ModelTurnComplete(message=event.message, usage=event.usage)
                continue
    finally:
        pending_model_wait_tasks = [
            pending_task
            for pending_task in (model_get_task, heartbeat_task, cancel_task)
            if pending_task is not None and not pending_task.done()
        ]
        for pending_task in pending_model_wait_tasks:
            pending_task.cancel()
        if pending_model_wait_tasks:
            await asyncio.gather(*pending_model_wait_tasks, return_exceptions=True)
        if not model_task.done():
            model_task.cancel()
            await asyncio.gather(model_task, return_exceptions=True)
