"""Heuristic token estimation utilities."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_IMAGE_TOKEN_ESTIMATE = 1_600
MIN_IMAGE_TOKEN_ESTIMATE = 64
MAX_IMAGE_TOKEN_ESTIMATE = 16_000


def _read_image_token_override() -> int | None:
    raw = os.environ.get("OPENHARNESS_IMAGE_TOKEN_ESTIMATE", "").strip()
    if not raw:
        return None
    try:
        return max(MIN_IMAGE_TOKEN_ESTIMATE, int(raw))
    except ValueError:
        log.warning("Ignoring invalid OPENHARNESS_IMAGE_TOKEN_ESTIMATE=%r", raw)
        return None


def _is_non_ascii_dense(text: str) -> bool:
    """Detect non-ASCII heavy text (e.g. CJK) that tokenizes denser than English."""
    sample = text[:512]
    if not sample:
        return False
    non_ascii = sum(1 for ch in sample if ord(ch) > 127)
    return non_ascii * 3 >= len(sample)


def estimate_tokens(text: str) -> int:
    """Estimate tokens from plain text using a conservative heuristic.

    English averages ~4 chars/token; CJK/non-ASCII-heavy text averages ~1.5-2 chars/token.
    """
    if not text:
        return 0
    if _is_non_ascii_dense(text):
        return max(1, (len(text) + 1) // 2)
    return max(1, (len(text) + 3) // 4)


def estimate_image_tokens(block: Any = None, *, default_tokens: int = DEFAULT_IMAGE_TOKEN_ESTIMATE) -> int:
    """Estimate token cost for a single inline image block."""
    override = _read_image_token_override()
    if override is not None:
        return override
    if block is None:
        return max(MIN_IMAGE_TOKEN_ESTIMATE, default_tokens)
    data = getattr(block, "data", None)
    if isinstance(data, str) and data:
        scaled = max(default_tokens, len(data) // 240)
        return min(MAX_IMAGE_TOKEN_ESTIMATE, scaled)
    return max(MIN_IMAGE_TOKEN_ESTIMATE, default_tokens)


def estimate_tool_result_tokens(
    content: str,
    images: Sequence[Any] | None = None,
    *,
    default_image_tokens: int = DEFAULT_IMAGE_TOKEN_ESTIMATE,
) -> int:
    """Estimate tokens for a multimodal tool result (text + attached images)."""
    total = estimate_tokens(content)
    if images:
        total += sum(
            estimate_image_tokens(image, default_tokens=default_image_tokens)
            for image in images
        )
    return total


def estimate_message_tokens(messages: list[str]) -> int:
    """Estimate tokens for a collection of message strings."""
    return sum(estimate_tokens(message) for message in messages)


def strip_lone_surrogates(text: str) -> str:
    """Remove unpaired UTF-16 surrogates so JSON/provider serialization stays valid."""
    if not text:
        return text
    return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")


def truncate_text_to_token_budget(
    text: str,
    max_tokens: int,
    *,
    head_ratio: float = 0.65,
    omission_template: str = "\n\n[... {omitted_chars} chars (~{omitted_tokens} tokens) omitted ...]\n\n",
) -> tuple[str, int]:
    """Deterministically prune text into *max_tokens* keeping head and tail."""
    content = strip_lone_surrogates(text or "")
    if max_tokens <= 0:
        return "", estimate_tokens(content)
    current_tokens = estimate_tokens(content)
    if current_tokens <= max_tokens:
        return content, 0

    chars_per_token = 2 if _is_non_ascii_dense(content) else 4
    total_char_budget = max(64, max_tokens * chars_per_token)
    sample_marker = omission_template.format(omitted_chars=len(content), omitted_tokens=current_tokens)
    if total_char_budget <= len(sample_marker) + 32:
        clipped = content[:total_char_budget].rstrip()
        saved = max(0, current_tokens - estimate_tokens(clipped))
        return clipped, saved

    available = total_char_budget - len(sample_marker)
    clamped_ratio = min(0.85, max(0.15, head_ratio))
    head_budget = max(16, int(available * clamped_ratio))
    tail_budget = max(16, available - head_budget)
    if head_budget + tail_budget >= len(content):
        return content, 0

    head = content[:head_budget].rstrip()
    tail = content[-tail_budget:].lstrip()
    omitted_chars = max(0, len(content) - len(head) - len(tail))
    omitted_tokens = max(1, estimate_tokens(content) - estimate_tokens(head) - estimate_tokens(tail))
    marker = omission_template.format(omitted_chars=omitted_chars, omitted_tokens=omitted_tokens)
    pruned = f"{head}{marker}{tail}" if tail else head
    saved = max(0, current_tokens - estimate_tokens(pruned))
    return pruned, saved

