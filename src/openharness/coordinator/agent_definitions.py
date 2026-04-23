"""Agent definition loading system for OpenHarness."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from openharness.config.paths import get_config_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Valid color names for agents (matches AgentColorName in TS).
AGENT_COLORS: frozenset[str] = frozenset(
    {
        "red",
        "green",
        "blue",
        "yellow",
        "purple",
        "orange",
        "cyan",
        "magenta",
        "white",
        "gray",
    }
)

#: Valid effort level strings (maps to EFFORT_LEVELS in TS).
EFFORT_LEVELS: tuple[str, ...] = ("low", "medium", "high")

#: Valid permission mode strings (maps to PERMISSION_MODES in TS).
PERMISSION_MODES: tuple[str, ...] = (
    "default",
    "acceptEdits",
    "bypassPermissions",
    "plan",
    "dontAsk",
)

#: Valid memory scope strings (maps to AgentMemoryScope in TS).
MEMORY_SCOPES: tuple[str, ...] = ("user", "project", "local")

#: Valid isolation mode strings.
ISOLATION_MODES: tuple[str, ...] = ("worktree", "remote")


# ---------------------------------------------------------------------------
# AgentDefinition model
# ---------------------------------------------------------------------------


class AgentDefinition(BaseModel):
    """Full agent definition with all configuration fields.

    Field mapping to TypeScript ``BaseAgentDefinition``:
    - ``name``          → ``agentType``
    - ``description``   → ``whenToUse``
    - ``system_prompt`` → ``getSystemPrompt()`` return value
    - ``tools``         → ``tools`` (None means all tools / ``['*']``)
    - ``disallowed_tools`` → ``disallowedTools``
    - ``skills``        → ``skills``
    - ``mcp_servers``   → ``mcpServers``
    - ``hooks``         → ``hooks``
    - ``color``         → ``color``
    - ``model``         → ``model``
    - ``effort``        → ``effort``
    - ``permission_mode`` → ``permissionMode``
    - ``max_turns``     → ``maxTurns``
    - ``filename``      → ``filename``
    - ``base_dir``      → ``baseDir``
    - ``critical_system_reminder`` → ``criticalSystemReminder_EXPERIMENTAL``
    - ``required_mcp_servers`` → ``requiredMcpServers``
    - ``background``    → ``background``
    - ``initial_prompt`` → ``initialPrompt``
    - ``memory``        → ``memory``
    - ``isolation``     → ``isolation``
    - ``omit_claude_md`` → ``omitClaudeMd``
    """

    # --- required ---
    name: str
    description: str

    # --- prompt / tools ---
    system_prompt: str | None = None
    tools: list[str] | None = None  # None means all tools allowed; ['*'] is equivalent
    disallowed_tools: list[str] | None = None

    # --- model & effort ---
    model: str | None = None  # model override; None means inherit default
    effort: str | int | None = None  # "low" | "medium" | "high" or positive int

    # --- permissions ---
    permission_mode: str | None = None  # one of PERMISSION_MODES

    # --- agent loop control ---
    max_turns: int | None = None  # maximum agentic turns before stopping; must be > 0

    # --- skills & mcp ---
    skills: list[str] = Field(default_factory=list)
    mcp_servers: list[Any] | None = None  # str refs or {name: config} dicts
    required_mcp_servers: list[str] | None = None  # server name patterns that must be present

    # --- hooks ---
    hooks: dict[str, Any] | None = None  # session-scoped hooks registered when agent starts

    # --- ui ---
    color: str | None = None  # one of AGENT_COLORS

    # --- lifecycle ---
    background: bool = False  # always run as background task when spawned
    initial_prompt: str | None = None  # prepended to the first user turn
    memory: str | None = None  # one of MEMORY_SCOPES
    isolation: str | None = None  # one of ISOLATION_MODES

    # --- metadata ---
    filename: str | None = None  # original filename without .md extension
    base_dir: str | None = None  # directory the agent definition was loaded from
    critical_system_reminder: str | None = None  # short message re-injected at every user turn
    pending_snapshot_update: dict[str, Any] | None = None  # for memory snapshot tracking
    omit_claude_md: bool = False  # skip CLAUDE.md injection for this agent

    # --- Python-specific ---
    permissions: list[str] = Field(default_factory=list)  # extra permission rules
    subagent_type: str = "general-purpose"  # routing key used by the harness
    source: Literal["builtin", "user", "plugin"] = "builtin"


# ---------------------------------------------------------------------------
# System-prompt constants (translated from TS built-in agent files)
# ---------------------------------------------------------------------------

_SHARED_AGENT_PREFIX = (
    "You are a specialized sub-agent for the Universal AI Assistant. "
    "Given the delegated task, use the tools available to you to complete it fully and correctly. "
    "Execute the task autonomously, and ensure you do not leave it half-done."
)

_SHARED_AGENT_GUIDELINES = """Your strengths:
- Gathering, analyzing, and synthesizing information across the internet and local environments.
- Finding data, configurations, and actionable insights across broad domains.
- Executing multi-step analysis, processing, or operational tasks autonomously.

