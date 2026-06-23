"""Tool for reading skill contents."""

from __future__ import annotations

from pydantic import BaseModel, Field

from openharness.skills import load_skill_registry
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.sandbox_workspace import ensure_skill_installed_in_sandbox, uses_e2b_task_workspace


class SkillToolInput(BaseModel):
    """Arguments for skill lookup."""

    name: str = Field(description="Skill name")


class SkillTool(BaseTool):
    """Return the content of a loaded skill."""

    name = "skill"
    description = "Read a bundled, user, project, or plugin skill by name."
    input_model = SkillToolInput

    def is_read_only(self, arguments: SkillToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: SkillToolInput, context: ToolExecutionContext) -> ToolResult:
        if context.progress_callback is not None:
            await context.progress_callback(
                {
                    "phase": "skill_resolve",
                    "status": "running",
                    "message": f"正在解析技能 {arguments.name}...",
                    "metadata": {"skill": arguments.name},
                }
            )
        registry = load_skill_registry(
            context.cwd,
            extra_skill_dirs=context.metadata.get("extra_skill_dirs"),
            extra_plugin_roots=context.metadata.get("extra_plugin_roots"),
            settings=context.metadata.get("settings"),
            include_default_user_skills=context.metadata.get("include_default_user_skills", True),
            include_default_plugin_roots=context.metadata.get("include_default_plugin_roots", True),
        )
        skill = registry.get(arguments.name) or registry.get(arguments.name.lower()) or registry.get(arguments.name.title())
        if skill is None:
            if context.progress_callback is not None:
                await context.progress_callback(
                    {
                        "phase": "skill_resolve",
                        "status": "error",
                        "message": f"未找到技能 {arguments.name}。",
                        "metadata": {"skill": arguments.name},
                    }
                )
            return ToolResult(output=f"Skill not found: {arguments.name}", is_error=True)
        if skill.disable_model_invocation:
            command_name = skill.command_name or skill.name
            return ToolResult(
                output=f"Skill {command_name} can only be invoked by the user as /{command_name}.",
                is_error=True,
            )
        if skill.base_dir:
            if uses_e2b_task_workspace(context):
                try:
                    sandbox_skill_dir = await ensure_skill_installed_in_sandbox(context, skill)
                except Exception as exc:
                    if context.progress_callback is not None:
                        await context.progress_callback(
                            {
                                "phase": "skill_ready",
                                "status": "error",
                                "message": f"技能 {skill.name} 同步到沙箱失败。",
                                "detail": str(exc),
                                "metadata": {"skill": skill.name},
                            }
                        )
                    return ToolResult(output=f"Failed to install skill in sandbox: {exc}", is_error=True)
                return ToolResult(
                    output=(
                        f"Sandbox directory for this skill: {sandbox_skill_dir}\n"
                        "Use files under this sandbox directory only. "
                        "Do not use host-only bundled skill paths.\n\n"
                        f"{skill.content}"
                    ),
                    metadata={"workspace": "e2b", "path": sandbox_skill_dir, "skill": skill.name},
                )
            return ToolResult(
                output=(
                    f"Base directory for this skill: {skill.base_dir}\n"
                    "Use paths under this directory for bundled skill assets and scripts.\n\n"
                    f"{skill.content}"
                )
            )
        return ToolResult(output=skill.content)
