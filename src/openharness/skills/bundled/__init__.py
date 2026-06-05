"""Bundled skill definitions loaded from markdown files or SKILL.md directories."""

from __future__ import annotations

from pathlib import Path

from openharness.skills._frontmatter import (
    optional_frontmatter_str,
    parse_bool_frontmatter,
    parse_skill_frontmatter,
    parse_skill_metadata,
)
from openharness.skills.types import SkillDefinition

_BUNDLED_ROOT = Path(__file__).parent


def get_bundled_skills() -> list[SkillDefinition]:
    """Load all bundled skills from content/ and aesthetics/ directories."""
    skills: list[SkillDefinition] = []
    for sub_dir, skill_type in (("content", "logic"), ("aesthetics", "aesthetic")):
        target_dir = _BUNDLED_ROOT / sub_dir
        if not target_dir.exists():
            continue
        for path in _iter_bundled_skill_files(target_dir):
            content = path.read_text(encoding="utf-8")
            command_name = path.stem if path.name != "SKILL.md" else path.parent.name
            metadata = _parse_metadata(command_name, content)
            display_name = metadata["name"] if metadata["name"] != command_name else None
            frontmatter = metadata["frontmatter"]
            skills.append(
                SkillDefinition(
                    name=metadata["name"],
                    description=metadata["description"],
                    content=content,
                    source="bundled",
                    path=str(path),
                    base_dir=str(path.parent),
                    command_name=command_name,
                    display_name=display_name,
                    aliases=_frontmatter_aliases(frontmatter),
                    user_invocable=metadata["user_invocable"],
                    disable_model_invocation=metadata["disable_model_invocation"],
                    model=metadata["model"],
                    argument_hint=metadata["argument_hint"],
                    skill_type=skill_type,
                    metadata=dict(frontmatter),
                )
            )
    return skills


def _iter_bundled_skill_files(target_dir: Path) -> list[Path]:
    """Return bundled skill files in stable command-name order."""
    direct_files = sorted(target_dir.glob("*.md"))
    directory_files = sorted(
        skill_file
        for child in target_dir.iterdir()
        if child.is_dir() and (skill_file := child / "SKILL.md").exists()
    )
    return sorted(
        [*direct_files, *directory_files],
        key=lambda path: path.stem if path.name != "SKILL.md" else path.parent.name,
    )


def _parse_frontmatter(default_name: str, content: str) -> tuple[str, str]:
    """Extract name and description from a bundled skill markdown file."""
    return parse_skill_frontmatter(
        default_name,
        content,
        fallback_template="Bundled skill: {name}",
    )


def _parse_metadata(default_name: str, content: str) -> dict:
    parsed = parse_skill_metadata(default_name, content, fallback_template="Bundled skill: {name}")
    frontmatter = parsed.get("frontmatter")
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return {
        "name": str(parsed["name"]),
        "description": str(parsed["description"]),
        "user_invocable": parse_bool_frontmatter(frontmatter.get("user-invocable"), default=True),
        "disable_model_invocation": parse_bool_frontmatter(
            frontmatter.get("disable-model-invocation"),
            default=False,
        ),
        "model": optional_frontmatter_str(frontmatter.get("model")),
        "argument_hint": optional_frontmatter_str(frontmatter.get("argument-hint")),
        "frontmatter": frontmatter,
    }


def _frontmatter_aliases(frontmatter: dict[str, object]) -> tuple[str, ...]:
    aliases: list[str] = []
    for key in ("aliases", "triggers", "keywords"):
        raw = frontmatter.get(key)
        if isinstance(raw, str) and raw.strip():
            aliases.append(raw.strip())
        elif isinstance(raw, (list, tuple, set)):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    aliases.append(item.strip())
    return tuple(dict.fromkeys(aliases))