Guidelines:
- When searching: search broadly if unsure, and use precise queries when confident.
- Start broad and narrow down to the core issue. Check multiple sources to verify information.
- Provide definitive, actionable insights in your output. Do not make assumptions for critical missing constraints; flag them in your final report if they block execution.
- Maintain a highly professional, confident, and structured (Markdown) formatting in your final report."""

_GENERAL_PURPOSE_SYSTEM_PROMPT = (
    f"{_SHARED_AGENT_PREFIX} When you complete the task, respond with a concise report covering "
    "what was done and any key findings — the caller will relay this to the user, so it only needs "
    f"the essentials.\n\n{_SHARED_AGENT_GUIDELINES}"
)

_RESEARCH_SYSTEM_PROMPT = """You are a Research and Data Gathering Specialist for the Universal AI Assistant. You excel at thoroughly navigating, exploring, and extracting information.

=== CRITICAL: READ-ONLY MODE ===
Your role is exclusively to gather data, read documents, and search the web. You are STRICTLY PROHIBITED from:
- Creating or modifying existing files or systems unless absolutely necessary for ephemeral caching.

Your strengths:
- Rapidly finding information using web search and fetch tools.
- Reading and analyzing complex documents and extracting key insights.
- Correlating facts across multiple sources.

Guidelines:
- Start broad and narrow down.
- Maintain rigorous fact-checking. 
- Return a structured, highly formatted report detailing your findings and sources.
"""

_STRATEGY_SYSTEM_PROMPT = """You are a Strategic Planner for the Universal AI Assistant. Your role is to break down complex goals into actionable implementation plans.

You will be provided with a set of requirements or a macro-goal.

## Your Process
1. **Understand Goals**: Deconstruct the core requirement.
2. **Context Gathering**: Read available data context or request specific knowledge base retrievals.
3. **Design Solution**: Create a step-by-step strategy. Consider trade-offs, timelines, and resource constraints.
4. **Detail the Plan**: Output a structured Markdown roadmap with clear milestones.

REMEMBER: You only plan. Do not execute the steps yourself. Output the strategy clearly so other execution agents can follow it.
"""

_REVIEW_SYSTEM_PROMPT = """You are a Quality Assurance and Review Specialist. Your job is not to passively agree with the provided output — it's to critically analyze and find logic holes, inaccuracies, or missing edge cases.

=== REVIEW STRATEGY ===
- **Fact-Checking**: Cross-verify claims made in the text against logical feasibility.
- **Completeness**: Did the output fully solve the user's root problem?
- **Clarity & Formatting**: Is the response sharp, perfectly structured in Markdown, and easy to consume?

=== OUTPUT FORMAT ===
Your report MUST contain:
1. **Identified Flaws/Gaps**: (Be direct, no politeness).
2. **Improvement Suggestions**: (Specific revisions).
3. **VERDICT**: End with exactly `VERDICT: PASS` or `VERDICT: FAIL`.
"""

_EXECUTION_SYSTEM_PROMPT = """You are an Action and Execution Specialist. Execute the assigned task precisely and autonomously.
Whether it's composing a formal document, writing a script, or executing a data pipeline, do it with extreme efficiency.

