"""Durable same-session Goal continuation service and tool (`dsh-goal` inspired)."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

GoalPhase = Literal["active", "paused", "blocked", "complete"]


@dataclass(frozen=True)
class GoalBlockReason:
    """Structured reason when a goal transitions to `blocked`."""

    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class GoalSnapshot:
    """Immutable snapshot of a durable session goal with CAS revision."""

    id: str
    revision: int
    objective: str
    phase: GoalPhase = "active"
    criteria: tuple[str, ...] = ()
    progress_notes: tuple[str, ...] = ()
    blocked_reason: GoalBlockReason | None = None
    rounds_used: int = 0
    max_rounds: int = 16
    armed: bool = True
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "revision": self.revision,
            "objective": self.objective,
            "phase": self.phase,
            "criteria": list(self.criteria),
            "progress_notes": list(self.progress_notes),
            "blocked_reason": self.blocked_reason.to_dict() if self.blocked_reason else None,
            "rounds_used": self.rounds_used,
            "max_rounds": self.max_rounds,
            "armed": self.armed,
            "updated_at": self.updated_at,
        }


class GoalService:
    """Event-sourced same-session goal state machine with compare-and-set revision checks."""

    def __init__(self, *, max_goal_rounds: int = 16) -> None:
        self._default_max_rounds = max(1, int(max_goal_rounds))
        self._current: GoalSnapshot | None = None
        self._event_log: list[dict[str, Any]] = []

    @property
    def current(self) -> GoalSnapshot | None:
        return self._current

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._event_log)

    def create(
        self,
        *,
        objective: str,
        criteria: list[str] | tuple[str, ...] = (),
        max_rounds: int | None = None,
        goal_id: str | None = None,
    ) -> GoalSnapshot:
        gid = (goal_id or f"goal_{uuid4().hex[:8]}").strip()
        snap = GoalSnapshot(
            id=gid,
            revision=1,
            objective=objective.strip(),
            phase="active",
            criteria=tuple(str(c).strip() for c in criteria if str(c).strip()),
            max_rounds=max(1, int(max_rounds or self._default_max_rounds)),
            armed=True,
        )
        self._record_change("create", snap)
        return snap

    def update(
        self,
        *,
        expected_revision: int | None = None,
        phase: GoalPhase | None = None,
        objective: str | None = None,
        criteria: list[str] | None = None,
        progress_note: str | None = None,
        blocked_reason: GoalBlockReason | dict[str, str] | None = None,
    ) -> GoalSnapshot:
        if self._current is None:
            raise ValueError("No active goal exists; call create first.")
        if expected_revision is not None and int(expected_revision) != self._current.revision:
            raise ValueError(
                f"Goal CAS revision mismatch: expected {expected_revision}, current is {self._current.revision}"
            )
        next_phase: GoalPhase = phase or self._current.phase
        resolved_block: GoalBlockReason | None = self._current.blocked_reason
        if blocked_reason is not None:
            if isinstance(blocked_reason, GoalBlockReason):
                resolved_block = blocked_reason
            elif isinstance(blocked_reason, dict):
                resolved_block = GoalBlockReason(
                    code=str(blocked_reason.get("code") or "BLOCKED"),
                    message=str(blocked_reason.get("message") or ""),
                )
        elif next_phase != "blocked":
            resolved_block = None

        notes = list(self._current.progress_notes)
        if progress_note and progress_note.strip():
            notes.append(progress_note.strip())

        snap = GoalSnapshot(
            id=self._current.id,
            revision=self._current.revision + 1,
            objective=objective.strip() if objective else self._current.objective,
            phase=next_phase,
            criteria=tuple(str(c).strip() for c in criteria if str(c).strip())
            if criteria is not None
            else self._current.criteria,
            progress_notes=tuple(notes),
            blocked_reason=resolved_block,
            rounds_used=self._current.rounds_used,
            max_rounds=self._current.max_rounds,
            armed=self._current.armed and next_phase == "active",
        )
        self._record_change("update", snap)
        return snap

    def disarm(self) -> GoalSnapshot | None:
        """Process-local disarm (e.g. on crash/restart recovery before explicit resume)."""
        if self._current is None:
            return None
        snap = GoalSnapshot(
            **{
                **self._current.__dict__,
                "armed": False,
                "revision": self._current.revision + 1,
                "updated_at": time.time(),
            }
        )
        self._record_change("disarm", snap)
        return snap

    def resume(self) -> GoalSnapshot:
        """Re-arm an existing goal so same-session continuation resumes."""
        if self._current is None:
            raise ValueError("No goal to resume.")
        next_phase: GoalPhase = "active" if self._current.phase == "paused" else self._current.phase
        snap = GoalSnapshot(
            **{
                **self._current.__dict__,
                "phase": next_phase,
                "armed": next_phase == "active",
                "revision": self._current.revision + 1,
                "updated_at": time.time(),
            }
        )
        self._record_change("resume", snap)
        return snap

    def claim_continuation_prompt(self) -> str | None:
        """Called by `run_query` when a turn ends without tool calls.

        If an armed `active` goal remains below `max_rounds`, increments `rounds_used`
        and returns the continuation prompt to keep the agent working toward the goal.
        """
        cur = self._current
        if cur is None or cur.phase != "active" or not cur.armed:
            return None
        if cur.rounds_used >= cur.max_rounds:
            blocked = GoalBlockReason(
                code="MAX_GOAL_ROUNDS_EXCEEDED",
                message=f"Reached max_rounds ({cur.max_rounds}) without completion.",
            )
            self.update(phase="blocked", blocked_reason=blocked)
            return None

        next_round = cur.rounds_used + 1
        snap = GoalSnapshot(
            **{
                **cur.__dict__,
                "rounds_used": next_round,
                "revision": cur.revision + 1,
                "updated_at": time.time(),
            }
        )
        self._record_change("continue_round", snap)
        criteria_lines = "\n".join(f"- {c}" for c in snap.criteria) if snap.criteria else "(none specified)"
        return (
            f"<goal-continuation id=\"{snap.id}\" revision=\"{snap.revision}\" "
            f"round=\"{next_round}/{snap.max_rounds}\">\n"
            f"Active Goal Objective: {snap.objective}\n"
            f"Acceptance Criteria:\n{criteria_lines}\n\n"
            "Continue working toward the goal. When all acceptance criteria are verified, call "
            f"`goal(action=\"complete\", expected_revision={snap.revision}, progress_note=\"...\")`. "
            "If genuinely blocked, call `goal(action=\"block\", blocked_code=\"...\", blocked_message=\"...\")`.\n"
            "</goal-continuation>"
        )

    def _record_change(self, op: str, snapshot: GoalSnapshot) -> None:
        self._current = snapshot
        self._event_log.append(
            {
                "type": "goal/change",
                "op": op,
                "goal": snapshot.to_dict(),
            }
        )


class GoalToolInput(BaseModel):
    """Input schema for the `goal` state management tool."""

    action: Literal["get", "create", "update", "complete", "pause", "resume", "block"] = Field(
        description="Goal lifecycle action"
    )
    objective: str | None = Field(default=None, description="Goal objective (required for create)")
    criteria: list[str] | None = Field(default=None, description="Acceptance criteria list")
    expected_revision: int | None = Field(
        default=None,
        description="Optional CAS revision number to guard against stale updates",
    )
    progress_note: str | None = Field(default=None, description="Progress note to record on the goal")
    blocked_code: str | None = Field(default=None, description="Block reason code when action='block'")
    blocked_message: str | None = Field(default=None, description="Block reason detail when action='block'")
    max_rounds: int | None = Field(default=None, ge=1, le=256, description="Maximum continuation rounds")


class GoalToolOutputModel(BaseModel):
    """Structured output contract for `GoalTool`."""

    id: str
    revision: int
    objective: str
    phase: str
    criteria: list[str] = Field(default_factory=list)
    progress_notes: list[str] = Field(default_factory=list)
    blocked_reason: dict[str, str] | None = None
    rounds_used: int = 0
    max_rounds: int = 16
    armed: bool = True


class GoalTool(BaseTool):
    """Manage same-session durable continuation goals."""

    name = "goal"
    display_name = "Session Goal"
    description = (
        "Create, inspect, update, complete, or block a durable same-session goal (`GoalService`). "
        "While a goal is in `active` phase, the agent loop automatically continues across turns "
        "until the goal is marked `complete` or `blocked` or reaches `max_rounds`."
    )
    input_model = GoalToolInput
    output_model = GoalToolOutputModel

    def when(self, selection_context: Any) -> bool | None:
        meta = getattr(selection_context, "tool_metadata", None)
        if isinstance(meta, dict) and (meta.get("goal_service") is not None or meta.get("enable_goal")):
            return True
        return None

    def is_read_only(self, arguments: GoalToolInput) -> bool:
        return arguments.action == "get"

    async def execute(self, arguments: GoalToolInput, context: ToolExecutionContext) -> ToolResult:
        service = context.metadata.get("goal_service")
        if not isinstance(service, GoalService):
            service = GoalService()
            context.metadata["goal_service"] = service

        try:
            if arguments.action == "get":
                cur = service.current
                if cur is None:
                    return ToolResult(output="No active goal.", is_error=False)
                data = cur.to_dict()
                return ToolResult(
                    output=json.dumps(data, ensure_ascii=False, indent=2),
                    structured_output=data,
                )
            if arguments.action == "create":
                if not arguments.objective or not arguments.objective.strip():
                    return ToolResult(output="objective is required for action='create'", is_error=True)
                snap = service.create(
                    objective=arguments.objective,
                    criteria=arguments.criteria or (),
                    max_rounds=arguments.max_rounds,
                )
            elif arguments.action == "complete":
                snap = service.update(
                    expected_revision=arguments.expected_revision,
                    phase="complete",
                    progress_note=arguments.progress_note,
                )
            elif arguments.action == "pause":
                snap = service.update(
                    expected_revision=arguments.expected_revision,
                    phase="paused",
                    progress_note=arguments.progress_note,
                )
            elif arguments.action == "resume":
                snap = service.resume()
            elif arguments.action == "block":
                reason = GoalBlockReason(
                    code=arguments.blocked_code or "BLOCKED",
                    message=arguments.blocked_message or arguments.progress_note or "Blocked",
                )
                snap = service.update(
                    expected_revision=arguments.expected_revision,
                    phase="blocked",
                    progress_note=arguments.progress_note,
                    blocked_reason=reason,
                )
            else:
                snap = service.update(
                    expected_revision=arguments.expected_revision,
                    objective=arguments.objective,
                    criteria=arguments.criteria,
                    progress_note=arguments.progress_note,
                )
        except ValueError as exc:
            return ToolResult(output=str(exc), is_error=True)

        payload = snap.to_dict()
        return ToolResult(
            output=json.dumps(payload, ensure_ascii=False, indent=2),
            structured_output=payload,
        )
