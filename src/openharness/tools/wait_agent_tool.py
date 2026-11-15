"""Wait for asynchronous in-process subagents to produce results."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class WaitAgentToolInput(BaseModel):
    """Arguments for waiting on running subagents."""

    agent_ids: list[str] | None = Field(
        default=None,
        description="Optional subagent IDs to wait for; omit to wait on active direct child subagents",
    )
    timeout_seconds: float = Field(
        default=60.0,
        ge=0.1,
        le=600.0,
        description="Maximum seconds to wait before returning current statuses",
    )


class WaitAgentTool(BaseTool):
    """Block until one or more async subagents finish or the timeout expires."""

    name = "wait_agent"
    display_name = "Wait Agent"
    default_start_message = "正在等待异步子智能体返回结果..."
    description = (
        "Wait for asynchronous subagents to finish (event-driven wake-up without polling). "
        "Returns completed outputs and lists any subagents still running."
    )
    input_model = WaitAgentToolInput

    def is_read_only(self, arguments: WaitAgentToolInput) -> bool:
        del arguments
        return True

    def is_concurrency_safe(self, arguments: WaitAgentToolInput) -> bool:
        del arguments
        return False

    async def execute(self, arguments: WaitAgentToolInput, context: ToolExecutionContext) -> ToolResult:
        runtime = context.metadata.get("subagent_runtime")
        if runtime is None or not hasattr(runtime, "wait_for_agents"):
            return ToolResult(
                output="No in-process subagent runtime is active in this session.",
                is_error=True,
            )

        caller_id = str(context.metadata.get("subagent_id") or "lead")
        caller_inbox = context.metadata.get("subagent_inbox") or getattr(runtime, "root_inbox", None)
        result = await runtime.wait_for_agents(
            agent_ids=arguments.agent_ids,
            parent_id=None if arguments.agent_ids else caller_id,
            caller_inbox=caller_inbox,
            timeout_seconds=arguments.timeout_seconds,
            cancellation_token=context.cancellation_token,
        )
        return ToolResult(output=json.dumps(result, ensure_ascii=False))
