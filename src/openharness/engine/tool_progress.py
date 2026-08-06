"""Tool execution progress streaming helpers."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator, Awaitable, Callable

from openharness.engine.messages import ToolResultBlock
from openharness.engine.stream_events import AgentProgressEvent
from openharness.engine.turn_state import RunTimingTrace, progress_event, query_cancel_reason

log = logging.getLogger(__name__)


async def run_tool_with_progress(
    context: Any,
    tool_name: str,
    tool_use_id: str,
    tool_input: dict[str, object],
    *,
    execute_tool_call: Callable[..., Awaitable[ToolResultBlock]],
    query_cancelled_error: type[BaseException],
    heartbeat_seconds: float,
    logger: logging.Logger | None = None,
    timing: RunTimingTrace | None = None,
) -> AsyncIterator[tuple[AgentProgressEvent | None, ToolResultBlock | None]]:
    active_log = logger or log
    progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    started = time.monotonic()
    heartbeat_count = 0
    progress_event_count = 0
    pending_progress_count = 0

    def _progress_payload_event(payload: dict[str, Any]) -> AgentProgressEvent:
        return progress_event(
            str(payload.get("phase") or "tool_progress"),
            str(payload.get("message") or f"{tool_name} 正在运行..."),
            status=str(payload.get("status") or "running"),
            tool_name=str(payload.get("tool_name") or tool_name),
            tool_use_id=str(payload.get("tool_use_id") or tool_use_id),
            workspace=str(payload.get("workspace") or (context.tool_metadata or {}).get("workspace_backend") or ""),
            path=str(payload.get("path") or "") or None,
            detail=str(payload.get("detail") or "") or None,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
            timing=timing,
        )

    async def _progress(payload: dict[str, Any]) -> None:
        await progress_queue.put(payload)

    task = asyncio.create_task(
        execute_tool_call(
            context,
            tool_name,
            tool_use_id,
            tool_input,
            progress_callback=_progress,
        )
    )
    progress_task: asyncio.Task[dict[str, Any]] | None = None
    heartbeat_task: asyncio.Task[None] | None = None
    cancel_task: asyncio.Task[None] | None = (
        asyncio.create_task(context.cancellation_token.wait())
        if context.cancellation_token is not None
        else None
    )
    try:
        while not task.done():
            if progress_task is None:
                progress_task = asyncio.create_task(progress_queue.get())
            if heartbeat_task is None:
                heartbeat_task = asyncio.create_task(asyncio.sleep(heartbeat_seconds))

            wait_tasks: set[asyncio.Task[Any]] = {task, progress_task, heartbeat_task}
            if cancel_task is not None:
                wait_tasks.add(cancel_task)
            done, _ = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)

            if progress_task in done:
                payload = progress_task.result()
                progress_task = None
                progress_event_count += 1
                yield _progress_payload_event(payload), None
                continue

            if task in done:
                break

            if cancel_task is not None and cancel_task in done:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                yield progress_event(
                    "tool_aborted",
                    "",
                    status="error",
                    tool_name=tool_name,
                    tool_use_id=tool_use_id,
                    workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                    metadata={"reason": query_cancel_reason(context)},
                    timing=timing,
                ), None
                raise query_cancelled_error(query_cancel_reason(context))

            if heartbeat_task in done:
                heartbeat_task = None
                heartbeat_count += 1
                yield progress_event(
                    "heartbeat",
                    f"工具 {tool_name} 仍在运行...",
                    status="info",
                    tool_name=tool_name,
                    tool_use_id=tool_use_id,
                    workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                    metadata={
                        "engine_elapsed_seconds": round(time.monotonic() - started, 3),
                        "engine_heartbeat_count": heartbeat_count,
                    },
                    timing=timing,
                ), None
    finally:
        pending_tasks = [
            pending_task
            for pending_task in (progress_task, heartbeat_task, cancel_task)
            if pending_task is not None and not pending_task.done()
        ]
        for pending_task in pending_tasks:
            pending_task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

    while not progress_queue.empty():
        payload = progress_queue.get_nowait()
        progress_event_count += 1
        pending_progress_count += 1
        yield _progress_payload_event(payload), None
    try:
        result = await task
    except Exception:
        elapsed_seconds = time.monotonic() - started
        active_log.debug(
            "tool progress wait failed: name=%s id=%s elapsed=%.3fs heartbeats=%d progress_events=%d pending_progress=%d",
            tool_name,
            tool_use_id,
            elapsed_seconds,
            heartbeat_count,
            progress_event_count,
            pending_progress_count,
            exc_info=True,
        )
        raise
    else:
        elapsed_seconds = time.monotonic() - started
        active_log.debug(
            "tool progress wait complete: name=%s id=%s elapsed=%.3fs heartbeats=%d progress_events=%d pending_progress=%d",
            tool_name,
            tool_use_id,
            elapsed_seconds,
            heartbeat_count,
            progress_event_count,
            pending_progress_count,
        )
    yield None, result
