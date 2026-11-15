"""Turn and step inbox for steering, follow-ups, and subagent notifications."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from openharness.tools.base import CancellationToken

InboxTarget = Literal["next_step", "next_turn"]


@dataclass(frozen=True)
class InboxMessage:
    """One queued message waiting to enter an agent turn or step."""

    id: str
    content: str | list[Any]
    source: str = "user"
    target: InboxTarget = "next_step"
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentInbox:
    """Thread-safe / asyncio-safe dual-lane inbox for an agent loop.

    Inspired by DeepSeek Harness's ``ReactLoopInbox``:
    - ``next_step``: high-priority steering inputs, injected context, and
      subagent completion notices claimed at the next step boundary.
    - ``next_turn``: follow-up prompts queued for subsequent turns.
    """

    def __init__(self) -> None:
        self._next_step: list[InboxMessage] = []
        self._next_turn: list[InboxMessage] = []
        self._condition = asyncio.Condition()
        self._version = 0

    @property
    def next_step(self) -> tuple[InboxMessage, ...]:
        """Return a snapshot of pending next-step messages."""
        return tuple(self._next_step)

    @property
    def next_turn(self) -> tuple[InboxMessage, ...]:
        """Return a snapshot of pending next-turn messages."""
        return tuple(self._next_turn)

    def has_next_step(self) -> bool:
        """Return whether any next-step input is waiting."""
        return bool(self._next_step)

    def has_next_turn(self) -> bool:
        """Return whether any next-turn input is waiting."""
        return bool(self._next_turn)

    def has_pending(self) -> bool:
        """Return whether either inbox lane contains pending messages."""
        return bool(self._next_step or self._next_turn)

    def next_step_ids(self) -> set[str]:
        """Return the IDs of messages currently pending in ``next_step``."""
        return {msg.id for msg in self._next_step}

    async def append(
        self,
        content: str | list[Any],
        *,
        target: InboxTarget = "next_step",
        source: str = "user",
        metadata: dict[str, Any] | None = None,
        msg_id: str | None = None,
    ) -> InboxMessage:
        """Append a message to the requested lane and wake any waiters."""
        message = InboxMessage(
            id=msg_id or f"inb_{uuid4().hex[:12]}",
            content=content,
            source=source,
            target=target,
            metadata=dict(metadata or {}),
        )
        async with self._condition:
            if target == "next_step":
                self._next_step.append(message)
            else:
                self._next_turn.append(message)
            self._version += 1
            self._condition.notify_all()
        return message

    def append_nowait(
        self,
        content: str | list[Any],
        *,
        target: InboxTarget = "next_step",
        source: str = "user",
        metadata: dict[str, Any] | None = None,
        msg_id: str | None = None,
    ) -> InboxMessage:
        """Synchronously append a message and wake waiters if inside an event loop."""
        message = InboxMessage(
            id=msg_id or f"inb_{uuid4().hex[:12]}",
            content=content,
            source=source,
            target=target,
            metadata=dict(metadata or {}),
        )
        if target == "next_step":
            self._next_step.append(message)
        else:
            self._next_turn.append(message)
        self._version += 1
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(self._notify_waiters())
        return message

    async def _notify_waiters(self) -> None:
        async with self._condition:
            self._condition.notify_all()

    async def steer(
        self,
        content: str | list[Any],
        *,
        source: str = "user",
        metadata: dict[str, Any] | None = None,
    ) -> InboxMessage:
        """Queue a steering message for the next step boundary."""
        return await self.append(content, target="next_step", source=source, metadata=metadata)

    async def followup(
        self,
        content: str | list[Any],
        *,
        source: str = "user",
        metadata: dict[str, Any] | None = None,
    ) -> InboxMessage:
        """Queue a follow-up prompt for the next turn boundary."""
        return await self.append(content, target="next_turn", source=source, metadata=metadata)

    def claim_next_step(self) -> list[InboxMessage]:
        """Atomically drain and return all pending next-step messages."""
        if not self._next_step:
            return []
        claimed = list(self._next_step)
        self._next_step.clear()
        return claimed

    def claim_next_turn(self) -> InboxMessage | None:
        """Pop the next queued follow-up turn, if any."""
        if not self._next_turn:
            return None
        return self._next_turn.pop(0)

    def clear(self) -> None:
        """Clear all pending messages in both lanes."""
        self._next_step.clear()
        self._next_turn.clear()

    async def wait_for_next_step(
        self,
        *,
        seen_ids: set[str] | None = None,
        timeout_seconds: float = 30.0,
        cancellation_token: CancellationToken | None = None,
    ) -> bool:
        """Wait until at least one unseen ``next_step`` message arrives or timeout expires."""
        seen = seen_ids or set()
        deadline = time.monotonic() + max(0.01, float(timeout_seconds))

        async with self._condition:
            while True:
                if cancellation_token is not None and cancellation_token.is_cancelled():
                    return False
                if any(msg.id not in seen for msg in self._next_step):
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                try:
                    if cancellation_token is not None:
                        wait_coro = self._condition.wait()
                        cancel_coro = cancellation_token.wait()
                        wait_task = asyncio.create_task(wait_coro)
                        cancel_task = asyncio.create_task(cancel_coro)
                        done, pending = await asyncio.wait(
                            {wait_task, cancel_task},
                            timeout=remaining,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for task in pending:
                            task.cancel()
                        if pending:
                            await asyncio.gather(*pending, return_exceptions=True)
                        if not done:
                            return any(msg.id not in seen for msg in self._next_step)
                    else:
                        await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    return any(msg.id not in seen for msg in self._next_step)
