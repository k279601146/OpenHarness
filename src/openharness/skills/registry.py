"""Skill registry."""

from __future__ import annotations

from openharness.skills.types import SkillDefinition


class SkillRegistry:
    """Store loaded skills by name."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        """Register one skill."""
        for key in (skill.name, skill.command_name, skill.display_name, *skill.aliases):
            if key:
                self._skills[key] = skill

    def get(self, name: str) -> SkillDefinition | None:
        """Return a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[SkillDefinition]:
        """Return all unique skills sorted by command name."""
        unique: dict[tuple[str, str | None], SkillDefinition] = {}
        for skill in self._skills.values():
            unique[(skill.source, skill.path or skill.name)] = skill
        return sorted(unique.values(), key=lambda skill: skill.command_name or skill.name)

    def find_by_trigger(self, query: str) -> list[SkillDefinition]:
        """Return skills whose trigger metadata matches *query*."""
        query_lower = query.lower()
        results: list[SkillDefinition] = []
        for skill in self.list_skills():
            triggers = skill.metadata.get("triggers", []) if isinstance(skill.metadata, dict) else []
            if isinstance(triggers, str):
                triggers = [triggers]
            if any(str(trigger).lower() in query_lower for trigger in triggers) or any(
                alias.lower() in query_lower for alias in skill.aliases
            ):
                results.append(skill)
        return results
