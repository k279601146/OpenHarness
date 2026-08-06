"""Shared turn state helpers for query execution."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from openharness.engine.stream_events import AgentProgressEvent


@dataclass
class RunTimingTrace:
    """Per-turn timing metadata attached to progress events."""

    turn_id: str
    turn_index: int
    started_at: float = field(default_factory=time.monotonic)
    event_seq: int = 0
    phase_started_at: dict[str, float] = field(default_factory=dict)

    def metadata(self, phase: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        now = time.monotonic()
        phase_started_at = self.phase_started_at.setdefault(phase, now)
        self.event_seq += 1
        data: dict[str, Any] = {
            "turn_id": self.turn_id,
            "turn_index": self.turn_index,
            "event_seq": self.event_seq,
            "elapsed_ms": max(0, int((now - self.started_at) * 1000)),
            "phase_elapsed_ms": max(0, int((now - phase_started_at) * 1000)),
        }
        if extra:
            data.update(extra)
        return data


def progress_event(
    phase: str,
    message: str,
    *,
    status: str = "running",
    tool_name: str | None = None,
    tool_use_id: str | None = None,
    workspace: str | None = None,
    path: str | None = None,
    detail: str | None = None,
    metadata: dict[str, Any] | None = None,
    timing: RunTimingTrace | None = None,
) -> AgentProgressEvent:
    if timing is not None:
        metadata = timing.metadata(phase, metadata)
    return AgentProgressEvent(
        phase=phase,
        status=status,  # type: ignore[arg-type]
        message=message,
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        workspace=workspace,
        path=path,
        detail=detail,
        metadata=metadata,
    )


def query_cancelled(context: Any) -> bool:
    token = getattr(context, "cancellation_token", None)
    return bool(token is not None and token.is_cancelled())


def query_cancel_reason(context: Any) -> str:
    token = getattr(context, "cancellation_token", None)
    return (token.reason if token is not None else None) or "cancelled"
