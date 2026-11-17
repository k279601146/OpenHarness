"""Tool for searching available tools."""

from __future__ import annotations

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class ToolSearchToolInput(BaseModel):
    """Arguments for tool search."""

    query: str = Field(description="Substring to search in tool names and descriptions")


class ToolSearchTool(BaseTool):
    """Search tool registry contents."""

    name = "tool_search"
    description = (
        "Search and activate deferred internal tools (e.g. ask_user_form, workflow, ralph, task_board, "
        "apply_patch, cron_create, generate_image). Matched tools are activated for subsequent turns. "
        "Strictly DO NOT use this for searching specialized domain expertise (e.g. PPT, SEO, Design); "
        "always use the `find-skills` skill for those instead."
    )
    input_model = ToolSearchToolInput

    def is_read_only(self, arguments: ToolSearchToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: ToolSearchToolInput, context: ToolExecutionContext) -> ToolResult:
        registry = context.metadata.get("tool_registry") if hasattr(context, "metadata") else None
        if registry is None:
            return ToolResult(output="Tool registry context not available", is_error=True)
        query = arguments.query.strip().lower()
        tools = registry.list_tools()
        matches = [
            tool for tool in tools
            if query in tool.name.lower() or query in tool.description.lower()
        ]
        if not matches and " " in query:
            terms = [t for t in query.split() if t]
            matches = [
                tool for tool in tools
                if any(term in tool.name.lower() or term in tool.description.lower() for term in terms)
            ]
        if not matches:
            return ToolResult(output="(no matches)")
        activated = [tool.name for tool in matches[:12]]
        lines = [f"{tool.name}: {tool.description}" for tool in matches]
        lines.append(f"\n[Activated tool schemas for next step: {', '.join(activated)}]")
        return ToolResult(
            output="\n".join(lines),
            metadata={"activated_tools": activated},
        )
