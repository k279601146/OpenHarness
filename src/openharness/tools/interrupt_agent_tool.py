"""Interrupt a running asynchronous subagent."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class InterruptAgentToolInput(BaseModel):
    """Arguments for interrupting a running subagent."""

    agent_id: str = Field(description="Target subagent ID returned by `agent` or `list_agents`")
    reason: str | None = Field(default=None, description="Optional reason for cancellation")


class InterruptAgentTool(BaseTool):
    """Cancel a running asynchronous subagent cleanly."""

    name = "interrupt_agent"
    display_name = "Interrupt Agent"
    default_start_message = "正在中断子智能体..."
    description = "Request cancellation of a running asynchronous subagent by agent_id."
    input_model = InterruptAgentToolInput

    def is_concurrency_safe(self, arguments: InterruptAgentToolInput) -> bool:
        del arguments
        return False

    async def execute(self, arguments: InterruptAgentToolInput, context: ToolExecutionContext) -> ToolResult:
        runtime = context.metadata.get("subagent_runtime")
        if runtime is None or not hasattr(runtime, "interrupt_agent"):
            return ToolResult(
                output="No in-process subagent runtime is active in this session.",
                is_error=True,
            )
        try:
            result = await runtime.interrupt_agent(arguments.agent_id, reason=arguments.reason)
        except KeyError as exc:
            return ToolResult(output=str(exc), is_error=True)
        return ToolResult(output=json.dumps(result, ensure_ascii=False))