When finished, formulate a concise summary of the actions taken.
"""

# ---------------------------------------------------------------------------
# Built-in agent definitions
# ---------------------------------------------------------------------------

_BUILTIN_AGENTS: list[AgentDefinition] = [
    AgentDefinition(
        name="general-purpose",
        description=(
            "General-purpose agent for tasks requiring adaptive mixed capabilities. "
            "Use this agent for complex conversational reasoning or when the task doesn't clearly map to a specialist."
        ),
        tools=["*"],  # all tools
        system_prompt=_GENERAL_PURPOSE_SYSTEM_PROMPT,
        subagent_type="general-purpose",
        source="builtin",
        base_dir="built-in",
    ),
    AgentDefinition(
        name="researcher",
        description=(
            "Fast agent specialized for data gathering, internet search, and document reading. "
            "Use this when you need deep contextual background before making a decision."
        ),
        system_prompt=_RESEARCH_SYSTEM_PROMPT,
        model="inherit",
        omit_claude_md=True,
        subagent_type="researcher",
        source="builtin",
        base_dir="built-in",
    ),
    AgentDefinition(
        name="strategist",
        description=(
            "Strategic agent for designing step-by-step plans or analyzing complex requirements. "
            "Returns actionable roadmaps and architectural designs."
        ),
        system_prompt=_STRATEGY_SYSTEM_PROMPT,
        model="inherit",
        omit_claude_md=True,
        subagent_type="strategist",
        source="builtin",
        base_dir="built-in",
    ),
    AgentDefinition(
        name="executor",
        description=(
            "Action-focused agent for executing concrete tasks and creating deliverables. "
            "Best for document composition, data processing pipelines, and automations."
        ),
        tools=["*"],  # all tools
        system_prompt=_EXECUTION_SYSTEM_PROMPT,
        subagent_type="executor",
        source="builtin",
        base_dir="built-in",
    ),
    AgentDefinition(
        name="reviewer",
        description=(
            "Verification agent to review plans, reports, or task outputs before finalizing. "
            "Pass the output to this agent and it will deliver a PASS/FAIL verdict with critique."
        ),
        system_prompt=_REVIEW_SYSTEM_PROMPT,
        color="red",
        background=True,
        model="inherit",
        subagent_type="reviewer",
        source="builtin",
        base_dir="built-in",
    ),
]


def get_builtin_agent_definitions() -> list[AgentDefinition]:
    """Return the built-in agent definitions."""
    return list(_BUILTIN_AGENTS)


# ---------------------------------------------------------------------------
# Markdown / YAML-frontmatter loader
# ---------------------------------------------------------------------------


def _parse_agent_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from a markdown file.

    Returns a (frontmatter_dict, body) tuple. Uses ``yaml.safe_load`` for
    proper YAML parsing (supports nested structures for hooks, mcpServers, etc.).
    """
    frontmatter: dict[str, Any] = {}
    body = content

    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return frontmatter, body

    end_index: int | None = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = i
            break

    if end_index is None:
        return frontmatter, body

    fm_text = "\n".join(lines[1:end_index])
    try:
        parsed = yaml.safe_load(fm_text)
        if isinstance(parsed, dict):
            frontmatter = parsed
    except yaml.YAMLError:
        # Fall back to simple key:value parsing
        for fm_line in lines[1:end_index]:
            if ":" in fm_line:
                key, _, value = fm_line.partition(":")
                frontmatter[key.strip()] = value.strip().strip("'\"")

    # Body is everything after the closing ---
    body = "\n".join(lines[end_index + 1 :]).strip()
    return frontmatter, body


def _parse_str_list(raw: Any) -> list[str] | None:
    """Parse a comma-separated string or list into a list of strings."""
    if raw is None:
        return None
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        items = [t.strip() for t in raw.split(",") if t.strip()]
        return items if items else None
    return None


def _parse_positive_int(raw: Any) -> int | None:
    """Parse a positive integer from frontmatter, returning None if invalid."""
    if raw is None:
        return None
    try:
        val = int(raw)
        return val if val > 0 else None
    except (TypeError, ValueError):
        return None


