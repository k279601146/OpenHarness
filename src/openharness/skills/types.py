"""Skill data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillDefinition:
    """A loaded skill."""

    name: str
    description: str
    content: str
    source: str
    path: str | None = None
    skill_type: str = "logic"  # "logic" or "aesthetic"
    metadata: dict = field(default_factory=dict)
