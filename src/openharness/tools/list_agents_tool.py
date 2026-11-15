"""Inspect active and completed in-process subagents."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class ListAgentsToolInput(BaseModel):
    """Arguments for listing subagents."""

    only_direct_children: bool = Field(
        default=False,
        description="When true, only list subagents directly spawned by the caller",
    )


class ListAgentsTool(BaseTool):
    """List tracked asynchronous subagents and their live status/usage."""

    name = "list_agents"
    display_name = "List Agents"
    default_start_message = "正在查看子智能体状态..."
    description = "List active, completed, failed, and interrupted subagents in this session."
    input_model = ListAgentsToolInput

    def is_read_only(self, arguments: ListAgentsToolInput) -> bool:
        del arguments
        return True

    def is_concurrency_safe(self, arguments: ListAgentsToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: ListAgentsToolInput, context: ToolExecutionContext) -> ToolResult:
        runtime = context.metadata.get("subagent_runtime")
        if runtime is None or not hasattr(runtime, "list_agents"):
            return ToolResult(output=json.dumps({"agents": [], "usage": {}}, ensure_ascii=False))

        caller_id = str(context.metadata.get("subagent_id") or "lead")
        parent_filter = caller_id if arguments.only_direct_children else None
        agents = runtime.list_agents(parent_id=parent_filter)
        usage = runtime.total_usage() if hasattr(runtime, "total_usage") else {}
        return ToolResult(
            output=json.dumps({"agents": agents, "usage": usage}, ensure_ascii=False)
        )
