"""Higher-level system prompt assembly."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Iterable

from openharness.config.paths import (
    get_project_active_repo_context_path,
    get_project_issue_file,
    get_project_pr_comments_file,
)
from openharness.config.settings import Settings
from openharness.coordinator.coordinator_mode import get_coordinator_system_prompt, is_coordinator_mode
from openharness.memory import find_relevant_memories, load_memory_prompt
from openharness.personalization.rules import load_local_rules
from openharness.prompts.claudemd import load_claude_md_prompt
from openharness.prompts.system_prompt import build_system_prompt
from openharness.skills.loader import load_skill_registry
import logging

logger = logging.getLogger("PromptContext")


def _build_skills_section(
    cwd: str | Path,
    *,
    extra_skill_dirs: Iterable[str | Path] | None = None,
    extra_plugin_roots: Iterable[str | Path] | None = None,
    settings: Settings | None = None,
) -> str | None:
    """Build a system prompt section listing available skills."""
    registry = load_skill_registry(
        cwd,
        extra_skill_dirs=extra_skill_dirs,
        extra_plugin_roots=extra_plugin_roots,
        settings=settings,
    )
    skills = sorted(registry.list_skills(), key=lambda s: s.name)
    if not skills:
        return None
    lines = [
        "# Available Skills",
        "",
        "The following skills are available via the `skill` tool. "
        "When a user's request matches a skill, invoke it with `skill(name=\"<skill_name>\")` "
        "to load detailed instructions before proceeding.",
        "",
    ]
    for skill in skills:
        # 只保留核心名称和一句话概括，减少 Token 浪费
        desc = skill.description.split('。')[0] if '。' in skill.description else skill.description
        lines.append(f"- **{skill.name}**: {desc[:120]}")
    return "\n".join(lines)


def _build_delegation_section() -> str:
    """Build a concise section describing delegation and worker usage."""
    return "\n".join(
        [
            "# Delegation And Subagents",
            "",
            "OpenHarness can delegate background work with the `agent` tool.",
            "Use it when the user explicitly asks for a subagent, background worker, or parallel investigation, "
            "or when the task clearly benefits from splitting off a focused worker.",
            "",
            "Default pattern:",
            '- Spawn with `agent(description=..., prompt=..., subagent_type="worker")`.',
            "- Inspect running or recorded workers with `/agents`.",
            "- Inspect one worker in detail with `/agents show TASK_ID`.",
            "- Send follow-up instructions with `send_message(task_id=..., message=...)`.",
            "- Read worker output with `task_output(task_id=...)`.",
            "",
            "Prefer a normal direct answer for simple tasks. Use subagents only when they materially help.",
        ]
    )


@functools.lru_cache(maxsize=4)
def _build_static_prompt_skeleton(base_dir: str) -> list[str]:
    """
    构建系统提示词的「静态骨架」并缓存结果。
    """
    logger.info(f"--- [Cache MISS] Building system prompt skeleton for: {base_dir} ---")
    
    sections: list[str] = []

    # 1. 核心 Persona（基于基础目录构建）
    sections.append(build_system_prompt(cwd=base_dir))

    # 2. Skills（按基础目录扫描一次，后续命中缓存）
    skills_section = _build_skills_section(base_dir)
    if skills_section:
        sections.append(skills_section)

    # 3. Delegation 说明（完全静态）
    sections.append(_build_delegation_section())

    # 4. 本地规则（进程级静态）
    local_rules = load_local_rules()
    if local_rules:
        sections.append(f"# Local Environment Rules\n\n{local_rules}")

    return sections


def build_runtime_system_prompt(
    settings: Settings,
    *,
    cwd: str | Path,
    latest_user_prompt: str | None = None,
    extra_skill_dirs: Iterable[str | Path] | None = None,
    extra_plugin_roots: Iterable[str | Path] | None = None,
) -> str:
    """Build the runtime system prompt with project instructions and memory."""
    if is_coordinator_mode():
        # Coordinator 模式走独立路径，不使用缓存骨架
        sections = [get_coordinator_system_prompt()]
    else:
        # [Optimize] 使用父级目录（通常是 temp_workspaces 或项目根）作为缓存键，
        # 避免因为 UUID 子目录不同导致缓存失效。
        cwd_path = Path(cwd).resolve()
        cache_key = str(cwd_path.parent) if "temp_workspaces" in str(cwd_path) else str(cwd_path)
        
        sections = list(_build_static_prompt_skeleton(cache_key))
        logger.info(f"--- [Prompt Skeleton] Using skeleton for key: {cache_key} ---")

    # --- 动态部分：每次请求都需要重新计算 ---

    if settings.fast_mode:
        sections.append(
            "# Session Mode\nFast mode is enabled. Prefer concise replies, minimal tool use, and quicker progress over exhaustive exploration."
        )

    sections.append(
        "# Reasoning Settings\n"
        f"- Effort: {settings.effort}\n"
        f"- Passes: {settings.passes}\n"
        "Adjust depth and iteration count to match these settings while still completing the task."
    )

    # claude.md（CWD 下的项目说明文件，空 temp_workspace 通常为空）
    claude_md = load_claude_md_prompt(cwd)
    if claude_md:
        sections.append(claude_md)

    # Issue / PR / Repo context（CWD 下的项目上下文文件）
    for title, path in (
        ("Issue Context", get_project_issue_file(cwd)),
        ("Pull Request Comments", get_project_pr_comments_file(cwd)),
        ("Active Repo Context", get_project_active_repo_context_path(cwd)),
    ):
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            if content:
                sections.append(f"# {title}\n\n```md\n{content[:12000]}\n```")

    # Memory（依赖 CWD 和当前 prompt，完全动态）
    if settings.memory.enabled:
        memory_section = load_memory_prompt(
            cwd,
            max_entrypoint_lines=settings.memory.max_entrypoint_lines,
        )
        if memory_section:
            sections.append(memory_section)

        if latest_user_prompt:
            relevant = find_relevant_memories(
                latest_user_prompt,
                cwd,
                max_results=settings.memory.max_files,
            )
            if relevant:
                lines = ["# Relevant Memories"]
                for header in relevant:
                    content = header.path.read_text(encoding="utf-8", errors="replace").strip()
                    lines.extend(
                        [
                            "",
                            f"## {header.path.name}",
                            "```md",
                            content[:8000],
                            "```",
                        ]
                    )
                sections.append("\n".join(lines))

    return "\n\n".join(section for section in sections if section.strip())
