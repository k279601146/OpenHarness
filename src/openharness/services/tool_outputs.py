"""Tool-output context budget helpers."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Any

from openharness.services.token_estimation import (
    estimate_tool_result_tokens,
    strip_lone_surrogates,
    truncate_text_to_token_budget,
)

log = logging.getLogger(__name__)

DEFAULT_TOOL_OUTPUT_INLINE_CHARS = 16_000
DEFAULT_TOOL_OUTPUT_PREVIEW_CHARS = 3_000
DEFAULT_TOOL_OUTPUT_INLINE_TOKENS = 4_000
DEFAULT_TOOL_OUTPUT_PREVIEW_TOKENS = 750
DEFAULT_MICROCOMPACT_TOOL_RESULT_CHARS = 4_000

# Tools whose primary contract is delivering requested instructions or bounded file slices
# into the model context. Their outputs must not be blindly truncated by spill policy.
NON_OFFLOADABLE_TOOL_NAMES: frozenset[str] = frozenset({"skill", "read_file"})
NON_MICROCOMPACTABLE_TOOL_NAMES: frozenset[str] = frozenset({"skill"})
SPILL_OMISSION_MARKER = "\n\n[...]\n\n"
PRUNED_OMISSION_TEMPLATE = "\n\n[... pruned {omitted_chars} chars (~{omitted_tokens} tokens) deterministically ...]\n\n"


def _read_positive_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        log.warning("Ignoring invalid %s=%r", name, raw)
        return default


def tool_output_inline_chars() -> int:
    return _read_positive_int_env(
        "OPENHARNESS_TOOL_OUTPUT_INLINE_CHARS",
        DEFAULT_TOOL_OUTPUT_INLINE_CHARS,
        minimum=256,
    )


def tool_output_preview_chars() -> int:
    return _read_positive_int_env(
        "OPENHARNESS_TOOL_OUTPUT_PREVIEW_CHARS",
        DEFAULT_TOOL_OUTPUT_PREVIEW_CHARS,
        minimum=128,
    )


def tool_output_inline_tokens() -> int:
    return _read_positive_int_env(
        "OPENHARNESS_TOOL_OUTPUT_INLINE_TOKENS",
        DEFAULT_TOOL_OUTPUT_INLINE_TOKENS,
        minimum=128,
    )


def tool_output_preview_tokens() -> int:
    return _read_positive_int_env(
        "OPENHARNESS_TOOL_OUTPUT_PREVIEW_TOKENS",
        DEFAULT_TOOL_OUTPUT_PREVIEW_TOKENS,
        minimum=64,
    )


def microcompact_tool_result_chars() -> int:
    return _read_positive_int_env(
        "OPENHARNESS_MICROCOMPACT_TOOL_RESULT_CHARS",
        DEFAULT_MICROCOMPACT_TOOL_RESULT_CHARS,
        minimum=256,
    )


def should_offload_tool_output(
    tool_name: str,
    content: str,
    *,
    max_inline_chars: int | None = None,
    max_inline_tokens: int | None = None,
    images: Sequence[Any] | None = None,
) -> bool:
    """Return True when a tool result exceeds char or multimodal token budgets."""
    normalized = (tool_name or "").strip().lower()
    if normalized in NON_OFFLOADABLE_TOOL_NAMES:
        return False
    text = content or ""
    char_limit = max_inline_chars if max_inline_chars is not None else tool_output_inline_chars()
    if len(text) > char_limit:
        return True
    token_limit = max_inline_tokens if max_inline_tokens is not None else tool_output_inline_tokens()
    return estimate_tool_result_tokens(text, images) > token_limit


def retain_tool_output_preview(
    text: str,
    max_chars: int,
    *,
    max_tokens: int | None = None,
) -> str:
    """Retain both head and tail of a spilled tool output within *max_chars* and *max_tokens*."""
    content = strip_lone_surrogates(text or "")
    if max_chars <= 0:
        return ""
    if max_tokens is not None and max_tokens > 0:
        content, _ = truncate_text_to_token_budget(
            content,
            max_tokens,
            head_ratio=0.6,
            omission_template="\n\n[...]\n\n",
        )
    if len(content) <= max_chars:
        return content
    if max_chars <= len(SPILL_OMISSION_MARKER) + 32:
        return content[:max_chars].rstrip()

    available = max_chars - len(SPILL_OMISSION_MARKER)
    head_budget = max(1, (available * 3) // 5)
    tail_budget = max(1, available - head_budget)
    head = content[:head_budget].rstrip()
    tail = content[-tail_budget:].lstrip()
    if not tail:
        return head
    return f"{head}{SPILL_OMISSION_MARKER}{tail}"


def prune_tool_result_text(
    text: str,
    *,
    max_chars: int = 3_200,
    max_tokens: int | None = 800,
    head_ratio: float = 0.65,
) -> str:
    """Deterministically prune an oversized historical tool result without an LLM call."""
    content = strip_lone_surrogates(text or "")
    if not content:
        return content
    token_budget = max_tokens if max_tokens is not None and max_tokens > 0 else max(64, max_chars // 4)
    pruned, _ = truncate_text_to_token_budget(
        content,
        token_budget,
        head_ratio=head_ratio,
        omission_template=PRUNED_OMISSION_TEMPLATE,
    )
    if len(pruned) > max_chars:
        return retain_tool_output_preview(pruned, max_chars)
    return pruned


def is_microcompactable_tool_result(tool_name: str, content: str) -> bool:
    """Return True when a tool result should be eligible for old-result clearing."""
    normalized = tool_name.strip()
    if normalized.lower() in NON_MICROCOMPACTABLE_TOOL_NAMES:
        return False
    if normalized.startswith("mcp__"):
        return True
    return len(content) >= microcompact_tool_result_chars()

