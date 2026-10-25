"""Conversation message models used by the query engine."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class TextBlock(BaseModel):
    """Plain text content."""

    type: Literal["text"] = "text"
    text: str
    cache_control: dict[str, Any] | None = None


class ImageBlock(BaseModel):
    """Image content encoded inline for multimodal providers."""

    type: Literal["image"] = "image"
    media_type: str
    data: str
    source_path: str = ""

    @classmethod
    def from_path(cls, path: str | Path, *, max_edge: int | None = 1600, quality: int = 92) -> "ImageBlock":
        """Load a local image file into a base64-backed content block, optimizing large images for LLM vision."""
        resolved = Path(path).expanduser().resolve()
        media_type, _ = mimetypes.guess_type(str(resolved))
        if not media_type or not media_type.startswith("image/"):
            raise ValueError(f"Unsupported image attachment: {resolved}")
        raw_bytes = resolved.read_bytes()

        # If vision optimization is requested and file is large (>256KB), generate an optimized vision buffer
        if max_edge and len(raw_bytes) > 256 * 1024:
            try:
                import io
                from PIL import Image

                with Image.open(resolved) as img:
                    w, h = img.size
                    longest = max(w, h)
                    needs_resize = longest > max_edge
                    if needs_resize or (media_type == "image/png" and len(raw_bytes) > 500 * 1024):
                        if needs_resize:
                            scale = max_edge / longest
                            new_size = (int(w * scale), int(h * scale))
                            resampled = img.resize(new_size, Image.Resampling.LANCZOS)
                        else:
                            resampled = img

                        if resampled.mode in ("CMYK", "P"):
                            resampled = resampled.convert("RGBA" if "transparency" in resampled.info else "RGB")

                        buf = io.BytesIO()
                        resampled.save(buf, format="WEBP", quality=quality, method=6)
                        compressed_bytes = buf.getvalue()
                        if len(compressed_bytes) < len(raw_bytes):
                            payload = base64.b64encode(compressed_bytes).decode("ascii")
                            return cls(media_type="image/webp", data=payload, source_path=str(resolved))
            except Exception:
                pass  # Fall back to raw bytes on any image processing error

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
    result_metadata: dict[str, Any] = Field(default_factory=dict)
    cache_control: dict[str, Any] | None = None


ContentBlock = Annotated[
    TextBlock | ImageBlock | ToolUseBlock | ToolResultBlock,
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
                if isinstance(block, (ImageBlock, ToolUseBlock, ToolResultBlock)):
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
    elif isinstance(block, ToolUseBlock):
        result = {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
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
