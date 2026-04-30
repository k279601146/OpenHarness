"""Tool for spawning local agent tasks."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from openharness.coordinator.agent_definitions import get_agent_definition
from openharness.coordinator.coordinator_mode import get_team_registry
from openharness.swarm.registry import get_backend_registry
from openharness.swarm.types import TeammateSpawnConfig
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

logger = logging.getLogger(__name__)


class AgentToolInput(BaseModel):
    """Arguments for local agent spawning."""

    description: str = Field(description="Short description of the delegated work")
    prompt: str = Field(description="Full prompt for the local agent")
    subagent_type: str | None = Field(
        default=None,
        description="Agent type for definition lookup (e.g. 'researcher', 'strategist', 'executor', 'reviewer')",
    )
    model: str | None = Field(default=None)
    command: str | None = Field(default=None, description="Override spawn command")
    team: str | None = Field(default=None, description="Optional team to attach the agent to")
    mode: str = Field(
        default="local_agent",
        description="Agent mode: local_agent, remote_agent, or in_process_teammate",
    )


class AgentTool(BaseTool):
    """Spawn a local agent subprocess and wait for its completion."""

    name = "agent"
    description = "Spawn a local agent task and WAIT for it to finish. The tool will block until the subagent completes, and then return the subagent's final output directly."
    input_model = AgentToolInput

    async def execute(self, arguments: AgentToolInput, context: ToolExecutionContext) -> ToolResult:
        import os
        from openharness.engine.query_engine import QueryEngine
        from openharness.api.client import AnthropicApiClient
        from openharness.api.openai_client import OpenAICompatibleClient
        from openharness.tools import create_mvp_safe_tool_registry
        from openharness.permissions.checker import PermissionChecker
        from openharness.config.settings import Settings
        from openharness.permissions.modes import PermissionMode

        logger.info(f"[SaaS AgentTool] Spawning in-process subagent natively: {arguments.subagent_type}")
        
        agent_def = None
        if arguments.subagent_type:
            agent_def = get_agent_definition(arguments.subagent_type)

        agent_name = arguments.subagent_type or "agent"

        # Initialize API Client for the subagent
        api_key = os.getenv("ARK_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3"
        
        settings = Settings()
        
        # Handle "inherit" model placeholder from agent_definitions
        def_model = agent_def.model if agent_def else None
        if def_model == "inherit":
            def_model = None
            
        settings.model = arguments.model or def_model or os.getenv("DEFAULT_MODEL", "gemini-2.5-pro")
        if settings.model == "inherit":
            settings.model = os.getenv("DEFAULT_MODEL", "gemini-2.5-pro")
            
        settings.permission.mode = PermissionMode.FULL_AUTO

        if "claude" in settings.model.lower():
            api_client = AnthropicApiClient(api_key=api_key, base_url=base_url)
        else:
            api_client = OpenAICompatibleClient(api_key=api_key, base_url=base_url)

        tool_registry = create_mvp_safe_tool_registry()

        # Build prompt with runtime environment (date, OS, memory, etc.)
        from openharness.prompts.context import build_runtime_system_prompt
        base_prompt = agent_def.system_prompt if agent_def else "You are a helpful sub-agent. Please complete the requested task."
        settings.system_prompt = base_prompt
        
        system_prompt = build_runtime_system_prompt(settings, cwd=str(context.cwd))

        engine = QueryEngine(
            api_client=api_client,
            tool_registry=tool_registry,
            permission_checker=PermissionChecker(settings.permission),
            cwd=str(context.cwd),
            model=settings.model,
            system_prompt=system_prompt,
            tool_metadata=getattr(context, 'tool_metadata', {})
        )

        logger.info(f"[SaaS AgentTool] Engine configured. Calling model for task...")
        
        final_responses = []
        try:
            # Accumulate stream deltas explicitly to catch <think> blocks and all raw text
            async for event in engine.submit_message(arguments.prompt):
                event_type = getattr(event, "type", type(event).__name__.lower())
                if "text_delta" in event_type or "reasoning_delta" in event_type:
                    if hasattr(event, "text") and event.text:
                        final_responses.append(event.text)
                        
            # Backup collection from messages if stream delta failed to trigger
            if not final_responses and engine.messages:
                for msg in engine.messages:
                    if msg.role == "assistant":
                        for block in msg.content:
                            if hasattr(block, "text") and block.text.strip():
                                final_responses.append(block.text)

        except Exception as e:
            logger.error(f"[SaaS AgentTool] Native execution failed: {e}", exc_info=True)
            return ToolResult(output=f"Error running subagent natively: {e}", is_error=True)

        if not final_responses:
            output_str = "(Subagent did not generate any text response)"
        else:
            output_str = "\n".join(final_responses)
            
        logger.info(f"[SaaS AgentTool] Subagent completed successfully.")
        
        return ToolResult(
            output=(
                f"Agent {agent_name} finished.\n"
                f"--- Subagent Output ---\n{output_str}"
            )
        )
