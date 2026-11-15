"""Runtime hook result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HookResult:
    """Result from a single hook execution."""

    hook_type: str
    success: bool
    output: str = ""
    blocked: bool = False
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    modified_input: dict[str, Any] | None = None
    additional_contexts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AggregatedHookResult:
    """Aggregated result for a hook event with monotonic deny semantics."""

    results: list[HookResult] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        """Return whether any hook blocked continuation (monotonic: once blocked, stays blocked)."""
        return any(result.blocked for result in self.results)

    @property
    def reason(self) -> str:
        """Return the first blocking reason, if any."""
        for result in self.results:
            if result.blocked:
                return result.reason or result.output
        return ""

    @property
    def modified_input(self) -> dict[str, Any] | None:
        """Return the latest non-blocked input rewrite across hooks, if any."""
        if self.blocked:
            return None
        latest: dict[str, Any] | None = None
        for result in self.results:
            if result.modified_input is not None:
                latest = dict(result.modified_input)
        return latest

    @property
    def additional_contexts(self) -> list[str]:
        """Return all advisory context strings emitted by hooks."""
        items: list[str] = []
        for result in self.results:
            for ctx in result.additional_contexts:
                if ctx and ctx.strip():
                    items.append(ctx)
        return items
