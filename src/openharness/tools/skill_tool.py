"""Tool for reading skill contents."""

from __future__ import annotations

from pydantic import BaseModel, Field

from openharness.skills import get_cached_skill_registry, load_skill_registry
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.sandbox_workspace import (
    ensure_skill_installed_in_sandbox,
    preinstalled_bundled_skill_dir,
    uses_e2b_task_workspace,
)


class SkillToolInput(BaseModel):
    """Arguments for skill lookup."""

    name: str = Field(description="Skill name")


def _format_skill_output(
    skill_name: str,
    instructions: str,
    *,
    resource_lines: list[str] | None = None,
) -> str:
    """Wrap loaded skill instructions and base directory metadata in a canonical envelope."""
    body = (instructions or "").strip()
    resources_block = ""
    if resource_lines:
        joined = "\n".join(line for line in resource_lines if line)
        resources_block = f"<skill_resources>\n{joined}\n</skill_resources>\n\n"
    return (
        f'<skill_content name="{skill_name}">\n'
        f"{resources_block}"
        "<skill_instructions>\n"
        f"{body}\n"
        "</skill_instructions>\n"
        "</skill_content>"
    )


def _record_invoked_skill_metadata(context: ToolExecutionContext, skill_name: str) -> None:
    if not isinstance(context.metadata, dict):
        return
    normalized = (skill_name or "").strip()
    if not normalized:
        return
    bucket = context.metadata.setdefault("invoked_skills", [])
    if isinstance(bucket, list) and normalized not in bucket:
        bucket.append(normalized)


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
        registry = get_cached_skill_registry(
            context.cwd,
            extra_skill_dirs=context.metadata.get("extra_skill_dirs"),
            extra_plugin_roots=context.metadata.get("extra_plugin_roots"),
            allowed_user_skill_ids=context.metadata.get("allowed_user_skill_ids"),
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
        canonical_name = str(getattr(skill, "command_name", None) or getattr(skill, "name", None) or arguments.name)
        if skill.base_dir:
            if uses_e2b_task_workspace(context):
                sandbox_skill_dir = preinstalled_bundled_skill_dir(context, skill)
                if sandbox_skill_dir is not None:
                    _record_invoked_skill_metadata(context, canonical_name)
                    if context.progress_callback is not None:
                        await context.progress_callback(
                            {
                                "phase": "skill_ready",
                                "status": "success",
                                "message": f"预置技能 {skill.name} 已可用。",
                                "path": sandbox_skill_dir,
                                "workspace": "e2b",
                                "metadata": {"skill": skill.name, "preinstalled": True},
                            }
                        )
                    return ToolResult(
                        output=_format_skill_output(
                            canonical_name,
                            skill.content,
                            resource_lines=[
                                f"Sandbox directory for this skill: {sandbox_skill_dir}",
                                "Resolve relative paths mentioned by this skill against this sandbox directory before using them. "
                                "Load referenced resources only as needed. Do not use host-only bundled skill paths.",
                            ],
                        ),
                        metadata={
                            "workspace": "e2b",
                            "path": sandbox_skill_dir,
                            "skill": skill.name,
                            "preinstalled": True,
                        },
                    )
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
                _record_invoked_skill_metadata(context, canonical_name)
                return ToolResult(
                    output=_format_skill_output(
                        canonical_name,
                        skill.content,
                        resource_lines=[
                            f"Sandbox directory for this skill: {sandbox_skill_dir}",
                            "Resolve relative paths mentioned by this skill against this sandbox directory before using them. "
                            "Load referenced resources only as needed. Do not use host-only bundled skill paths.",
                        ],
                    ),
                    metadata={"workspace": "e2b", "path": sandbox_skill_dir, "skill": skill.name},
                )
            _record_invoked_skill_metadata(context, canonical_name)
            return ToolResult(
                output=_format_skill_output(
                    canonical_name,
                    skill.content,
                    resource_lines=[
                        f"Base directory for this skill: {skill.base_dir}",
                        "Resolve relative paths mentioned by this skill against this base directory before using them. "
                        "Load referenced resources only as needed.",
                    ],
                )
            )
        _record_invoked_skill_metadata(context, canonical_name)
        return ToolResult(output=_format_skill_output(canonical_name, skill.content))
