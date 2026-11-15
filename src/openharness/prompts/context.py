"""Higher-level system prompt assembly."""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Iterable

from openharness.config.paths import (
    get_project_active_repo_context_path,
    get_project_issue_file,
    get_project_pr_comments_file,
)
from openharness.config.settings import Settings
from openharness.coordinator.coordinator_mode import get_coordinator_system_prompt, is_coordinator_mode
from openharness.memory import load_memory_prompt
from openharness.memory.relevance import format_relevant_memories, select_relevant_memories
from openharness.memory.usage import mark_memory_used
from openharness.personalization.rules import load_local_rules
from openharness.prompts.claudemd import load_claude_md_prompt
from openharness.prompts.system_prompt import build_system_prompt
from openharness.skills.loader import load_skill_registry

logger = logging.getLogger("PromptContext")

def _build_delegation_section() -> str:
    """Build a concise section describing when and how to delegate work to subagents."""
    return "\n".join(
        [
            "# Delegation And Subagents",
            "",
            "OpenHarness supports non-blocking subagents via `agent` plus structured tracking via `task_board`.",
            "Every `agent(...)` call returns immediately after spawning; completion and failure notifications arrive in your inbox automatically.",
            "",
            "When to delegate:",
            "- Parallel independent workstreams: spawn multiple `agent` calls in the same turn when files, research tracks, or verification checks can run concurrently, then end your turn without polling.",
            "- Context isolation (`inherit_context=False`, default): keep noisy search output, broad repository exploration, or verbose test logs out of your main context window.",
            "- Context-inherited follow-up (`inherit_context=True`): spawn a forked child that sees completed turns so far for independent verification, code review, or continuing a multi-step investigation with fresh focus.",
            "- Explicit multi-agent workflows: when the user asks for parallel investigation, background execution, or task decomposition.",
            "",
            "When NOT to delegate:",
            "- Do not spawn a subagent for simple direct answers, single-file reads, or quick 1–2 tool lookups that take less effort than delegating.",
            "- Do not spawn duplicate subagents for the same slice, and do not poll `wait_agent` in a loop after spawning background workers unless you genuinely need results before continuing.",
            "",
            "Lifecycle tools:",
            "- `agent(description=..., prompt=..., subagent_type=..., inherit_context=False)`: spawn an async child agent.",
            "- `run_code(code=...)`: run a bounded Python script that batches multiple `await tools.<name>(**kwargs)` / `await gather(...)` calls in a single turn, filtering or aggregating intermediate outputs before returning only the distilled summary.",
            "- `task_board(...)`: break multi-step work into dependency-aware DAG tasks (`batch_create`, `create`, `claim`, `update`, `list`).",
            "- `send_message(agent_id=..., message=...)`: steer or send follow-up instructions to a child agent.",
            "- `list_agents()` / `wait_agent(agent_id=..., timeout=...)` / `interrupt_agent(agent_id=...)`: inspect, explicitly await if needed, or stop running workers.",
        ]
    )


import re

def compact_skill_description(description: str, max_chars: int = 180) -> str:
    """Compact a skill description for system prompt display without modifying source files.

    Extracts the core trigger and purpose sentence(s), removing internal developer
    constraints, CLI options, and excessive prose while preserving semantic trigger accuracy.
    """
    if not description:
        return ""

    clean = " ".join(description.strip().split())
    if len(clean) <= max_chars:
        return clean

    # Check for "Use when asked to..." clause
    use_when_match = re.search(r"(Use when asked to\s+[^。\n]+)", clean, re.IGNORECASE)
    use_when_clause = use_when_match.group(1).strip() if use_when_match else ""

    # Split by Chinese/English sentence boundaries
    sentences = re.split(r"(?<=[。！？\.\!\?])\s+", clean)

    first_meaningful = ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        # Skip internal dev/script validation noise
        if re.search(r"\b\d+\s*项全自动脚本校验|\bKPI\b|--\w+|API key|references/", s):
            continue
        first_meaningful = s
        break

    if not first_meaningful and sentences:
        first_meaningful = sentences[0]

    if use_when_clause and use_when_clause not in first_meaningful:
        combined = f"{first_meaningful} {use_when_clause}"
        if len(combined) <= max_chars:
            return combined

    if len(first_meaningful) <= max_chars:
        return first_meaningful

    # Truncate safely at word/punctuation boundary
    truncated = first_meaningful[:max_chars]
    last_punct = max(truncated.rfind(" "), truncated.rfind("，"), truncated.rfind("。"), truncated.rfind(","))
    if last_punct > max_chars // 2:
        return truncated[:last_punct].rstrip(" ,;，。") + "..."
    return truncated.rstrip() + "..."


