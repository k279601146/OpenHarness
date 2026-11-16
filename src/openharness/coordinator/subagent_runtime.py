"""In-process asynchronous subagent runtime with steering, cold resume, and tree tracking."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from openharness.coordinator.agent_definitions import AgentDefinition, get_agent_definition
from openharness.coordinator.coordinator_mode import TaskNotification, format_task_notification
from openharness.coordinator.task_board import TaskBoard
from openharness.engine.inbox import AgentInbox
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.engine.stream_events import (
    AgentProgressEvent,
    AssistantTurnComplete,
    ErrorEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from openharness.tools.base import CancellationToken, ToolRegistry

log = logging.getLogger(__name__)

SubagentStatus = Literal["running", "completed", "failed", "interrupted"]

_PARENT_ONLY_TOOLS = frozenset(
    {
        "ask_user_question",
        "ask_user_form",
        "deliver_artifact",
    }
)

_TRANSIENT_METADATA_KEYS = frozenset(
    {
        "task_focus_state",
        "read_file_state",
        "recent_verified_work",
        "subagent_runtime",
        "subagent_id",
        "subagent_name",
        "subagent_depth",
        "subagent_inbox",
        "parent_completed_messages",
    }
)


def _normalize_agent_name(raw_name: str | None, fallback_index: int) -> str:
    text = (raw_name or "").strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text).strip("-_")
    return text or f"agent-{fallback_index}"


_SENSITIVE_KEY_PATTERN = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|authorization|cookie|jwt|credential|private[_-]?key)",
    re.IGNORECASE,
)


def _truncate_preview(text: str | None, limit: int = 1200) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def _summarize_tool_input(tool_input: dict[str, Any] | None) -> str:
    if not isinstance(tool_input, dict) or not tool_input:
        return ""
    safe: dict[str, Any] = {}
    for key, value in list(tool_input.items())[:8]:
        key_str = str(key)
        if _SENSITIVE_KEY_PATTERN.search(key_str):
            safe[key_str] = "***"
        elif isinstance(value, str):
            safe[key_str] = _truncate_preview(value, 240)
        elif isinstance(value, (int, float, bool)) or value is None:
            safe[key_str] = value
        elif isinstance(value, (list, dict)):
            safe[key_str] = _truncate_preview(str(value), 240)
        else:
            safe[key_str] = _truncate_preview(str(value), 120)
    try:
        import json

        return json.dumps(safe, ensure_ascii=False)
    except Exception:
        return _truncate_preview(str(safe), 480)


@dataclass
class SubagentRecord:
    """Tracked state for one in-process async subagent."""

    agent_id: str
    name: str
    description: str
    subagent_type: str
    parent_id: str
    parent_inbox: AgentInbox | None
    depth: int
    model: str
    max_turns: int
    system_prompt: str
    inbox: AgentInbox = field(default_factory=AgentInbox)
    cancellation_token: CancellationToken = field(default_factory=CancellationToken)
    history: list[ConversationMessage] = field(default_factory=list)
    tool_registry: ToolRegistry | None = None
    status: SubagentStatus = "running"
    output: str = ""
    structured_output: Any = None
    output_schema: dict[str, Any] | None = None
    preset: str | None = None
    external_cli: str | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    turns_used: int = 0
    tool_calls_count: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    task: asyncio.Task[None] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_running(self) -> bool:
        return self.status == "running" and self.task is not None and not self.task.done()

    def to_summary(self) -> dict[str, Any]:
        """Serialize a compact JSON-friendly view of this subagent."""
        now = time.time()
        end = self.finished_at or now
        start = self.started_at or self.created_at
        preview = self.output.strip()
        if len(preview) > 280:
            preview = preview[:277] + "..."
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "subagent_type": self.subagent_type,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "status": self.status,
            "model": self.model,
            "inherit_context": bool(self.metadata.get("inherit_context")),
            "turns_used": self.turns_used,
            "tool_calls_count": self.tool_calls_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "elapsed_seconds": round(max(0.0, end - start), 2),
            "output_preview": preview,
            "structured_output": self.structured_output,
            "preset": self.preset,
            "external_cli": self.external_cli,
            "error": self.error,
        }


class SubagentRuntime:
    """In-process asynchronous subagent coordinator inspired by DeepSeek Harness.

    Features:
    - Non-blocking ``spawn`` returning ``agent_id`` immediately so lead/parents can
      launch parallel workers and continue working or call ``wait_agent``.
    - Hierarchical tree paths (``<parent>/<name>``) and depth guard (``max_depth``).
    - Live mid-turn steering via ``send_message`` when running, and cold resume
      from retained ``history`` when completed/interrupted/failed.
    - Completion ``<task-notification>`` pushed directly to the spawning parent's
      ``AgentInbox`` so ``wait_agent`` and the step loop wake up immediately.
    - Isolated ``event_queue`` for forwarding structured progress events to the host
      stream without letting child tasks touch SaaS database sessions.
    """

    def __init__(
        self,
        *,
        api_client: Any,
        tool_registry: ToolRegistry,
        permission_checker: Any,
        cwd: Path,
        default_model: str,
        max_tokens: int = 8192,
        effort: str | None = None,
        system_prompt: str = "",
        max_depth: int = 2,
        default_max_turns: int = 40,
        max_agents: int = 32,
        root_inbox: AgentInbox | None = None,
        task_board: TaskBoard | None = None,
        base_tool_metadata: dict[str, Any] | None = None,
        root_cancellation_token: CancellationToken | None = None,
    ) -> None:
        self._api_client = api_client
        self._tool_registry = tool_registry
        self._permission_checker = permission_checker
        self._cwd = cwd
        self._default_model = default_model
        self._max_tokens = max(512, int(max_tokens))
        self._effort = effort
        self._base_system_prompt = system_prompt
        self._max_depth = max(1, int(max_depth))
        self._default_max_turns = max(1, int(default_max_turns))
        self._max_agents = max(1, int(max_agents))
        self._root_inbox = root_inbox or AgentInbox()
        self._task_board = task_board or TaskBoard()
        self._base_tool_metadata = dict(base_tool_metadata or {})
        self._root_cancellation_token = root_cancellation_token

        self._records: dict[str, SubagentRecord] = {}
        self._order: list[str] = []
        self._counter = 0
        self._completion_condition = asyncio.Condition()
        self.event_queue: asyncio.Queue[AgentProgressEvent] = asyncio.Queue()

    @property
    def max_depth(self) -> int:
        return self._max_depth

    @property
    def root_inbox(self) -> AgentInbox:
        return self._root_inbox

    @property
    def task_board(self) -> TaskBoard:
        return self._task_board

    def get(self, agent_id: str) -> SubagentRecord | None:
        """Look up a subagent record by exact ID or unambiguous leaf name."""
        if agent_id in self._records:
            return self._records[agent_id]
        matches = [
            rec
            for rec in self._records.values()
            if rec.name == agent_id or rec.agent_id.endswith(f"/{agent_id}")
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def list_agents(self, *, parent_id: str | None = None) -> list[dict[str, Any]]:
        """List tracked subagents in creation order."""
        items: list[dict[str, Any]] = []
        for agent_id in self._order:
            rec = self._records.get(agent_id)
            if rec is None:
                continue
            if parent_id is not None and rec.parent_id != parent_id:
                continue
            items.append(rec.to_summary())
        return items

    def running_ids(self, *, parent_id: str | None = None) -> list[str]:
        """Return currently running subagent IDs."""
        return [
            agent_id
            for agent_id in self._order
            if (rec := self._records.get(agent_id)) is not None
            and rec.status == "running"
            and (parent_id is None or rec.parent_id == parent_id)
        ]

    def has_running(self, *, parent_id: str | None = None) -> bool:
        """Return True when any tracked subagent is still running."""
        return bool(self.running_ids(parent_id=parent_id))

    def total_usage(self) -> dict[str, int]:
        """Aggregate token and tool telemetry across all subagents."""
        input_tokens = 0
        output_tokens = 0
        turns = 0
        tool_calls = 0
        for rec in self._records.values():
            input_tokens += rec.input_tokens
            output_tokens += rec.output_tokens
            turns += rec.turns_used
            tool_calls += rec.tool_calls_count
        return {
            "agent_count": len(self._records),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "turns_used": turns,
            "tool_calls_count": tool_calls,
        }

    def drain_events(self) -> list[AgentProgressEvent]:
        """Non-blockingly drain all pending progress events from subagents."""
        events: list[AgentProgressEvent] = []
        while True:
            try:
                events.append(self.event_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return events

    def _emit_event(
        self,
        *,
        category: str,
        message: str,
        status: str,
        agent: str,
        tool_name: str | None = None,
        tool_use_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized_status: Literal["running", "success", "error", "info"]
        if status in {"completed", "success"}:
            normalized_status = "success"
        elif status in {"failed", "error"}:
            normalized_status = "error"
        elif status in {"interrupted", "warning", "interrupting", "info"}:
            normalized_status = "info"
        else:
            normalized_status = "running"

        event_metadata = dict(metadata or {})
        event_metadata.setdefault("agent_id", agent)
        self.event_queue.put_nowait(
            AgentProgressEvent(
                phase=category,
                status=normalized_status,
                message=message,
                tool_name=tool_name,
                tool_use_id=tool_use_id,
                workspace=str(self._base_tool_metadata.get("workspace_backend") or "") or None,
                detail=agent,
                metadata=event_metadata,
            )
        )

    def _build_child_registry(
        self,
        definition: AgentDefinition | None,
        *,
        next_depth: int,
    ) -> ToolRegistry:
        child_registry = ToolRegistry()
        allowed_set: set[str] | None = None
        if definition and definition.tools and "*" not in definition.tools:
            allowed_set = {name.strip() for name in definition.tools if name.strip()}
        disallowed_set = set(_PARENT_ONLY_TOOLS)
        if definition and definition.disallowed_tools:
            disallowed_set.update(name.strip() for name in definition.disallowed_tools if name.strip())
        if next_depth >= self._max_depth:
            disallowed_set.add("agent")

        for tool in self._tool_registry.list_tools():
            if tool.name in disallowed_set:
                continue
            if allowed_set is not None and tool.name not in allowed_set:
                continue
            child_registry.register(tool)
        return child_registry

    def _build_child_system_prompt(
        self,
        *,
        agent_id: str,
        parent_id: str,
        depth: int,
        definition: AgentDefinition | None,
        subagent_type: str,
        inherit_context: bool = False,
    ) -> str:
        sections: list[str] = [
            f"You are subagent `{agent_id}` (type `{subagent_type}`, depth {depth}/{self._max_depth}), "
            f"spawned by `{parent_id}` inside a coordinated multi-agent session.\n"
            f'Your name is "{agent_id}". The root agent of your collaboration tree is "lead".',
            (
                "Work autonomously to complete the assigned task using your available tools. "
                "Do not ask the user interactive questions; report blockers or uncertainties back to your parent. "
                "When finished, produce a concise, factual summary including exact findings, modified files, "
                "symbols, and verification output."
            ),
        ]
        if inherit_context:
            sections.append(
                f"You inherited completed conversation turns from `{parent_id}` prior to this fork point "
                "(excluding its in-flight tool invocation). Build directly on verified facts already in your "
                "history instead of re-reading unchanged files unless freshness matters."
            )
        if depth < self._max_depth:
            sections.append(
                "Start independent delegations with `agent` together in one assistant message when subtasks "
                "can run in parallel, and end your turn when only waiting for their results remains."
            )
        else:
            sections.append(
                f"Delegation depth for `agent`: current {depth}, maximum {self._max_depth}, remaining levels 0. "
                "Do not call `agent` at this depth; carry out the work directly."
            )
        if definition and definition.system_prompt:
            sections.append(f"## Role Instructions ({definition.name})\n{definition.system_prompt.strip()}")
        return "\n\n".join(sections)

    async def spawn(
        self,
        *,
        description: str,
        prompt: str,
        subagent_type: str | None = None,
        name: str | None = None,
        model: str | None = None,
        max_turns: int | None = None,
        parent_id: str = "lead",
        parent_depth: int = 0,
        parent_inbox: AgentInbox | None = None,
        parent_cancellation_token: CancellationToken | None = None,
        inherit_context: bool = False,
        inherited_history: list[ConversationMessage] | None = None,
        output_schema: dict[str, Any] | None = None,
        preset: str | None = None,
        external_cli: str | None = None,
    ) -> SubagentRecord:
        """Spawn a new asynchronous in-process subagent and return immediately."""
        next_depth = parent_depth + 1
        if next_depth > self._max_depth:
            raise ValueError(
                f"Subagent depth limit reached (depth {next_depth} > max_depth {self._max_depth})."
            )
        if len(self._records) >= self._max_agents:
            raise ValueError(
                f"Subagent limit reached ({self._max_agents} agents per run)."
            )

        self._counter += 1
        resolved_type = (subagent_type or "general-purpose").strip() or "general-purpose"
        definition = get_agent_definition(resolved_type)

        base_name = _normalize_agent_name(name or subagent_type, self._counter)
        prefix = "" if parent_id in {"", "lead"} else f"{parent_id}/"
        candidate_id = f"{prefix}{base_name}"
        if candidate_id in self._records:
            suffix = 2
            while f"{prefix}{base_name}-{suffix}" in self._records:
                suffix += 1
            base_name = f"{base_name}-{suffix}"
            candidate_id = f"{prefix}{base_name}"

        resolved_preset = None
        if preset or subagent_type:
            from openharness.coordinator.agent_preset import DEFAULT_PRESET_REGISTRY

            resolved_preset = DEFAULT_PRESET_REGISTRY.get(preset or subagent_type)

        resolved_model = (
            model
            or (resolved_preset.model if resolved_preset and resolved_preset.model else None)
            or (definition.model if definition and definition.model else None)
            or self._default_model
        )
        resolved_max_turns = max(
            1,
            int(
                max_turns
                or (resolved_preset.max_turns if resolved_preset and resolved_preset.max_turns else None)
                or (definition.max_turns if definition and definition.max_turns else None)
                or self._default_max_turns
            ),
        )
        effective_prompt = prompt
        if output_schema:
            schema_json = json.dumps(output_schema, ensure_ascii=False, indent=2)
            effective_prompt = (
                f"{prompt}\n\n"
                "## Required Structured Output Contract\n"
                "Your final response MUST include a valid JSON block matching the following JSON Schema:\n"
                f"```json\n{schema_json}\n```"
            )
        initial_history: list[ConversationMessage] = []
        if inherit_context and inherited_history:
            for msg in inherited_history:
                initial_history.append(msg.model_copy(deep=True))
            while initial_history and initial_history[-1].role == "assistant" and initial_history[-1].tool_uses:
                initial_history.pop()
        has_inherited_turns = bool(initial_history)
        if initial_history and initial_history[-1].role == "user":
            merged_blocks = list(initial_history[-1].content)
            merged_blocks.append(TextBlock(text=f"\n\n[Forked Subtask Assignment]\n{effective_prompt}"))
            initial_history[-1] = ConversationMessage(role="user", content=merged_blocks)
        else:
            initial_history.append(ConversationMessage.from_user_text(effective_prompt))

        child_registry = self._build_child_registry(definition, next_depth=next_depth)
        child_prompt = self._build_child_system_prompt(
            agent_id=candidate_id,
            parent_id=parent_id,
            depth=next_depth,
            definition=definition,
            subagent_type=resolved_type,
            inherit_context=has_inherited_turns,
        )
        if resolved_preset and resolved_preset.system_prompt_sections:
            child_prompt = child_prompt + "\n\n" + "\n\n".join(resolved_preset.system_prompt_sections)

        resolved_external_cli = external_cli or (resolved_preset.external_cli if resolved_preset else None)
        record_metadata: dict[str, Any] = {
            "parent_cancellation_token": parent_cancellation_token,
            "inherit_context": has_inherited_turns,
            "raw_prompt": prompt,
        }
        if resolved_preset is not None:
            record_metadata = resolved_preset.apply_to_metadata(record_metadata)

        record = SubagentRecord(
            agent_id=candidate_id,
            name=base_name,
            description=description.strip() or f"Subagent {candidate_id}",
            subagent_type=resolved_type,
            parent_id=parent_id or "lead",
            parent_inbox=parent_inbox or self._root_inbox,
            depth=next_depth,
            model=resolved_model,
            max_turns=resolved_max_turns,
            system_prompt=child_prompt,
            tool_registry=child_registry,
            history=initial_history,
            started_at=time.time(),
            output_schema=output_schema,
            preset=resolved_preset.name if resolved_preset else preset,
            external_cli=resolved_external_cli,
            metadata=record_metadata,
        )
        self._records[candidate_id] = record
        self._order.append(candidate_id)

        self._emit_event(
            category="subagent_started",
            message=f"已启动异步子智能体 {candidate_id}：{record.description}",
            status="running",
            agent=candidate_id,
            metadata={
                "agent_id": candidate_id,
                "name": record.name,
                "parent_id": record.parent_id,
                "depth": record.depth,
                "subagent_type": record.subagent_type,
                "model": record.model,
                "inherit_context": has_inherited_turns,
                "description": record.description,
                "prompt_preview": _truncate_preview(prompt, 2000),
            },
        )
        record.task = asyncio.create_task(
            self._execute_record(record, is_resume=False),
            name=f"openharness-subagent-{candidate_id}",
        )
        return record

    async def send_message(
        self,
        *,
        target_id: str,
        message: str,
        source: str = "lead",
    ) -> dict[str, Any]:
        """Deliver a steering message to a live subagent or cold-resume an idle one."""
        normalized_target = target_id.strip()
        if normalized_target == "lead":
            inbox_msg = await self._root_inbox.steer(
                f"[Message from {source}]\n{message}",
                source=source,
                metadata={"from": source},
            )
            return {
                "delivery": "steered_lead",
                "agent_id": "lead",
                "message_id": inbox_msg.id,
                "status": "queued",
            }

        record = self.get(normalized_target)
        if record is None:
            raise KeyError(f"Unknown subagent: {target_id}")

        formatted = f"[Message from {source}]\n{message}"
        if record.is_running:
            inbox_msg = await record.inbox.steer(
                formatted,
                source=source,
                metadata={"from": source, "target": record.agent_id},
            )
            self._emit_event(
                category="subagent_steered",
                message=f"向运行中子智能体 {record.agent_id} 发送实时转向指令",
                status="running",
                agent=record.agent_id,
                metadata={
                    "agent_id": record.agent_id,
                    "message_id": inbox_msg.id,
                    "source": source,
                    "steer_message": _truncate_preview(message, 1000),
                },
            )
            return {
                "delivery": "steered",
                "agent_id": record.agent_id,
                "message_id": inbox_msg.id,
                "status": record.status,
            }

        # Cold resume: continue conversation history in a fresh background run.
        record.cancellation_token = CancellationToken()
        record.status = "running"
        record.error = None
        record.finished_at = None
        record.started_at = time.time()
        record.history.append(ConversationMessage.from_user_text(formatted))
        self._emit_event(
            category="subagent_resumed",
            message=f"唤醒子智能体 {record.agent_id} 继续执行任务",
            status="running",
            agent=record.agent_id,
            metadata={
                "agent_id": record.agent_id,
                "source": source,
                "steer_message": _truncate_preview(message, 1000),
            },
        )
        record.task = asyncio.create_task(
            self._execute_record(record, is_resume=True),
            name=f"openharness-subagent-{record.agent_id}-resume",
        )
        return {
            "delivery": "resumed",
            "agent_id": record.agent_id,
            "status": "running",
        }

    async def interrupt_agent(
        self,
        agent_id: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Request cancellation of a running subagent."""
        record = self.get(agent_id.strip())
        if record is None:
            raise KeyError(f"Unknown subagent: {agent_id}")

        was_running = record.is_running
        record.cancellation_token.cancel()
        if was_running:
            self._emit_event(
                category="subagent_interrupt_requested",
                message=f"已请求中断子智能体 {record.agent_id}"
                + (f"（{reason}）" if reason else ""),
                status="interrupting",
                agent=record.agent_id,
                metadata={"agent_id": record.agent_id, "reason": reason or ""},
            )
        return {
            "agent_id": record.agent_id,
            "was_running": was_running,
            "status": record.status,
            "reason": reason or "",
        }

    async def wait_for_agents(
        self,
        *,
        agent_ids: list[str] | None = None,
        parent_id: str | None = None,
        caller_inbox: AgentInbox | None = None,
        timeout_seconds: float = 60.0,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, Any]:
        """Block until target subagents complete or timeout/cancellation hits."""
        target_records: list[SubagentRecord] = []
        missing_ids: list[str] = []
        if agent_ids:
            for raw_id in agent_ids:
                rec = self.get(raw_id.strip())
                if rec is None:
                    missing_ids.append(raw_id)
                else:
                    target_records.append(rec)
        else:
            for aid in self._order:
                rec = self._records.get(aid)
                if rec is None:
                    continue
                if parent_id is not None and rec.parent_id != parent_id:
                    continue
                target_records.append(rec)

        if not target_records:
            return {
                "completed": [],
                "still_running": [],
                "missing": missing_ids,
                "timed_out": False,
                "message": "No matching subagents found.",
            }

        target_id_set = {rec.agent_id for rec in target_records}
        seen_inbox_ids = caller_inbox.next_step_ids() if caller_inbox is not None else set()
        deadline = time.monotonic() + max(0.05, float(timeout_seconds))
        timed_out = False

        while True:
            if cancellation_token is not None and cancellation_token.is_cancelled():
                break
            finished_targets = [rec for rec in target_records if not rec.is_running]
            running_targets = [rec for rec in target_records if rec.is_running]
            if not running_targets:
                break
            if caller_inbox is not None:
                unseen_for_targets = [
                    msg
                    for msg in caller_inbox.next_step
                    if msg.id not in seen_inbox_ids
                    and msg.metadata.get("subagent_id") in target_id_set
                ]
                if unseen_for_targets:
                    break
            elif finished_targets and not agent_ids:
                break

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break

            step_timeout = min(remaining, 0.5)
            async with self._completion_condition:
                running_targets = [rec for rec in target_records if rec.is_running]
                if not running_targets:
                    break
                try:
                    await asyncio.wait_for(self._completion_condition.wait(), timeout=step_timeout)
                except asyncio.TimeoutError:
                    pass

        completed_items = [
            {
                **rec.to_summary(),
                "output": rec.output,
                "structured_output": rec.structured_output,
            }
            for rec in target_records
            if not rec.is_running
        ]
        still_running = [rec.agent_id for rec in target_records if rec.is_running]
        return {
            "completed": completed_items,
            "still_running": still_running,
            "missing": missing_ids,
            "timed_out": timed_out,
        }

    async def shutdown_all(self, *, timeout_seconds: float = 2.0) -> None:
        """Cancel and clean up any remaining running child agent tasks."""
        active_tasks: list[asyncio.Task[None]] = []
        for rec in self._records.values():
            rec.cancellation_token.cancel()
            if rec.task is not None and not rec.task.done():
                active_tasks.append(rec.task)
        if not active_tasks:
            return
        done, pending = await asyncio.wait(active_tasks, timeout=max(0.1, float(timeout_seconds)))
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _watch_parent_cancellation(
        self,
        child_token: CancellationToken,
        parent_tokens: list[CancellationToken],
    ) -> None:
        if not parent_tokens:
            return
        wait_tasks = [asyncio.create_task(tok.wait()) for tok in parent_tokens]
        try:
            done, pending = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()
            if done:
                child_token.cancel()
        except asyncio.CancelledError:
            for wt in wait_tasks:
                wt.cancel()
            raise

    async def _execute_record(self, record: SubagentRecord, *, is_resume: bool) -> None:
        from openharness.engine.query import QueryContext, run_query  # noqa: PLC0415

        parent_tokens: list[CancellationToken] = []
        parent_token = record.metadata.get("parent_cancellation_token")
        if isinstance(parent_token, CancellationToken):
            parent_tokens.append(parent_token)
        if (
            self._root_cancellation_token is not None
            and self._root_cancellation_token is not parent_token
        ):
            parent_tokens.append(self._root_cancellation_token)

        watcher_task: asyncio.Task[None] | None = None
        if any(tok.is_cancelled() for tok in parent_tokens):
            record.cancellation_token.cancel()
        elif parent_tokens:
            watcher_task = asyncio.create_task(
                self._watch_parent_cancellation(record.cancellation_token, parent_tokens),
                name=f"openharness-cancel-watch-{record.agent_id}",
            )

        child_metadata: dict[str, Any] = {
            k: v for k, v in self._base_tool_metadata.items() if k not in _TRANSIENT_METADATA_KEYS
        }
        for preset_key in ("active_agent_preset", "preset_allowed_tools", "preset_disallowed_tools", "allowed_user_skill_ids", "preset_read_only"):
            if preset_key in record.metadata:
                child_metadata[preset_key] = record.metadata[preset_key]
        child_metadata.update(
            {
                "subagent_runtime": self,
                "subagent_id": record.agent_id,
                "subagent_name": record.name,
                "subagent_depth": record.depth,
                "subagent_max_depth": self._max_depth,
                "subagent_inbox": record.inbox,
                "enable_subagents": record.depth < self._max_depth,
                "task_board": self._task_board,
            }
        )

        context = QueryContext(
            api_client=self._api_client,
            tool_registry=record.tool_registry or self._tool_registry,
            permission_checker=self._permission_checker,
            cwd=self._cwd,
            model=record.model,
            system_prompt=record.system_prompt,
            max_tokens=self._max_tokens,
            effort=self._effort,
            max_turns=record.max_turns,
            tool_metadata=child_metadata,
            cancellation_token=record.cancellation_token,
            inbox=record.inbox,
            auto_drain_subagents=True,
        )

        last_assistant_text = ""
        last_error: str | None = None
        terminal_status: SubagentStatus = "completed"
        tool_started_at: dict[str, float] = {}
        try:
            if record.external_cli:
                # External CLI coding-agent adapter (`subagent-oar` pattern)
                import shlex
                from openharness.utils.shell import create_shell_subprocess

                raw_prompt = str(record.metadata.get("raw_prompt") or "")
                cli_spec = record.external_cli.strip()
                if "{prompt}" in cli_spec:
                    cmd_str = cli_spec.replace("{prompt}", shlex.quote(raw_prompt))
                else:
                    cmd_str = f"{cli_spec} {shlex.quote(raw_prompt)}"
                proc = await create_shell_subprocess(
                    cmd_str,
                    cwd=self._cwd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_b, stderr_b = await proc.communicate()
                record.turns_used += 1
                out_str = stdout_b.decode("utf-8", errors="replace").strip()
                err_str = stderr_b.decode("utf-8", errors="replace").strip()
                last_assistant_text = out_str or err_str
                if proc.returncode != 0:
                    last_error = err_str or f"External CLI exited with code {proc.returncode}"
            else:
                while True:
                    async for event, _usage in run_query(context, record.history):
                        if isinstance(event, AssistantTurnComplete):
                            record.turns_used += 1
                            turn_in = int(event.usage.input_tokens or 0) if event.usage is not None else 0
                            turn_out = int(event.usage.output_tokens or 0) if event.usage is not None else 0
                            record.input_tokens += turn_in
                            record.output_tokens += turn_out
                            text = event.message.text.strip()
                            if text:
                                last_assistant_text = text
                            tool_names_in_turn = [tu.name for tu in getattr(event.message, "tool_uses", ())]
                            if text or tool_names_in_turn:
                                self._emit_event(
                                    category="subagent_turn",
                                    message=f"[{record.agent_id}] 第 {record.turns_used} 轮模型响应",
                                    status="running",
                                    agent=record.agent_id,
                                    metadata={
                                        "agent_id": record.agent_id,
                                        "turn_index": record.turns_used,
                                        "text_preview": _truncate_preview(text, 3000),
                                        "tool_calls_in_turn": len(tool_names_in_turn),
                                        "tool_names": tool_names_in_turn[:8],
                                        "input_tokens": turn_in,
                                        "output_tokens": turn_out,
                                    },
                                )
                        elif isinstance(event, ToolExecutionStarted):
                            record.tool_calls_count += 1
                            if event.tool_use_id:
                                tool_started_at[event.tool_use_id] = time.monotonic()
                            self._emit_event(
                                category="subagent_tool",
                                message=f"[{record.agent_id}] 调用工具 {event.tool_name}",
                                status="running",
                                agent=record.agent_id,
                                tool_name=event.tool_name,
                                tool_use_id=event.tool_use_id,
                                metadata={
                                    "agent_id": record.agent_id,
                                    "tool_name": event.tool_name,
                                    "tool_use_id": event.tool_use_id,
                                    "tool_input_preview": _summarize_tool_input(event.tool_input),
                                    "rationale": _truncate_preview(event.rationale, 400) if event.rationale else "",
                                },
                            )
                        elif isinstance(event, ToolExecutionCompleted):
                            started_t = tool_started_at.pop(event.tool_use_id, None) if event.tool_use_id else None
                            duration_ms = int(max(0.0, (time.monotonic() - started_t) * 1000)) if started_t is not None else None
                            self._emit_event(
                                category="subagent_tool_error" if event.is_error else "subagent_tool_result",
                                message=(
                                    f"[{record.agent_id}] 工具 {event.tool_name} 返回错误"
                                    if event.is_error
                                    else f"[{record.agent_id}] 工具 {event.tool_name} 执行完成"
                                ),
                                status="info",
                                agent=record.agent_id,
                                tool_name=event.tool_name,
                                tool_use_id=event.tool_use_id,
                                metadata={
                                    "agent_id": record.agent_id,
                                    "tool_name": event.tool_name,
                                    "tool_use_id": event.tool_use_id,
                                    "is_error": bool(event.is_error),
                                    "output_preview": _truncate_preview(event.output, 2000),
                                    **({"duration_ms": duration_ms} if duration_ms is not None else {}),
                                },
                            )
                        elif isinstance(event, ErrorEvent):
                            last_error = event.message

                    if record.cancellation_token.is_cancelled():
                        break
                    queued_turn = record.inbox.claim_next_turn()
                    if queued_turn is None:
                        break
                    follow_text = queued_turn.content if isinstance(queued_turn.content, str) else str(queued_turn.content)
                    record.history.append(ConversationMessage.from_user_text(follow_text))

            if record.cancellation_token.is_cancelled():
                terminal_status = "interrupted"
                record.output = last_assistant_text or "Subagent interrupted."
            elif last_error:
                terminal_status = "failed"
                record.error = last_error
                record.output = last_assistant_text or last_error
            else:
                terminal_status = "completed"
                record.output = last_assistant_text or "(no output)"
                if record.output_schema:
                    from openharness.coordinator.agent_preset import extract_and_validate_structured_output

                    parsed_out, schema_err = extract_and_validate_structured_output(
                        record.output,
                        record.output_schema,
                    )
                    if schema_err is None:
                        record.structured_output = parsed_out
                    else:
                        record.metadata["output_schema_validation_error"] = schema_err
        except asyncio.CancelledError:
            terminal_status = "interrupted"
            record.output = last_assistant_text or "Subagent cancelled."
        except Exception as exc:
            log.exception("Subagent %s execution failed", record.agent_id)
            terminal_status = "failed"
            record.error = str(exc)
            record.output = last_assistant_text or f"Subagent failed: {exc}"
        finally:
            if watcher_task is not None and not watcher_task.done():
                watcher_task.cancel()
                await asyncio.gather(watcher_task, return_exceptions=True)

            record.finished_at = time.time()
            notif_status: Literal["completed", "failed", "killed"]
            if terminal_status == "completed":
                notif_status = "completed"
                event_category = "subagent_completed"
                summary_msg = f"子智能体 {record.agent_id} 已完成（{record.turns_used} 轮，{record.tool_calls_count} 次工具调用）"
            elif terminal_status == "interrupted":
                notif_status = "killed"
                event_category = "subagent_interrupted"
                summary_msg = f"子智能体 {record.agent_id} 已中断"
            else:
                notif_status = "failed"
                event_category = "subagent_failed"
                summary_msg = f"子智能体 {record.agent_id} 执行失败：{record.error or 'unknown error'}"

            # Deliver notification to parent_inbox BEFORE flipping status out of "running"
            # so auto-drain loops never observe has_running()==False before inbox notification lands.
            if record.parent_inbox is not None:
                notification = TaskNotification(
                    task_id=record.agent_id,
                    status=notif_status,
                    summary=f"{record.agent_id} ({record.description}) {terminal_status}",
                    result=record.output,
                    usage={
                        "total_tokens": record.input_tokens + record.output_tokens,
                        "tool_uses": record.tool_calls_count,
                        "duration_ms": int(
                            max(0.0, (record.finished_at or time.time()) - (record.started_at or record.created_at))
                            * 1000
                        ),
                    },
                )
                try:
                    await record.parent_inbox.append(
                        format_task_notification(notification),
                        target="next_step",
                        source=f"subagent:{record.agent_id}",
                        metadata={
                            "subagent_id": record.agent_id,
                            "status": terminal_status,
                        },
                    )
                except Exception:
                    log.debug("Failed to deliver subagent notification for %s", record.agent_id, exc_info=True)

            record.status = terminal_status
            self._emit_event(
                category=event_category,
                message=summary_msg,
                status=terminal_status,
                agent=record.agent_id,
                metadata={
                    **record.to_summary(),
                    "output_detail": _truncate_preview(record.output, 8000),
                    "is_resume": is_resume,
                },
            )

            async with self._completion_condition:
                self._completion_condition.notify_all()