def load_agents_dir(directory: Path) -> list[AgentDefinition]:
    """Load agent definitions from .md files in *directory*.

    Each file should contain YAML frontmatter with at least ``name`` and
    ``description`` fields. The markdown body becomes the ``system_prompt``.

    Supported frontmatter fields (all optional unless noted):

    Required:
    * ``name`` — agent type identifier
    * ``description`` — when-to-use description shown to the spawning agent

    Optional:
    * ``tools`` — comma-separated or YAML list of allowed tool names
    * ``disallowedTools`` / ``disallowed_tools`` — comma-separated or list of disallowed tools
    * ``model`` — model override (e.g. "haiku", "inherit")
    * ``effort`` — "low", "medium", "high", or a positive integer
    * ``permissionMode`` / ``permission_mode`` — one of PERMISSION_MODES
    * ``maxTurns`` / ``max_turns`` — positive integer turn limit
    * ``skills`` — comma-separated or list of skill names
    * ``mcpServers`` / ``mcp_servers`` — list of MCP server references or inline configs
    * ``hooks`` — YAML dict of session-scoped hooks
    * ``color`` — one of AGENT_COLORS
    * ``background`` — true/false; run as background task
    * ``initialPrompt`` / ``initial_prompt`` — string prepended to first user turn
    * ``memory`` — one of MEMORY_SCOPES
    * ``isolation`` — one of ISOLATION_MODES
    * ``omitClaudeMd`` / ``omit_claude_md`` — true/false; skip CLAUDE.md injection
    * ``criticalSystemReminder`` / ``critical_system_reminder`` — re-injected message
    * ``requiredMcpServers`` / ``required_mcp_servers`` — list of required server patterns
    * ``permissions`` — comma-separated extra permission rules (Python-specific)
    * ``subagent_type`` — routing key (Python-specific, defaults to name)
    """
    agents: list[AgentDefinition] = []

    if not directory.is_dir():
        return agents

    for path in sorted(directory.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
            frontmatter, body = _parse_agent_frontmatter(content)

            name = str(frontmatter.get("name", "")).strip() or path.stem
            description = str(frontmatter.get("description", "")).strip()
            if not description:
                description = f"Agent: {name}"

            # Unescape literal \n in descriptions from YAML
            description = description.replace("\\n", "\n")

            # --- tools ---
            tools = _parse_str_list(frontmatter.get("tools"))

            # --- disallowed tools ---
            disallowed_raw = frontmatter.get(
                "disallowedTools", frontmatter.get("disallowed_tools")
            )
            disallowed_tools = _parse_str_list(disallowed_raw)

            # --- model ---
            model_raw = frontmatter.get("model")
            model: str | None = None
            if isinstance(model_raw, str) and model_raw.strip():
                trimmed = model_raw.strip()
                model = "inherit" if trimmed.lower() == "inherit" else trimmed

            # --- effort ---
            effort_raw = frontmatter.get("effort")
            effort: str | int | None = None
            if effort_raw is not None:
                if isinstance(effort_raw, int):
                    effort = effort_raw if effort_raw > 0 else None
                elif isinstance(effort_raw, str) and effort_raw in EFFORT_LEVELS:
                    effort = effort_raw
                else:
                    logger.debug("Agent %s: invalid effort %r", name, effort_raw)

            # --- permissionMode ---
            perm_raw = frontmatter.get("permissionMode", frontmatter.get("permission_mode"))
            permission_mode: str | None = None
            if isinstance(perm_raw, str) and perm_raw in PERMISSION_MODES:
                permission_mode = perm_raw
            elif perm_raw is not None:
                logger.debug("Agent %s: invalid permissionMode %r", name, perm_raw)

            # --- maxTurns ---
            max_turns_raw = frontmatter.get("maxTurns", frontmatter.get("max_turns"))
            max_turns = _parse_positive_int(max_turns_raw)
            if max_turns_raw is not None and max_turns is None:
                logger.debug("Agent %s: invalid maxTurns %r", name, max_turns_raw)

            # --- skills ---
            skills_raw = frontmatter.get("skills")
            skills = _parse_str_list(skills_raw) or []

            # --- mcpServers ---
            mcp_raw = frontmatter.get("mcpServers", frontmatter.get("mcp_servers"))
            mcp_servers: list[Any] | None = None
            if isinstance(mcp_raw, list):
                mcp_servers = mcp_raw if mcp_raw else None

            # --- hooks ---
            hooks_raw = frontmatter.get("hooks")
            hooks: dict[str, Any] | None = None
            if isinstance(hooks_raw, dict):
                hooks = hooks_raw

            # --- color ---
            color_raw = frontmatter.get("color")
            color: str | None = None
            if isinstance(color_raw, str) and color_raw in AGENT_COLORS:
                color = color_raw

            # --- background ---
            bg_raw = frontmatter.get("background")
            background = bg_raw is True or bg_raw == "true"

            # --- initialPrompt ---
            ip_raw = frontmatter.get("initialPrompt", frontmatter.get("initial_prompt"))
            initial_prompt: str | None = None
            if isinstance(ip_raw, str) and ip_raw.strip():
                initial_prompt = ip_raw

            # --- memory ---
            memory_raw = frontmatter.get("memory")
            memory: str | None = None
            if isinstance(memory_raw, str) and memory_raw in MEMORY_SCOPES:
                memory = memory_raw
            elif memory_raw is not None:
                logger.debug("Agent %s: invalid memory %r", name, memory_raw)

            # --- isolation ---
            iso_raw = frontmatter.get("isolation")
            isolation: str | None = None
            if isinstance(iso_raw, str) and iso_raw in ISOLATION_MODES:
                isolation = iso_raw
            elif iso_raw is not None:
                logger.debug("Agent %s: invalid isolation %r", name, iso_raw)

            # --- omitClaudeMd ---
            ocm_raw = frontmatter.get("omitClaudeMd", frontmatter.get("omit_claude_md"))
            omit_claude_md = ocm_raw is True or ocm_raw == "true"

            # --- criticalSystemReminder ---
            csr_raw = frontmatter.get(
                "criticalSystemReminder", frontmatter.get("critical_system_reminder")
            )
            critical_system_reminder: str | None = None
            if isinstance(csr_raw, str) and csr_raw.strip():
                critical_system_reminder = csr_raw

            # --- requiredMcpServers ---
            rms_raw = frontmatter.get(
                "requiredMcpServers", frontmatter.get("required_mcp_servers")
            )
            required_mcp_servers = _parse_str_list(rms_raw)

            # --- permissions (Python-specific) ---
            permissions: list[str] = []
            raw_perms = frontmatter.get("permissions", "")
            if raw_perms:
                permissions = [p.strip() for p in str(raw_perms).split(",") if p.strip()]

            agents.append(
                AgentDefinition(
                    name=name,
                    description=description,
                    system_prompt=body or None,
                    tools=tools,
                    disallowed_tools=disallowed_tools,
                    model=model,
                    effort=effort,
                    permission_mode=permission_mode,
                    max_turns=max_turns,
                    skills=skills,
                    mcp_servers=mcp_servers,
                    hooks=hooks,
                    color=color,
                    background=background,
                    initial_prompt=initial_prompt,
                    memory=memory,
                    isolation=isolation,
                    omit_claude_md=omit_claude_md,
                    critical_system_reminder=critical_system_reminder,
                    required_mcp_servers=required_mcp_servers,
                    permissions=permissions,
                    filename=path.stem,
                    base_dir=str(directory),
                    subagent_type=str(frontmatter.get("subagent_type", name)),
                    source="user",
                )
            )
        except Exception:
            logger.debug("Failed to parse agent from %s", path, exc_info=True)
            continue

    return agents


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _get_user_agents_dir() -> Path:
    """Return the user agent definitions directory."""
    return get_config_dir() / "agents"


def get_all_agent_definitions() -> list[AgentDefinition]:
    """Return all agent definitions: built-in + user + plugin.

    Merge order (last writer wins for same ``name``):
    1. Built-in agents
    2. User agents (~/.openharness/agents/)
    3. Plugin agents (loaded from active plugins)

    User definitions override built-ins with the same name; plugin definitions
    override user definitions with the same name.
    """
    agent_map: dict[str, AgentDefinition] = {}

    # 1. Built-ins (lowest priority)
    for agent in get_builtin_agent_definitions():
        agent_map[agent.name] = agent

    # 2. User-defined agents
    user_agents = load_agents_dir(_get_user_agents_dir())
    for agent in user_agents:
        agent_map[agent.name] = agent

    # 3. Plugin agents — loaded lazily to avoid import cycles
    try:
        from openharness.plugins.loader import load_plugins  # noqa: PLC0415
        from openharness.config.settings import load_settings  # noqa: PLC0415

        settings = load_settings()
        import os  # noqa: PLC0415

        cwd = os.getcwd()
        for plugin in load_plugins(settings, cwd):
            if not plugin.enabled:
                continue
            for agent_def in getattr(plugin, "agents", []):
                if isinstance(agent_def, AgentDefinition):
                    agent_map[agent_def.name] = agent_def
    except Exception:
        pass

    return list(agent_map.values())


def get_agent_definition(name: str) -> AgentDefinition | None:
    """Return the agent definition for *name*, or ``None`` if not found."""
    for agent in get_all_agent_definitions():
        if agent.name == name:
            return agent
    return None


def has_required_mcp_servers(agent: AgentDefinition, available_servers: list[str]) -> bool:
    """Return True if the agent's required MCP servers are all available.

    Each pattern in ``required_mcp_servers`` must match (case-insensitive
    substring) at least one server in ``available_servers``.
    """
    if not agent.required_mcp_servers:
        return True
    return all(
        any(pattern.lower() in server.lower() for server in available_servers)
        for pattern in agent.required_mcp_servers
    )


def filter_agents_by_mcp_requirements(
    agents: list[AgentDefinition],
    available_servers: list[str],
) -> list[AgentDefinition]:
    """Return only agents whose required MCP servers are available."""
    return [a for a in agents if has_required_mcp_servers(a, available_servers)]
