"""Tool for spawning local agent tasks."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from openharness.coordinator.agent_definitions import get_agent_definition
from openharness.coordinator.coordinator_mode import get_team_registry
from openharness.hooks import HookEvent
from openharness.swarm.registry import get_backend_registry
from openharness.swarm.types import TeammateSpawnConfig
from openharness.tasks import get_task_manager
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

logger = logging.getLogger(__name__)


class AgentToolInput(BaseModel):
    """Arguments for local agent spawning."""

    description: str = Field(
        description=(
            "A short (3-5 word) description of the delegated task, for display. "
            "Use the language of the user's current request."
        )
    )
    prompt: str = Field(
        description=(
            "The complete, self-contained task for the subagent. When `inherit_context=False` (default), "
            "it does not share this conversation's context, so include everything it needs. "
            "When `inherit_context=True`, it already sees this conversation's completed turns, "
            "so build on them freely and state only what is new."
        )
    )
    name: str | None = Field(
        default=None,
        description=(
            "Optional short name for the subagent, unique among the subagents you create: "
            "lower-case letters, digits, and hyphens, starting with a letter, at most 32 characters; "
            "lead is reserved for the root agent. Omitted names default to agent-1, agent-2, and so on."
        ),
    )
    inherit_context: bool = Field(
        default=False,
        description=(
            "When false (default), start a fresh isolated subagent that works in its own context. "
            "When true, delegate to a child agent seeded with all completed turns so far (excluding the "
            "current in-flight turn) for follow-up analysis, review, or verification."
        ),
    )
    output_schema: dict[str, object] | None = Field(
        default=None,
        description="Optional JSON Schema dict that the subagent's final output must conform to.",
    )
    subagent_type: str | None = Field(
        default=None,
        description="Agent type for definition lookup (e.g. 'general-purpose', 'Explore', 'worker')",
    )
    model: str | None = Field(default=None)
    max_turns: int | None = Field(default=None, ge=1, description="Optional maximum turns for this subagent")
    preset: str | None = Field(
        default=None,
        description="Optional AgentPreset name (e.g. 'researcher', 'coder', 'short_drama', 'voice').",
    )
    external_cli: str | None = Field(
        default=None,
        description="Optional external CLI coding-agent command (subagent-oar adapter).",
    )
    command: str | None = Field(default=None, description="Override spawn command")
    team: str | None = Field(default=None, description="Optional team to attach the agent to")
    mode: str = Field(
        default="local_agent",
        description="Agent mode: local_agent, remote_agent, or in_process_teammate",
    )


_HIDDEN_AGENT_SCHEMA_FIELDS = frozenset(
    {
        "subagent_type",
        "model",
        "max_turns",
        "preset",
        "external_cli",
        "command",
        "team",
        "mode",
    }
)


class AgentTool(BaseTool):
    """Spawn a local asynchronous subagent."""

    name = "agent"
    description = (
        "Delegate a self-contained task to a subagent (a separate agent that works in its own context) "
        "to offload focused, independent work — research, multi-target comparison, document review, "
        "a scoped implementation, or an analysis — so it does not consume this conversation's context. "
        "The subagent returns its result, not its intermediate steps. "
        "This tool starts an independently managed subagent and immediately returns its name (`agent_id`). "
        "If you are still online when it finishes, the runtime automatically delivers its completion notice. "
        "Use `send_message` to steer it while running or continue its conversation after it finishes."
    )
    input_model = AgentToolInput
    execution_group = "task_manager"

    def to_api_schema(self) -> dict[str, object]:
        schema = super().to_api_schema()
        input_schema = schema.get("input_schema")
        if isinstance(input_schema, dict):
            props = input_schema.get("properties")
            if isinstance(props, dict):
                for hidden_key in _HIDDEN_AGENT_SCHEMA_FIELDS:
                    props.pop(hidden_key, None)
        return schema

    def is_concurrency_safe(self, arguments: AgentToolInput) -> bool:
        """Spawning independent subagents can run concurrently when no custom CLI command is set."""
        return arguments.command is None

    async def execute(self, arguments: AgentToolInput, context: ToolExecutionContext) -> ToolResult:
        if arguments.mode not in {"local_agent", "remote_agent", "in_process_teammate", "in_process"}:
            return ToolResult(
                output="Invalid mode. Use local_agent, remote_agent, or in_process_teammate.",
                is_error=True,
            )

        if arguments.command is None and arguments.mode in {
            "local_agent",
            "in_process_teammate",
            "in_process",
        }:
            runtime = context.metadata.get("subagent_runtime")
            if runtime is not None and hasattr(runtime, "spawn"):
                try:
                    record = await runtime.spawn(
                        description=arguments.description,
                        prompt=arguments.prompt,
                        subagent_type=arguments.subagent_type,
                        name=arguments.name,
                        model=arguments.model,
                        max_turns=arguments.max_turns,
                        parent_id=str(context.metadata.get("subagent_id") or "lead"),
                        parent_depth=int(context.metadata.get("subagent_depth") or 0),
                        parent_inbox=context.metadata.get("subagent_inbox"),
                        parent_cancellation_token=context.cancellation_token,
                        inherit_context=arguments.inherit_context,
                        inherited_history=context.metadata.get("parent_completed_messages"),
                        output_schema=arguments.output_schema,
                        preset=arguments.preset,
                        external_cli=arguments.external_cli,
                    )
                except ValueError as exc:
                    return ToolResult(output=str(exc), is_error=True)
                return ToolResult(
                    output=json.dumps(
                        {
                            "agent_id": record.agent_id,
                            "name": record.name,
                            "status": record.status,
                            "parent_id": record.parent_id,
                            "depth": record.depth,
                            "model": record.model,
                            "inherit_context": bool(record.metadata.get("inherit_context")),
                            "message": (
                                f"Spawned async subagent {record.agent_id}. "
                                "Use wait_agent to collect results or send_message to steer it."
                            ),
                        },
                        ensure_ascii=False,
                    )
                )

        # Look up agent definition if subagent_type is specified
        agent_def = None
        if arguments.subagent_type:
            agent_def = get_agent_definition(arguments.subagent_type)

        # Resolve team and agent name for the swarm backend
        team = arguments.team or "default"
        agent_name = arguments.subagent_type or "agent"

        # Use subprocess backend so spawned agents are registered in
        # BackgroundTaskManager and are pollable by the task tools.
        # in_process tasks return asyncio-internal IDs that task tools
        # cannot query, and subprocess is always available on all platforms.
        registry = get_backend_registry()
        executor = registry.get_executor("subprocess")

        config = TeammateSpawnConfig(
            name=agent_name,
            team=team,
            prompt=arguments.prompt,
            cwd=str(context.cwd),
            parent_session_id="main",
            model=arguments.model or (agent_def.model if agent_def else None),
            command=arguments.command,
            system_prompt=agent_def.system_prompt if agent_def else None,
            permissions=agent_def.permissions if agent_def else [],
            task_type=arguments.mode,
        )

        try:
            result = await executor.spawn(config)
        except Exception as exc:
            logger.error("Failed to spawn agent: %s", exc)
            return ToolResult(output=str(exc), is_error=True)

        if not result.success:
            return ToolResult(output=result.error or "Failed to spawn agent", is_error=True)

        if arguments.team:
            registry = get_team_registry()
            try:
                registry.add_agent(arguments.team, result.task_id)
            except ValueError:
                registry.create_team(arguments.team)
                registry.add_agent(arguments.team, result.task_id)

        if context.hook_executor is not None:
            manager = get_task_manager()
            unregister = None

            async def _emit_subagent_stop(task_record) -> None:
                nonlocal unregister
                if task_record.id != result.task_id:
                    return
                if unregister is not None:
                    unregister()
                    unregister = None
                await context.hook_executor.execute(
                    HookEvent.SUBAGENT_STOP,
                    {
                        "event": HookEvent.SUBAGENT_STOP.value,
                        "agent_id": result.agent_id,
                        "task_id": result.task_id,
                        "backend_type": result.backend_type,
                        "status": task_record.status,
                        "return_code": task_record.return_code,
                        "description": arguments.description,
                        "subagent_type": arguments.subagent_type or "agent",
                        "team": team,
                        "mode": arguments.mode,
                    },
                )

            unregister = manager.register_completion_listener(_emit_subagent_stop)
            task_record = manager.get_task(result.task_id)
            if task_record is not None and task_record.status in {"completed", "failed", "killed"}:
                await _emit_subagent_stop(task_record)

        return ToolResult(
            output=(
                f"Spawned agent {result.agent_id} "
                f"(task_id={result.task_id}, backend={result.backend_type})"
            ),
            metadata={
                "agent_id": result.agent_id,
                "task_id": result.task_id,
                "backend_type": result.backend_type,
                "description": arguments.description,
            },
        )
