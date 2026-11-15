"""Historical inline image offloading and multimodal limit recovery helpers."""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from collections.abc import Sequence
from pathlib import Path

from openharness.engine.messages import (
    ContentBlock,
    ConversationMessage,
    ImageBlock,
    TextBlock,
    ToolResultBlock,
)

log = logging.getLogger(__name__)

IMAGE_OFFLOAD_MARKER = "[Image offloaded:"
MAX_IMAGE_OFFLOAD_RETRIES = 4

_EXT_BY_MEDIA_TYPE: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}

_IMAGE_LIMIT_PHRASES = (
    "too many images",
    "maximum number of images",
    "max images",
    "image limit",
    "images per request",
    "image count exceeds",
    "exceeds the maximum number of images",
    "exceeded maximum images",
    "image payload too large",
    "too many media",
    "request size exceeds",
)


def is_image_limit_error(exc: Exception) -> bool:
    """Return True when a provider exception indicates too many inline images."""
    text = str(exc).lower()
    if any(phrase in text for phrase in _IMAGE_LIMIT_PHRASES):
        return True
    if "image" in text and re.search(r"\b(?:at most|maximum|max(?:imum)? of|exceed(?:s|ed)?|limit(?:ed)? to)\s+\d+\s+images?\b", text):
        return True
    return False


def extract_image_limit_from_error(exc: Exception) -> int | None:
    """Extract numeric per-request image cap from provider error messages when present."""
    text = str(exc).lower().replace(",", "")
    patterns = (
        r"(?:at most|maximum of|max(?:imum)?|up to|limit(?:ed)? to)\s+(\d+)\s+images?",
        r"(\d+)\s+images?\s+(?:per request|allowed|max(?:imum)?)",
        r"too many images\s*\(\s*\d+\s*>\s*(\d+)\s*\)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return max(0, int(match.group(1)))
            except ValueError:
                return None
    return None


def count_inline_images(messages: Sequence[ConversationMessage]) -> int:
    """Count all inline ImageBlock objects across message content and tool results."""
    total = 0
    for msg in messages:
        for block in msg.content:
            if isinstance(block, ImageBlock):
                total += 1
            elif isinstance(block, ToolResultBlock) and block.images:
                total += len(block.images)
    return total


def _image_offload_dir(workspace_dir: Path | None) -> Path | None:
    if workspace_dir is None:
        return None
    target = workspace_dir / ".openharness" / "image_offloads"
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except OSError:
        return None


def _persist_image_reference(
    block: ImageBlock,
    *,
    offload_dir: Path | None,
    expose_path: bool = True,
) -> str:
    """Return a durable non-inline reference for an offloaded ImageBlock."""
    raw_source = (block.source_path or "").strip()
    if raw_source:
        if not expose_path:
            return Path(raw_source).name or "image"
        return raw_source

    if offload_dir is not None and block.data:
        try:
            raw_bytes = base64.b64decode(block.data, validate=False)
        except Exception:
            raw_bytes = b""
        if raw_bytes:
            digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
            ext = _EXT_BY_MEDIA_TYPE.get((block.media_type or "").lower(), ".img")
            target = offload_dir / f"img_{digest}{ext}"
            try:
                if not target.exists():
                    target.write_bytes(raw_bytes)
                return str(target) if expose_path else target.name
            except OSError:
                pass
    return "inline image data"


def _format_offload_notice(reference: str, media_type: str, *, allow_read_hint: bool) -> str:
    hint = " Use read_file if you still need to inspect it." if allow_read_hint and reference != "inline image data" else ""
    return f"{IMAGE_OFFLOAD_MARKER} {reference} ({media_type}).{hint}]"


def offload_oldest_images(
    messages: list[ConversationMessage],
    *,
    count: int | None = None,
    keep_recent_images: int = 0,
    workspace_dir: Path | None = None,
    expose_paths: bool = True,
) -> int:
    """Offload the oldest inline ImageBlocks in *messages* to durable text placeholders.

    Mutates *messages* in place while preserving conversation role structure and
    tool_use/tool_result pairing. Returns the number of images offloaded.
    """
    total_images = count_inline_images(messages)
    if total_images == 0:
        return 0

    keep_recent = max(0, keep_recent_images)
    max_removable = max(0, total_images - keep_recent)
    if max_removable == 0:
        return 0

    to_offload = max_removable if count is None else min(max_removable, max(0, count))
    if to_offload <= 0:
        return 0

    offload_dir = _image_offload_dir(workspace_dir)
    remaining = to_offload
    offloaded = 0

    for msg in messages:
        if remaining <= 0:
            break
        changed = False
        next_content: list[ContentBlock] = []
        for block in msg.content:
            if remaining <= 0:
                next_content.append(block)
                continue

            if isinstance(block, ImageBlock):
                ref = _persist_image_reference(block, offload_dir=offload_dir, expose_path=expose_paths)
                notice = _format_offload_notice(ref, block.media_type, allow_read_hint=expose_paths)
                next_content.append(TextBlock(text=notice))
                remaining -= 1
                offloaded += 1
                changed = True
                continue

            if isinstance(block, ToolResultBlock) and block.images:
                kept_images: list[ImageBlock] = []
                notices: list[str] = []
                for img in block.images:
                    if remaining > 0:
                        ref = _persist_image_reference(img, offload_dir=offload_dir, expose_path=expose_paths)
                        notices.append(_format_offload_notice(ref, img.media_type, allow_read_hint=expose_paths))
                        remaining -= 1
                        offloaded += 1
                        changed = True
                    else:
                        kept_images.append(img)
                if notices:
                    base_text = block.content.rstrip()
                    joined_notices = "\n".join(notices)
                    updated_text = f"{base_text}\n\n{joined_notices}" if base_text else joined_notices
                    next_content.append(
                        block.model_copy(
                            update={
                                "content": updated_text,
                                "images": kept_images,
                            }
                        )
                    )
                else:
                    next_content.append(block)
                continue

            next_content.append(block)

        if changed:
            msg.content = next_content

    if offloaded > 0:
        log.info("Offloaded %d oldest inline image(s) to text placeholders", offloaded)
    return offloaded
