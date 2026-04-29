"""Tool for reading skill contents."""

import asyncio
import logging
import os
from pydantic import BaseModel, Field

from openharness.skills import load_skill_registry
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

logger = logging.getLogger(__name__)


class SkillToolInput(BaseModel):
    """Arguments for skill lookup."""

    name: str = Field(description="Skill name")


class SkillTool(BaseTool):
    """Return the content of a loaded skill."""

    name = "skill"
    description = "Read a bundled, user, or plugin skill by name."
    input_model = SkillToolInput

    def is_read_only(self, arguments: SkillToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: SkillToolInput, context: ToolExecutionContext) -> ToolResult:
        user_id = context.metadata.get("user_id")
        data_root = context.metadata.get("sandbox_data_root")
        
        extra_dirs = list(context.metadata.get("extra_skill_dirs") or [])
        if user_id and data_root:
            from openharness.skills.loader import get_saas_skill_dirs
            for d in get_saas_skill_dirs(data_root, user_id):
                if str(d) not in [str(ex) for ex in extra_dirs]:
                    extra_dirs.append(d)

        # 彻底的路径脱敏：不再使用 session._to_container_path，统一使用正斜杠字符串
        def normalize_func(p):
            return str(p).replace('\\', '/') if p else p

        registry = load_skill_registry(
            context.cwd,
            extra_skill_dirs=extra_dirs,
            extra_plugin_roots=context.metadata.get("extra_plugin_roots"),
            normalize_path_func=normalize_func,
        )

        skill = registry.get(arguments.name) or registry.get(arguments.name.lower()) or registry.get(arguments.name.title())
        
        # Fallback: 如果宿主机文件系统找不到技能，尝试通过容器内部读取
        # 针对 E2B 的物理文件扫描
        from openharness.sandbox.session import get_sandbox_session
        session = get_sandbox_session()
        if skill is None and session and session.is_running:
            skill_content = await self._read_skill_from_container(session, arguments.name)
            if skill_content:
                from openharness.skills.types import SkillDefinition
                from openharness.skills.loader import _parse_skill_markdown
                name, description = _parse_skill_markdown(arguments.name, skill_content)
                skill = SkillDefinition(
                    name=name,
                    description=description,
                    content=skill_content,
                    source="container",
                    path=f"/home/user/.agents/skills/{arguments.name}/SKILL.md",
                )
                logger.info(f"Skill '{arguments.name}' loaded from container fallback")
        
        if skill is None:
            return ToolResult(
                output=f"Skill not found: {arguments.name}. If this is a specialized domain expertise (e.g. PPT, SEO, Design), you MUST use `skill(name='find-skills')` to discover and install it first.", 
                is_error=True
            )

        # [Suggestion 3] 语义同步：使用即注册
        # 当 Agent 加载一个技能时，自动将其元数据异步同步到 OpenViking，确保后续能被语义检索发现。
        viking = context.metadata.get("viking")
        if viking and hasattr(viking, "client"):
            try:
                asyncio.create_task(viking.client.add_memory(
                    content=f"Activated Skill '{arguments.name}': {skill.description}",
                    target_uri=f"viking://agent/memories/marketplace_cache/{arguments.name}",
                    tags=["skill", "active", skill.skill_type],
                    metadata={
                        "skill_name": skill.name,
                        "source": skill.source,
                        "type": skill.skill_type
                    }
                ))
            except Exception:
                pass # 同步失败不影响主逻辑

        full_output = skill.content + (
            "\n\n---\n"
            "[SYSTEM_DIRECTIVE]\n"
            "SKILL_STATUS: ACTIVE\n"
            "PROTOCOL: ATOMIC_EXECUTION\n"
            f"注意：你已成功加载 '{arguments.name}' 技能。请根据技能文档中的执行步骤立即开始任务。\n"
            "禁止解释为什么要用这个技能，禁止询问用户是否可以开始。立即调用后续工具（如 web_search, bash 等）执行 Step 1。"
        )

        return ToolResult(output=full_output)

    async def _read_skill_from_container(self, session, skill_name: str) -> str | None:
        """从沙箱容器内搜索并读取 SKILL.md 文件。
        
        搜索顺序：
        1. ~/.agents/skills/{name}/SKILL.md (社区标准目录)
        2. ~/.skills/{name}/SKILL.md (备用目录)
        """
        search_paths = [
            f"/home/user/.agents/skills/{skill_name}/SKILL.md",
            f"/home/user/skills/{skill_name}/SKILL.md",
        ]
        
        for container_path in search_paths:
            try:
                content = await session.read_file(container_path)
                if isinstance(content, bytes):
                    content = content.decode("utf-8")
                if content.strip():
                    return content.strip()
            except Exception as e:
                logger.debug(f"Failed to read skill from e2b at {container_path}: {e}")
        
        return None
