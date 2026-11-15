"""Deterministic Agent Loop Testkit (`dsh-agent-loop-testkit` inspired).

Mounts the real OpenHarness query loop, tool registry, middlewares, hooks,
subagent runtime, goal service, and session projection store downstream of a
scripted deterministic model adapter so multi-turn agent flows run without API keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from openharness.api.client import ApiMessageCompleteEvent, ApiMessageRequest, ApiTextDeltaEvent
from openharness.api.usage import UsageSnapshot
from openharness.engine.inbox import AgentInbox
from openharness.coordinator.goal_service import GoalService
from openharness.coordinator.subagent_runtime import SubagentRuntime
from openharness.coordinator.task_board import TaskBoard
from openharness.engine.messages import ConversationMessage, TextBlock, ToolUseBlock
from openharness.engine.query import QueryContext, run_query
from openharness.engine.stream_events import AssistantTurnComplete, StreamEvent
from openharness.hooks.executor import HookExecutionContext, HookExecutor
from openharness.hooks.loader import HookRegistry
from openharness.permissions.checker import PermissionChecker
from openharness.permissions.modes import PermissionMode
from openharness.config.settings import PermissionSettings
from openharness.prompts.context import PromptContextTracker
from openharness.services.session_projection import SessionProjectionStore
from openharness.tools import ToolRegistry, create_default_tool_registry


@dataclass
class ScriptedModelTurn:
    """A single scripted assistant response turn for deterministic replay."""

    text: str = ""
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    input_tokens: int = 10
    output_tokens: int = 10

    def to_message(self) -> ConversationMessage:
        blocks: list[Any] = []
        if self.text:
            blocks.append(TextBlock(text=self.text))
        for idx, (t_name, t_input) in enumerate(self.tool_calls, start=1):
            blocks.append(ToolUseBlock(id=f"call_{idx}_{t_name}", name=t_name, input=dict(t_input)))
        return ConversationMessage(role="assistant", content=blocks)


class ScriptedModelAdapter:
    """Deterministic `SupportsStreamingMessages` adapter that records every request envelope."""

    def __init__(self, turns: list[ScriptedModelTurn | ConversationMessage]) -> None:
        self._turns = list(turns)
        self.requests: list[ApiMessageRequest] = []

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[Any]:
        self.requests.append(request)
        if not self._turns:
            msg = ConversationMessage(role="assistant", content=[TextBlock(text="(scripted turns exhausted)")])
            yield ApiMessageCompleteEvent(
                message=msg,
                usage=UsageSnapshot(input_tokens=1, output_tokens=1),
                stop_reason="end_turn",
            )
            return

        item = self._turns.pop(0)
        if isinstance(item, ScriptedModelTurn):
            msg = item.to_message()
            usage = UsageSnapshot(input_tokens=item.input_tokens, output_tokens=item.output_tokens)
        else:
            msg = item
            usage = UsageSnapshot(input_tokens=10, output_tokens=10)

        if msg.text:
            yield ApiTextDeltaEvent(text=msg.text)
        yield ApiMessageCompleteEvent(
            message=msg,
            usage=usage,
            stop_reason="tool_use" if msg.tool_uses else "end_turn",
        )


class AgentLoopTestHarness:
    """Full-fidelity test harness wiring real tools, hooks, projections, and subagents."""

    def __init__(
        self,
        *,
        cwd: Path,
        turns: list[ScriptedModelTurn | ConversationMessage],
        tool_registry: ToolRegistry | None = None,
        system_prompt: str = "You are a helpful test agent.",
        model: str = "deepseek-test",
        max_turns: int = 12,
        tool_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.cwd = Path(cwd)
        self.adapter = ScriptedModelAdapter(turns)
        self.tool_registry = tool_registry or create_default_tool_registry()
        self.hook_registry = HookRegistry()
        self.hook_executor = HookExecutor(
            self.hook_registry,
            HookExecutionContext(cwd=self.cwd, api_client=self.adapter, default_model=model),
        )
        self.inbox = AgentInbox()
        self.task_board = TaskBoard()
        self.goal_service = GoalService()
        self.prompt_context_tracker = PromptContextTracker()
        self.projection_store = SessionProjectionStore()
        self.permission_checker = PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))
        self.messages: list[ConversationMessage] = []

        self.tool_metadata: dict[str, Any] = {
            "enable_subagents": True,
            "task_board": self.task_board,
            "goal_service": self.goal_service,
            "prompt_context_tracker": self.prompt_context_tracker,
            "session_projection_store": self.projection_store,
            **(tool_metadata or {}),
        }
        self.subagent_runtime = SubagentRuntime(
            api_client=self.adapter,
            tool_registry=self.tool_registry,
            permission_checker=self.permission_checker,
            cwd=self.cwd,
            default_model=model,
            max_tokens=1024,
            base_tool_metadata=self.tool_metadata,
            root_inbox=self.inbox,
            task_board=self.task_board,
        )
        self.tool_metadata["subagent_runtime"] = self.subagent_runtime
        self.context = QueryContext(
            api_client=self.adapter,
            tool_registry=self.tool_registry,
            permission_checker=self.permission_checker,
            cwd=self.cwd,
            model=model,
            system_prompt=system_prompt,
            max_tokens=1024,
            max_turns=max_turns,
            hook_executor=self.hook_executor,
            tool_metadata=self.tool_metadata,
            inbox=self.inbox,
        )

    async def run(self, user_prompt: str) -> list[StreamEvent]:
        user_msg = ConversationMessage.from_user_text(user_prompt)
        self.messages.append(user_msg)
        self.projection_store.append_message(user_msg)
        events: list[StreamEvent] = []
        async for evt, _usage in run_query(self.context, self.messages):
            events.append(evt)
            if isinstance(evt, AssistantTurnComplete):
                self.projection_store.append_message(evt.message)
        return events
