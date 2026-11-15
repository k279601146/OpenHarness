"""Skill registry with layered rank precedence and `SkillProviderObservation` semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openharness.skills.types import SkillDefinition

SOURCE_DEFAULT_RANK: dict[str, int] = {
    "project": 100,
    "plugin": 200,
    "user": 300,
    "bundled": 600,
}


@dataclass(frozen=True)
class SkillProviderObservation:
    """Observation emitted by a layered skill provider (`dsh-skills` pattern).

    Lower ``rank`` has higher priority (e.g., 100 project .. 600 bundled).
    When ``complete`` is False, missing candidates do not evict lower-priority skills.
    """

    source: str
    rank: int
    candidates: tuple[SkillDefinition, ...]
    complete: bool = True


class SkillResourceResolver:
    """Unified abstraction (`SkillResourceBase`) for resolving local vs sandbox skill resources."""

    @staticmethod
    def resolve_local_resource_lines(skill: SkillDefinition) -> list[str]:
        if not skill.base_dir:
            return []
        return [
            f"Base directory for this skill: {skill.base_dir}",
            "Resolve relative paths mentioned by this skill against that base directory. "
            "Load referenced resources only as needed.",
        ]


class SkillRegistry:
    """Store loaded skills by name with rank precedence."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}
        self._ranks: dict[str, int] = {}
        self._observations: list[SkillProviderObservation] = []

    def register(self, skill: SkillDefinition, *, rank: int | None = None) -> None:
        """Register one skill respecting provider rank (lower rank number wins)."""
        effective_rank = (
            rank
            if rank is not None
            else SOURCE_DEFAULT_RANK.get(getattr(skill, "source", "user"), 400)
        )
        for key in (skill.name, skill.command_name, skill.display_name, *skill.aliases):
            if not key:
                continue
            existing_rank = self._ranks.get(key)
            if existing_rank is None or effective_rank <= existing_rank:
                self._skills[key] = skill
                self._ranks[key] = effective_rank

    def apply_observation(self, observation: SkillProviderObservation) -> None:
        """Apply a `SkillProviderObservation` to the registry."""
        self._observations.append(observation)
        for skill in observation.candidates:
            self.register(skill, rank=observation.rank)

    @property
    def observations(self) -> tuple[SkillProviderObservation, ...]:
        return tuple(self._observations)

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
