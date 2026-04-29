"""Tool for installing new skills from the skill marketplace with SaaS persistence."""

from __future__ import annotations
import shutil
import os
from pathlib import Path
from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class SkillInstallInput(BaseModel):
    """Arguments for skill installation."""

    name: str = Field(description="Name of the skill to install")
    source_path: str | None = Field(None, description="Optional source path if known, otherwise look in marketplace")


class SkillInstallTool(BaseTool):
    """Install a skill into the user's persistent shared assets."""

    name = "install_skill"
    description = "Install a new skill to your persistent account so it can be used across all tasks."
    input_model = SkillInstallInput

    def is_read_only(self, arguments: SkillInstallInput) -> bool:
        return False

    async def execute(self, arguments: SkillInstallInput, context: ToolExecutionContext) -> ToolResult:
        user_id = context.metadata.get("user_id")
        data_root = context.metadata.get("sandbox_data_root")
        viking = context.metadata.get("viking")
        
        if not user_id or not data_root:
            return ToolResult(output="User context missing. Skill installation aborted.", is_error=True)
            
        # 确定用户全局共享技能区 (Host 路径) - 优先使用社区标准路径 .agents/skills
        user_skills_root = Path(data_root) / str(user_id) / "shared_assets" / "user-home" / ".agents" / "skills" / arguments.name
        user_skills_root.mkdir(parents=True, exist_ok=True)
        
        # 查找源
        source_dir = None
        if arguments.source_path:
            source_dir = Path(arguments.source_path)
        else:
            # 默认市场路径: OpenHarness/skills/bundled/content/
            # 考虑到可能包含 Python 脚本，我们支持寻找同名文件夹或单个 .md 文件
            bundled_root = Path(__file__).parent.parent / "skills" / "bundled"
            
            # 路径 1: 单个逻辑技能 .md
            potential_md = bundled_root / "content" / f"{arguments.name}.md"
            # 路径 2: 完整技能包目录 (未来扩展用)
            potential_dir = bundled_root / "packages" / arguments.name
            
            if potential_md.exists():
                source_dir = potential_md
            elif potential_dir.exists():
                source_dir = potential_dir
                
        if source_dir is None or not source_dir.exists():
            return ToolResult(output=f"Skill source for '{arguments.name}' not found.", is_error=True)
            
        try:
            # 1. 物理安装 (到宿主机挂载点)
            if source_dir.is_dir():
                shutil.copytree(source_dir, user_skills_root, dirs_exist_ok=True)
            else:
                # 如果只是单个 MD，存入该技能文件夹并命名为 SKILL.md
                shutil.copy2(source_dir, user_skills_root / "SKILL.md")
            
            # 2. 语义存储 (到 OpenViking 记忆系统)
            if viking and viking.client:
                # 获取摘要：这里简单读前 200 字作为 Memory
                skill_content = ""
                md_path = user_skills_root / "SKILL.md"
                if md_path.exists():
                    skill_content = md_path.read_text(encoding="utf-8")
                
                try:
                    # 存入用户专属能力库
                    viking.client.add_memory(
                        content=f"Installed Skill '{arguments.name}': {skill_content[:300]}...",
                        target_uri=f"viking://user/{user_id}/memories/skills/{arguments.name}",
                        tags=["skill", "installed", arguments.name]
                    )
                except Exception as ve:
                    # Viking 失败不影响物理安装
                    pass

            return ToolResult(output=(
                f"Successfully installed skill '{arguments.name}' to your persistent profile.\n"
                f"- Path in sandbox: ~/.agents/skills/{arguments.name}/\n"
                f"- Status: Active and persistent across tasks.\n"
                f"Tip: Use the 'skill' tool to load instructions."
            ))
        except Exception as e:
            return ToolResult(output=f"Failed to install skill: {e}", is_error=True)