def _build_skills_section(
    cwd: str | Path,
    *,
    extra_skill_dirs: Iterable[str | Path] | None = None,
    extra_plugin_roots: Iterable[str | Path] | None = None,
    allowed_user_skill_ids: Iterable[str] | None = None,
    settings: Settings | None = None,
    include_default_user_skills: bool = True,
    include_default_plugin_roots: bool = True,
) -> str | None:
    """Build a system prompt section listing available skills."""
    registry = load_skill_registry(
        cwd,
        extra_skill_dirs=extra_skill_dirs,
        extra_plugin_roots=extra_plugin_roots,
        allowed_user_skill_ids=allowed_user_skill_ids,
        settings=settings,
        include_default_user_skills=include_default_user_skills,
        include_default_plugin_roots=include_default_plugin_roots,
    )
    skills = [skill for skill in registry.list_skills() if not skill.disable_model_invocation]
    if not skills:
        return None
    lines = [
        "# Available Skills",
        "",
        "The following skills are available via the `skill` tool. "
        "When a user's request matches a skill, invoke it with `skill(name=\"<skill_name>\")` "
        "to load detailed instructions before proceeding. "
        "User-invocable skills can also be run directly by the user as `/<skill-name>`.",
        "",
    ]
    for skill in skills:
        command_name = skill.command_name or skill.name
        display = f" ({skill.display_name})" if skill.display_name else ""
        lines.append(f"- **{command_name}**{display}: {compact_skill_description(skill.description)}")
    return "\n".join(lines)


def _build_extra_skills_section(
    cwd: str | Path,
    *,
    extra_skill_dirs: Iterable[str | Path] | None = None,
    extra_plugin_roots: Iterable[str | Path] | None = None,
    allowed_user_skill_ids: Iterable[str] | None = None,
    settings: Settings | None = None,
    include_default_user_skills: bool = True,
    include_default_plugin_roots: bool = True,
) -> str | None:
    """Build a dynamic prompt section for SaaS user and plugin skills."""
    skills = [
        skill
        for skill in load_skill_registry(
            cwd,
            extra_skill_dirs=extra_skill_dirs,
            extra_plugin_roots=extra_plugin_roots,
            allowed_user_skill_ids=allowed_user_skill_ids,
            settings=settings,
            include_default_user_skills=include_default_user_skills,
            include_default_plugin_roots=include_default_plugin_roots,
        ).list_skills()
        if not skill.disable_model_invocation and skill.source in {"user", "plugin"}
    ]
    if not skills:
        return None
    lines = [
        "# User And Plugin Skills",
        "",
        "The current user has added these private skills or enabled plugins that provide skills. "
        "They are available via the `skill` tool. "
        "When the request matches one of them, invoke `skill(name=\"<skill_name>\")` before proceeding.",
        "",
    ]
    for skill in skills:
        command_name = skill.command_name or skill.name
        display = f" ({skill.display_name})" if skill.display_name else ""
        lines.append(f"- **{command_name}**{display}: {compact_skill_description(skill.description)}")
    return "\n".join(lines)


