"""Skill loading from bundled and user directories."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import yaml

from openharness.config.paths import get_config_dir
from openharness.config.settings import load_settings
from openharness.skills.bundled import get_bundled_skills
from openharness.skills.registry import SkillRegistry
from openharness.skills.types import SkillDefinition

logger = logging.getLogger(__name__)


def get_user_skills_dir() -> Path:
    """Return the primary user skills directory (~/.openharness/skills)."""
    path = get_config_dir() / "skills"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_community_skills_dir() -> Path:
    """Return the community standard skills directory (~/.agents/skills)."""
    return Path.home() / ".agents" / "skills"


def get_saas_skill_dirs(data_root: str | Path, user_id: str | int) -> list[Path]:
    """Return the list of skill directories for a SaaS user based on their data root."""
    base = Path(data_root) / str(user_id) / "shared_assets" / "user-home"
    return [
        base / ".skills",
        base / ".agents" / "skills",
    ]


def load_skill_registry(
    cwd: str | Path | None = None,
    *,
    extra_skill_dirs: Iterable[str | Path] | None = None,
    extra_plugin_roots: Iterable[str | Path] | None = None,
    settings=None,
    normalize_path_func: callable | None = None,
) -> SkillRegistry:
    """Load bundled and user-defined skills."""
    registry = SkillRegistry()
    for skill in get_bundled_skills():
        registry.register(skill)
    for skill in load_user_skills(normalize_path_func=normalize_path_func):
        registry.register(skill)
    for skill in load_skills_from_dirs(extra_skill_dirs, normalize_path_func=normalize_path_func):
        registry.register(skill)
    if cwd is not None:
        from openharness.plugins.loader import load_plugins

        resolved_settings = settings or load_settings()
        for plugin in load_plugins(resolved_settings, cwd, extra_roots=extra_plugin_roots):
            if not plugin.enabled:
                continue
            for skill in plugin.skills:
                registry.register(skill)
    return registry


def load_user_skills(normalize_path_func: callable | None = None) -> list[SkillDefinition]:
    """Load markdown skills from all standard user config directories."""
    dirs = [get_user_skills_dir(), get_community_skills_dir()]
    return load_skills_from_dirs(dirs, source="user", normalize_path_func=normalize_path_func)


def load_skills_from_dirs(
    directories: Iterable[str | Path] | None,
    *,
    source: str = "user",
    normalize_path_func: callable | None = None,
) -> list[SkillDefinition]:
    """Load markdown skills from one or more directories.

    Supported layout:
    - ``<root>/<skill-dir>/SKILL.md``
    """
    skills: list[SkillDefinition] = []
    if not directories:
        return skills
    seen: set[Path] = set()
    for directory in directories:
        root = Path(directory).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        candidates: list[Path] = []
        for child in sorted(root.iterdir()):
            if child.is_dir():
                skill_path = child / "SKILL.md"
                if skill_path.exists():
                    candidates.append(skill_path)
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            content = path.read_text(encoding="utf-8")
            default_name = path.parent.name
            name, description = _parse_skill_markdown(default_name, content)
            
            # 路径脱敏：如果在沙箱模式下，将宿主机物理路径转换为容器内路径
            reported_path = str(path)
            if normalize_path_func:
                reported_path = normalize_path_func(path)
                
            skills.append(
                SkillDefinition(
                    name=name,
                    description=description,
                    content=content,
                    source=source,
                    path=reported_path,
                )
            )
    return skills


def _parse_skill_markdown(default_name: str, content: str) -> tuple[str, str]:
    """Parse name and description from a skill markdown file with YAML frontmatter support."""
    name = default_name
    description = ""

    lines = content.splitlines()

    # Try YAML frontmatter first (--- ... ---)
    if content.startswith("---\n"):
        end_index = content.find("\n---\n", 4)
        if end_index != -1:
            try:
                metadata = yaml.safe_load(content[4:end_index])
                if isinstance(metadata, dict):
                    val = metadata.get("name")
                    if isinstance(val, str) and val.strip():
                        name = val.strip()
                    val = metadata.get("description")
                    if isinstance(val, str) and val.strip():
                        description = val.strip()
            except yaml.YAMLError:
                logger.debug("Failed to parse YAML frontmatter for skill %s", default_name)

    # Fallback: extract from headings and first paragraph
    if not description:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                if not name or name == default_name:
                    name = stripped[2:].strip() or default_name
                continue
            if stripped and not stripped.startswith("---") and not stripped.startswith("#"):
                description = stripped[:200]
                break

    if not description:
        description = f"Skill: {name}"
    return name, description
