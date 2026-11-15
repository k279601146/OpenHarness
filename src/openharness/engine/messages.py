"""Conversation message models used by the query engine."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


COMMON_IMAGE_MIME_TYPES: dict[str, str] = {
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".jfif": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".avif": "image/avif",
}

for _ext, _mime in COMMON_IMAGE_MIME_TYPES.items():
    mimetypes.add_type(_mime, _ext)

COMMON_VIDEO_MIME_TYPES: dict[str, str] = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
}

for _ext, _mime in COMMON_VIDEO_MIME_TYPES.items():
    mimetypes.add_type(_mime, _ext)


class TextBlock(BaseModel):
    """Plain text content."""

    type: Literal["text"] = "text"
    text: str
    cache_control: dict[str, Any] | None = None


def sniff_image_media_type(raw_bytes: bytes) -> str | None:
    """Detect common raster image MIME types from magic bytes."""
    if len(raw_bytes) >= 8 and raw_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(raw_bytes) >= 3 and raw_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(raw_bytes) >= 6 and raw_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(raw_bytes) >= 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


class ImageBlock(BaseModel):
    """Image content encoded inline for multimodal providers."""

    type: Literal["image"] = "image"
    media_type: str
    data: str
    source_path: str = ""

    @classmethod
    def from_bytes_with_metadata(
        cls,
        raw_bytes: bytes,
        *,
        media_type: str | None = None,
        source_path: str = "",
        max_edge: int | None = 1600,
        quality: int = 92,
    ) -> tuple["ImageBlock", dict[str, Any]]:
        """Create a base64-backed ImageBlock from raw bytes and return dimension/compression metadata."""
        sniffed = sniff_image_media_type(raw_bytes)
        effective_mime = sniffed or media_type or ""
        if (not effective_mime or not effective_mime.startswith("image/")) and source_path:
            guessed, _ = mimetypes.guess_type(source_path)
            suffix = Path(source_path).suffix.lower()
            effective_mime = guessed or COMMON_IMAGE_MIME_TYPES.get(suffix, "")
        if not effective_mime or not effective_mime.startswith("image/"):
            raise ValueError(f"Unsupported image content: {source_path or 'bytes'}")

        original_width = 0
        original_height = 0
        width = 0
        height = 0
        final_bytes = raw_bytes
        final_mime = effective_mime

        try:
            import io
            from PIL import Image

            with Image.open(io.BytesIO(raw_bytes)) as img:
                original_width, original_height = img.size
                width, height = original_width, original_height
                longest = max(original_width, original_height)
                needs_resize = bool(max_edge and longest > max_edge)
                should_reencode = needs_resize or (
                    bool(max_edge)
                    and len(raw_bytes) > 256 * 1024
                    and (effective_mime != "image/gif" or not getattr(img, "is_animated", False))
                )
                if should_reencode:
                    if needs_resize and max_edge:
                        scale = max_edge / longest
                        new_size = (max(1, int(round(original_width * scale))), max(1, int(round(original_height * scale))))
                        resampled = img.resize(new_size, Image.Resampling.LANCZOS)
                    else:
                        resampled = img

                    if resampled.mode in ("CMYK", "P"):
                        resampled = resampled.convert("RGBA" if "transparency" in resampled.info else "RGB")

                    buf = io.BytesIO()
                    resampled.save(buf, format="WEBP", quality=quality, method=6)
                    compressed_bytes = buf.getvalue()
                    if needs_resize or len(compressed_bytes) < len(raw_bytes):
                        final_bytes = compressed_bytes
                        final_mime = "image/webp"
                        width, height = resampled.size
        except Exception:
            pass  # Fall back to raw bytes on any image processing error

        payload = base64.b64encode(final_bytes).decode("ascii")
        block = cls(media_type=final_mime, data=payload, source_path=source_path)
        meta: dict[str, Any] = {
            "media_type": final_mime,
            "original_media_type": effective_mime,
            "width": width,
            "height": height,
            "original_width": original_width,
            "original_height": original_height,
            "byte_length": len(final_bytes),
            "original_byte_length": len(raw_bytes),
        }
        return block, meta

    @classmethod
    def from_bytes(
        cls,
        raw_bytes: bytes,
        *,
        media_type: str | None = None,
        source_path: str = "",
        max_edge: int | None = 1600,
        quality: int = 92,
    ) -> "ImageBlock":
        """Create a base64-backed ImageBlock from raw bytes."""
        block, _ = cls.from_bytes_with_metadata(
            raw_bytes,
            media_type=media_type,
            source_path=source_path,
            max_edge=max_edge,
            quality=quality,
        )
        return block

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        media_type: str | None = None,
        max_edge: int | None = 1600,
        quality: int = 92,
    ) -> "ImageBlock":
        """Load a local image file into a base64-backed content block, optimizing large images for LLM vision."""
        resolved = Path(path).expanduser().resolve()
        if not media_type or not media_type.startswith("image/"):
            guessed, _ = mimetypes.guess_type(str(resolved))
            media_type = guessed or COMMON_IMAGE_MIME_TYPES.get(resolved.suffix.lower())
        if not media_type or not media_type.startswith("image/"):
            raise ValueError(f"Unsupported image attachment: {resolved}")
        raw_bytes = resolved.read_bytes()
        return cls.from_bytes(
            raw_bytes,
            media_type=media_type,
            source_path=str(resolved),
            max_edge=max_edge,
            quality=quality,
        )


class VideoBlock(BaseModel):
    """Video content encoded inline for multimodal providers."""

    type: Literal["video"] = "video"
    media_type: str
    data: str
    source_path: str = ""

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        media_type: str | None = None,
        max_bytes: int = 35 * 1024 * 1024,
    ) -> "VideoBlock":
        """Load a local video file into a base64-backed content block."""
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Video file not found: {resolved}")
        if not media_type or not media_type.startswith("video/"):
            guessed, _ = mimetypes.guess_type(str(resolved))
            media_type = guessed or COMMON_VIDEO_MIME_TYPES.get(resolved.suffix.lower())
        if not media_type or not media_type.startswith("video/"):
            raise ValueError(f"Unsupported video attachment: {resolved}")
        size = resolved.stat().st_size
        if max_bytes and size > max_bytes:
            raise ValueError(f"Video file size {size} exceeds max allowed inline limit {max_bytes}")
        raw_bytes = resolved.read_bytes()
        payload = base64.b64encode(raw_bytes).decode("ascii")
        return cls(media_type=media_type, data=payload, source_path=str(resolved))


class ToolUseBlock(BaseModel):
    """A request from the model to execute a named tool."""

    type: Literal["tool_use"] = "tool_use"
    id: str = Field(default_factory=lambda: f"toolu_{uuid4().hex}")
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    """Tool result content sent back to the model."""

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str
    is_error: bool = False
    images: list[ImageBlock] = Field(default_factory=list)
    result_metadata: dict[str, Any] = Field(default_factory=dict)
    cache_control: dict[str, Any] | None = None


ContentBlock = Annotated[
    TextBlock | ImageBlock | VideoBlock | ToolUseBlock | ToolResultBlock,
    Field(discriminator="type"),
]


class ConversationMessage(BaseModel):
    """A single assistant or user message."""

    role: Literal["user", "assistant"]
    content: list[ContentBlock] = Field(default_factory=list)

    @field_validator("content", mode="before")
    @classmethod
    def _normalize_content(cls, value: Any) -> list[Any]:
        """Normalize legacy/null payloads before block validation."""
        if value is None:
            return []
        return value

    @classmethod
    def from_user_text(cls, text: str) -> "ConversationMessage":
        """Construct a user message from raw text."""
        return cls(role="user", content=[TextBlock(text=text)])

    @classmethod
    def from_user_content(cls, content: list[ContentBlock]) -> "ConversationMessage":
        """Construct a user message from explicit content blocks."""
        return cls(role="user", content=list(content))

    @property
    def text(self) -> str:
        """Return concatenated text blocks."""
        return "".join(
            block.text for block in self.content if isinstance(block, TextBlock)
        )

    @property
    def tool_uses(self) -> list[ToolUseBlock]:
        """Return all tool calls contained in the message."""
        return [block for block in self.content if isinstance(block, ToolUseBlock)]

    def to_api_param(self) -> dict[str, Any]:
        """Convert the message into Anthropic SDK message params."""
        return {
            "role": self.role,
            "content": [serialize_content_block(block) for block in self.content],
        }

    def is_effectively_empty(self) -> bool:
        """Return True when the message carries no useful content."""
        if self.content:
            for block in self.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    return False
                if isinstance(block, (ImageBlock, VideoBlock, ToolUseBlock, ToolResultBlock)):
                    return False
        return True


def sanitize_conversation_messages(messages: list[ConversationMessage]) -> list[ConversationMessage]:
    """Normalize restored conversation history into a provider-safe sequence.

    This drops legacy empty assistant messages and trims malformed trailing tool
    turns, such as an assistant ``tool_use`` message that never received a
    matching user ``tool_result`` response. Those broken tails can happen when a
    session is interrupted mid-turn and would later cause OpenAI-compatible
    providers to reject the resumed conversation.
    """
    sanitized: list[ConversationMessage] = []
    pending_tool_use_ids: set[str] = set()
    pending_tool_use_index: int | None = None

    for message in messages:
        if message.role == "assistant" and message.is_effectively_empty():
            continue

        tool_uses = message.tool_uses if message.role == "assistant" else []
        tool_results = [
            block for block in message.content if isinstance(block, ToolResultBlock)
        ] if message.role == "user" else []

        matched_pending_tool_results = False
        if pending_tool_use_ids:
            result_ids = {block.tool_use_id for block in tool_results}
            if message.role != "user" or not pending_tool_use_ids.issubset(result_ids):
                if pending_tool_use_index is not None and pending_tool_use_index < len(sanitized):
                    sanitized.pop(pending_tool_use_index)
                pending_tool_use_ids = set()
                pending_tool_use_index = None
            else:
                matched_pending_tool_results = True
                pending_tool_use_ids = set()
                pending_tool_use_index = None

        if message.role == "user" and tool_results and not matched_pending_tool_results:
            content = [
                block for block in message.content if not isinstance(block, ToolResultBlock)
            ]
            if not content:
                continue
            message = ConversationMessage(role="user", content=content)

        sanitized.append(message)

        if tool_uses:
            pending_tool_use_ids = {block.id for block in tool_uses}
            pending_tool_use_index = len(sanitized) - 1

    if pending_tool_use_ids and pending_tool_use_index is not None and pending_tool_use_index < len(sanitized):
        sanitized.pop(pending_tool_use_index)

    return sanitized


def serialize_content_block(block: ContentBlock) -> dict[str, Any]:
    """Convert a local content block into the provider wire format."""
    result: dict[str, Any]
    if isinstance(block, TextBlock):
        result = {"type": "text", "text": block.text}
    elif isinstance(block, ImageBlock):
        result = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": block.media_type,
                "data": block.data,
            },
        }
    elif isinstance(block, VideoBlock):
        result = {
            "type": "video",
            "source": {
                "type": "base64",
                "media_type": block.media_type,
                "data": block.data,
            },
        }
    elif isinstance(block, ToolUseBlock):
        result = {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    else:
        if block.images:
            content_blocks: list[dict[str, Any]] = []
            if block.content:
                content_blocks.append({"type": "text", "text": block.content})
            for image in block.images:
                content_blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image.media_type,
                            "data": image.data,
                        },
                    }
                )
            result = {
                "type": "tool_result",
                "tool_use_id": block.tool_use_id,
                "content": content_blocks,
                "is_error": block.is_error,
            }
        else:
            result = {
                "type": "tool_result",
                "tool_use_id": block.tool_use_id,
                "content": block.content,
                "is_error": block.is_error,
            }

    cache_control = getattr(block, "cache_control", None)
    if cache_control:
        result["cache_control"] = cache_control
    return result


def assistant_message_from_api(raw_message: Any) -> ConversationMessage:
    """Convert an Anthropic SDK message object into a conversation message."""
    content: list[ContentBlock] = []

    for raw_block in getattr(raw_message, "content", []):
        block_type = getattr(raw_block, "type", None)
        if block_type == "text":
            content.append(TextBlock(text=getattr(raw_block, "text", "")))
        elif block_type == "tool_use":
            content.append(
                ToolUseBlock(
                    id=getattr(raw_block, "id", f"toolu_{uuid4().hex}"),
                    name=getattr(raw_block, "name", ""),
                    input=dict(getattr(raw_block, "input", {}) or {}),
                )
            )

    return ConversationMessage(role="assistant", content=content)
