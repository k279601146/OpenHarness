"""Append-only Session Event Log and pure synchronous `SessionProjection` folds (`dsh-session-projection` inspired)."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Callable, Generic, TypeVar

from openharness.engine.messages import (
    ConversationMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    sanitize_conversation_messages,
)
from openharness.services.tool_outputs import prune_tool_result_text

TState = TypeVar("TState")


@dataclass(frozen=True)
class SequencedSessionEvent:
    """Immutable append-only session event entry with monotonic sequence number."""

    seq: int
    type: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ProjectionSpec(Generic[TState]):
    """Pure synchronous fold specification over `SequencedSessionEvent`s."""

    name: str
    init: Callable[[], TState]
    apply: Callable[[TState, SequencedSessionEvent], TState]


class SessionProjectionStore:
    """Append-only event log with synchronous pure projections and `as_of_seq` time-travel."""

    def __init__(self) -> None:
        self._events: list[SequencedSessionEvent] = []
        self._specs: dict[str, ProjectionSpec[Any]] = {}
        self._states: dict[str, Any] = {}
        self._state_versions: dict[str, int] = {}
        self.register(SURFACE_HISTORY_PROJECTION)
        self.register(TASK_FOCUS_PROJECTION)

    def register(self, spec: ProjectionSpec[TState]) -> None:
        """Register a projection fold and compute its state over existing events."""
        state = spec.init()
        version = 0
        for evt in self._events:
            next_state = spec.apply(state, evt)
            if next_state is not state:
                version += 1
            state = next_state
        self._specs[spec.name] = spec
        self._states[spec.name] = state
        self._state_versions[spec.name] = version

    def append(self, event_type: str, payload: dict[str, Any] | None = None) -> SequencedSessionEvent:
        """Append an event and synchronously fold all registered projections."""
        evt = SequencedSessionEvent(
            seq=len(self._events) + 1,
            type=event_type,
            payload=dict(payload or {}),
        )
        self._events.append(evt)
        for name, spec in self._specs.items():
            prev = self._states[name]
            updated = spec.apply(prev, evt)
            if updated is not prev:
                self._state_versions[name] = self._state_versions.get(name, 0) + 1
            self._states[name] = updated
        return evt

    def view(self, name: str, *, as_of_seq: int | None = None) -> Any:
        """Return the current projection state, or fold up to `as_of_seq` for time-travel cuts."""
        if name not in self._specs:
            raise KeyError(f"Unknown session projection: {name}")
        if as_of_seq is None or as_of_seq >= len(self._events):
            return self._states[name]
        spec = self._specs[name]
        state = spec.init()
        for evt in self._events:
            if evt.seq > as_of_seq:
                break
            state = spec.apply(state, evt)
        return state

    def state_version(self, name: str) -> int:
        return self._state_versions.get(name, 0)

    @property
    def events(self) -> tuple[SequencedSessionEvent, ...]:
        return tuple(self._events)

    def append_message(self, message: ConversationMessage) -> SequencedSessionEvent:
        return self.append("message/append", {"message": message.model_dump(mode="json")})

    def record_compaction_replace(
        self,
        *,
        start_seq: int,
        end_seq: int,
        replacement_messages: list[ConversationMessage],
        summary: str = "",
    ) -> SequencedSessionEvent:
        """Record a non-destructive `surfaceOp: replace` compaction event."""
        return self.append(
            "compaction/summary",
            {
                "surface_op": {
                    "op": "replace",
                    "start_seq": int(start_seq),
                    "end_seq": int(end_seq),
                },
                "summary": summary,
                "replacement_messages": [m.model_dump(mode="json") for m in replacement_messages],
            },
        )

    def record_tool_result_prune(
        self,
        *,
        tool_use_id: str,
        max_chars: int = 1200,
        max_tokens: int = 300,
    ) -> SequencedSessionEvent:
        """Record a shadow-price deterministic tool-result prune event."""
        return self.append(
            "compaction/prune",
            {
                "tool_use_id": tool_use_id,
                "max_chars": max_chars,
                "max_tokens": max_tokens,
            },
        )

    def derive_messages(self, *, as_of_seq: int | None = None) -> list[ConversationMessage]:
        """Derive provider-ready conversation messages from the append-only event log."""
        surface: SurfaceHistoryState = self.view("surface_history", as_of_seq=as_of_seq)
        return surface.to_messages()


def is_tool_pairing_balanced(messages: list[ConversationMessage]) -> bool:
    """Verify that every assistant `tool_use` is balanced by a matching user `tool_result`."""
    pending_ids: set[str] = set()
    for msg in messages:
        if msg.role == "assistant":
            if pending_ids:
                return False
            tool_uses = [b.id for b in msg.content if isinstance(b, ToolUseBlock)]
            pending_ids = set(tool_uses)
        elif msg.role == "user" and pending_ids:
            result_ids = {b.tool_use_id for b in msg.content if isinstance(b, ToolResultBlock)}
            if not pending_ids.issubset(result_ids):
                return False
            pending_ids = set()
    return len(pending_ids) == 0


@dataclass(frozen=True)
class SurfaceHistoryState:
    """Immutable state for surface message derivation (`surfaceOp: replace` + shadow pruning)."""

    entries: tuple[tuple[int, ConversationMessage], ...] = ()
    pruned_tool_ids: dict[str, tuple[int, int]] = field(default_factory=dict)

    def to_messages(self) -> list[ConversationMessage]:
        out: list[ConversationMessage] = []
        for _seq, msg in self.entries:
            if msg.role == "user" and self.pruned_tool_ids:
                updated_blocks = []
                changed = False
                for block in msg.content:
                    if isinstance(block, ToolResultBlock) and block.tool_use_id in self.pruned_tool_ids:
                        max_c, max_t = self.pruned_tool_ids[block.tool_use_id]
                        pruned_text = prune_tool_result_text(block.content, max_chars=max_c, max_tokens=max_t)
                        if pruned_text != block.content:
                            block = block.model_copy(update={"content": pruned_text})
                            changed = True
                    updated_blocks.append(block)
                if changed:
                    msg = ConversationMessage(role="user", content=updated_blocks)
            out.append(msg)
        return sanitize_conversation_messages(out)


def _apply_surface_history(state: SurfaceHistoryState, event: SequencedSessionEvent) -> SurfaceHistoryState:
    if event.type == "message/append":
        raw_msg = event.payload.get("message")
        if isinstance(raw_msg, dict):
            msg = ConversationMessage.model_validate(raw_msg)
            return SurfaceHistoryState(
                entries=(*state.entries, (event.seq, msg)),
                pruned_tool_ids=dict(state.pruned_tool_ids),
            )
    elif event.type == "compaction/summary":
        surface_op = event.payload.get("surface_op") or {}
        if isinstance(surface_op, dict) and surface_op.get("op") == "replace":
            start_seq = int(surface_op.get("start_seq") or 0)
            end_seq = int(surface_op.get("end_seq") or event.seq)
            replacements = [
                (event.seq, ConversationMessage.model_validate(item))
                for item in (event.payload.get("replacement_messages") or ())
                if isinstance(item, dict)
            ]
            before = [item for item in state.entries if item[0] < start_seq]
            after = [item for item in state.entries if item[0] > end_seq]
            return SurfaceHistoryState(
                entries=tuple([*before, *replacements, *after]),
                pruned_tool_ids=dict(state.pruned_tool_ids),
            )
    elif event.type == "compaction/prune":
        tool_use_id = str(event.payload.get("tool_use_id") or "").strip()
        if tool_use_id:
            max_chars = int(event.payload.get("max_chars") or 1200)
            max_tokens = int(event.payload.get("max_tokens") or 300)
            next_pruned = dict(state.pruned_tool_ids)
            next_pruned[tool_use_id] = (max_chars, max_tokens)
            return SurfaceHistoryState(entries=state.entries, pruned_tool_ids=next_pruned)
    return state


SURFACE_HISTORY_PROJECTION = ProjectionSpec[SurfaceHistoryState](
    name="surface_history",
    init=SurfaceHistoryState,
    apply=_apply_surface_history,
)


@dataclass(frozen=True)
class TaskFocusProjectionState:
    """Deterministic projection of task focus, artifacts, and invoked skills."""

    goal: str = ""
    active_artifacts: tuple[str, ...] = ()
    invoked_skills: tuple[str, ...] = ()
    verified_work: tuple[str, ...] = ()


def _apply_task_focus(state: TaskFocusProjectionState, event: SequencedSessionEvent) -> TaskFocusProjectionState:
    if event.type == "message/append":
        raw = event.payload.get("message")
        if isinstance(raw, dict) and raw.get("role") == "user":
            blocks = raw.get("content") or ()
            texts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
            joined = " ".join(t.strip() for t in texts if t.strip() and not t.strip().startswith("<prompt-context"))
            if joined and not state.goal:
                return TaskFocusProjectionState(
                    goal=joined[:240],
                    active_artifacts=state.active_artifacts,
                    invoked_skills=state.invoked_skills,
                    verified_work=state.verified_work,
                )
    elif event.type == "tool/completed":
        artifact = str(event.payload.get("artifact_path") or "").strip()
        skill = str(event.payload.get("skill_name") or "").strip()
        verified = str(event.payload.get("verified_entry") or "").strip()
        artifacts = list(state.active_artifacts)
        skills = list(state.invoked_skills)
        work = list(state.verified_work)
        changed = False
        if artifact and artifact not in artifacts:
            artifacts.append(artifact)
            changed = True
        if skill and skill not in skills:
            skills.append(skill)
            changed = True
        if verified and verified not in work:
            work.append(verified)
            changed = True
        if changed:
            return TaskFocusProjectionState(
                goal=state.goal,
                active_artifacts=tuple(artifacts[-12:]),
                invoked_skills=tuple(skills[-12:]),
                verified_work=tuple(work[-16:]),
            )
    return state


TASK_FOCUS_PROJECTION = ProjectionSpec[TaskFocusProjectionState](
    name="task_focus",
    init=TaskFocusProjectionState,
    apply=_apply_task_focus,
)