@functools.lru_cache(maxsize=8)
def _build_static_prompt_skeleton(
    base_dir: str,
    include_default_user_skills: bool = True,
    include_default_plugin_roots: bool = True,
) -> list[str]:
    """Build and cache the static skeleton of the system prompt."""
    logger.info("--- [Cache MISS] Building system prompt skeleton for: %s ---", base_dir)
    sections: list[str] = []
    sections.append(build_system_prompt(cwd=base_dir))

    sections.append(_build_delegation_section())

    skills_section = _build_skills_section(
        base_dir,
        include_default_user_skills=include_default_user_skills,
        include_default_plugin_roots=include_default_plugin_roots,
    )
    if skills_section:
        sections.append(skills_section)

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
    allowed_user_skill_ids: Iterable[str] | None = None,
    include_default_user_skills: bool = True,
    include_default_plugin_roots: bool = True,
    include_project_memory: bool = True,
) -> str:
    """Build the runtime system prompt with project instructions and memory."""
    if is_coordinator_mode():
        sections = [get_coordinator_system_prompt()]
    else:
        cwd_path = Path(cwd).resolve()
        cache_key = str(cwd_path)

        parts = cwd_path.parts
        if "sandbox-data" in parts:
            idx = parts.index("sandbox-data")
            if len(parts) > idx + 1:
                cache_key = str(Path(*parts[: idx + 2]))
        elif "temp_workspaces" in parts:
            idx = parts.index("temp_workspaces")
            cache_key = str(Path(*parts[: idx + 1]))

        sections = list(
            _build_static_prompt_skeleton(
                cache_key,
                include_default_user_skills,
                include_default_plugin_roots,
            )
        )
        logger.info("--- [Prompt Skeleton] Using skeleton for key: %s ---", cache_key)

    extra_skills_section = _build_extra_skills_section(
        cwd,
        extra_skill_dirs=extra_skill_dirs,
        extra_plugin_roots=extra_plugin_roots,
        allowed_user_skill_ids=allowed_user_skill_ids,
        settings=settings,
        include_default_user_skills=include_default_user_skills,
        include_default_plugin_roots=include_default_plugin_roots,
    )
    if extra_skills_section:
        sections.append(extra_skills_section)

    from openharness.prompts.environment import get_environment_info

    env_info = get_environment_info(cwd, is_sandbox=settings.sandbox.enabled)
    sections.append(
        f"# Environment Context\n"
        f"- Current Date (UTC): {env_info.date}\n"
        f"- User Default Timezone: Asia/Shanghai\n"
        f"- Working Directory: {env_info.cwd}\n"
        f"- OS: {env_info.os_name} {env_info.os_version}\n"
        f"- Sudo: {env_info.extra.get('sudo', 'Not available')}\n"
        f"- Search Policy: Today is {env_info.date}. ALWAYS prioritize records from {env_info.date[:4]} or {int(env_info.date[:4]) - 1} when searching to ensure data recency."
    )

    if settings.fast_mode:
        sections.append(
            "# Session Mode\nFast mode is enabled. Prefer concise replies, minimal tool use, and quicker progress over exhaustive exploration."
        )

 

    claude_md = load_claude_md_prompt(cwd)
    if claude_md:
        sections.append(claude_md)

    for title, path in (
        ("Issue Context", get_project_issue_file(cwd)),
        ("Pull Request Comments", get_project_pr_comments_file(cwd)),
        ("Active Repo Context", get_project_active_repo_context_path(cwd)),
    ):
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            if content:
                sections.append(f"# {title}\n\n```md\n{content[:12000]}\n```")

    if include_project_memory and settings.memory.enabled:
        memory_section = load_memory_prompt(
            cwd,
            max_entrypoint_lines=settings.memory.max_entrypoint_lines,
            max_entrypoint_bytes=settings.memory.max_entrypoint_bytes,
        )
        if memory_section:
            sections.append(memory_section)

        if latest_user_prompt:
            relevant = select_relevant_memories(
                latest_user_prompt,
                cwd,
                max_results=settings.memory.max_files,
            )
            if relevant:
                try:
                    headers = [item.header for item in relevant]
                    mark_memory_used(cwd, headers, memory_dir=headers[0].path.parent)
                except OSError:
                    pass
                sections.append(format_relevant_memories(relevant))

    return "\n\n".join(section for section in sections if section.strip())
