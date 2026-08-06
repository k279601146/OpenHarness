"""Versioned session event protocol for durable engine logs."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage
from openharness.engine.stream_events import (
    AgentProgressEvent,
    AssistantReasoningDelta,
    AssistantTextDelta,
    AssistantTurnComplete,
    CompactProgressEvent,
    ErrorEvent,
    StatusEvent,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)

SESSION_EVENT_SCHEMA_VERSION = 1

_TEXT_PREVIEW_CHARS = 240
_MAX_STRING_CHARS = 500
_MAX_COLLECTION_ITEMS = 40
_MAX_DEPTH = 4

_SENSITIVE_KEY_RE = re.compile(
    r"(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|"
    r"token|secret|cookie|password|passwd|jwt|session|prompt)",
    re.IGNORECASE,
)
_PATH_KEY_RE = re.compile(r"(^|_)(cwd|path|file|filename|directory|workspace|root)($|_)", re.IGNORECASE)
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\b(Bearer)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|cookie)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{12,})\b"),
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{20,})\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)


@dataclass(frozen=True)
class SessionEvent:
    """Append-only event record persisted as JSONL."""

    event_type: str
    session_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    turn_id: str | None = None
    event_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: float = field(default_factory=time.time)
    schema_version: int = SESSION_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", sanitize_event_payload(self.payload))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "created_at": self.created_at,
            "turn_id": self.turn_id,
            "payload": self.payload,
        }


def build_session_event(
    event_type: str,
    *,
    session_id: str,
    payload: dict[str, Any] | None = None,
    turn_id: str | None = None,
) -> SessionEvent:
    return SessionEvent(
        event_type=str(event_type),
        session_id=str(session_id or "default"),
        payload=payload or {},
        turn_id=str(turn_id) if turn_id else None,
    )


def message_event_payload(message: ConversationMessage) -> dict[str, Any]:
    tool_uses = getattr(message, "tool_uses", [])
    return {
        "role": message.role,
        "text": summarize_text(message.text, include_preview=False),
        "content_block_count": len(getattr(message, "content", []) or []),
        "tool_use_count": len(tool_uses),
        "tool_uses": [
            {
                "id": getattr(block, "id", None),
                "name": getattr(block, "name", None),
                "input_keys": sorted((getattr(block, "input", {}) or {}).keys())
                if isinstance(getattr(block, "input", None), dict)
                else [],
            }
            for block in tool_uses[:_MAX_COLLECTION_ITEMS]
        ],
    }


def stream_event_to_session_event(
    event: StreamEvent,
    *,
    session_id: str,
    fallback_turn_id: str | None = None,
) -> SessionEvent | None:
    event_type = type(event).__name__
    turn_id = stream_event_turn_id(event) or fallback_turn_id

    if isinstance(event, AssistantTextDelta):
        return build_session_event(
            "assistant_text_delta",
            session_id=session_id,
            turn_id=turn_id,
            payload={"text": summarize_text(event.text, include_preview=False)},
        )
    if isinstance(event, AssistantReasoningDelta):
        return build_session_event(
            "assistant_reasoning_delta",
            session_id=session_id,
            turn_id=turn_id,
            payload={"text": summarize_text(event.text, include_preview=False)},
        )
    if isinstance(event, AssistantTurnComplete):
        return build_session_event(
            "assistant_turn_complete",
            session_id=session_id,
            turn_id=turn_id,
            payload={
                "message": message_event_payload(event.message),
                "usage": _usage_payload(event.usage),
            },
        )
    if isinstance(event, ToolExecutionStarted):
        return build_session_event(
            "tool_execution_started",
            session_id=session_id,
            turn_id=turn_id,
            payload={
                "tool_name": event.tool_name,
                "tool_use_id": event.tool_use_id,
                "tool_input": _summarize_tool_input(event.tool_input),
                "rationale": summarize_text(event.rationale or ""),
                "display_name": event.display_name,
                "start_message": summarize_text(event.start_message or ""),
            },
        )
    if isinstance(event, ToolExecutionCompleted):
        return build_session_event(
            "tool_execution_completed",
            session_id=session_id,
            turn_id=turn_id,
            payload={
                "tool_name": event.tool_name,
                "tool_use_id": event.tool_use_id,
                "is_error": event.is_error,
                "output_length": len(event.output or ""),
                "metadata": sanitize_event_payload(event.metadata or {}),
            },
        )
    if isinstance(event, AgentProgressEvent):
        return build_session_event(
            "agent_progress",
            session_id=session_id,
            turn_id=turn_id,
            payload={
                "phase": event.phase,
                "status": event.status,
                "message": summarize_text(event.message or ""),
                "tool_name": event.tool_name,
                "tool_use_id": event.tool_use_id,
                "workspace": sanitize_event_payload({"workspace": event.workspace}).get("workspace"),
                "path": sanitize_event_payload({"path": event.path}).get("path"),
                "detail": summarize_text(event.detail or ""),
                "metadata": sanitize_event_payload(event.metadata or {}),
            },
        )
    if isinstance(event, ErrorEvent):
        return build_session_event(
            "error",
            session_id=session_id,
            turn_id=turn_id,
            payload={"message": summarize_text(event.message), "recoverable": event.recoverable},
        )
    if isinstance(event, StatusEvent):
        return build_session_event(
            "status",
            session_id=session_id,
            turn_id=turn_id,
            payload={
                "message": summarize_text(event.message),
                "kind": event.kind,
                "attempt": event.attempt,
                "max_attempts": event.max_attempts,
                "delay_seconds": event.delay_seconds,
                "detail": summarize_text(event.detail or ""),
            },
        )
    if isinstance(event, CompactProgressEvent):
        return build_session_event(
            "compact_progress",
            session_id=session_id,
            turn_id=turn_id,
            payload={
                "phase": event.phase,
                "trigger": event.trigger,
                "message": summarize_text(event.message or ""),
                "attempt": event.attempt,
                "checkpoint": event.checkpoint,
                "metadata": sanitize_event_payload(event.metadata or {}),
            },
        )

    return build_session_event(
        "stream_event",
        session_id=session_id,
        turn_id=turn_id,
        payload={"runtime_type": event_type},
    )


def sanitize_event_payload(payload: Any) -> Any:
    return _sanitize_value(payload)


def summarize_text(
    text: str,
    *,
    limit: int = _TEXT_PREVIEW_CHARS,
    include_preview: bool = True,
) -> dict[str, Any]:
    text = str(text or "")
    redacted = _redact_text(_redact_url_query(text))
    payload: dict[str, Any] = {
        "length": len(text),
        "redacted_length": len(redacted),
        "truncated": len(redacted) > limit,
        "sha256": sha256(redacted.encode("utf-8", errors="replace")).hexdigest(),
    }
    if include_preview:
        payload["preview"] = redacted[:limit]
    return payload


def dumps_event_record(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _usage_payload(usage: UsageSnapshot) -> dict[str, Any]:
    try:
        return usage.model_dump()
    except AttributeError:
        return {}


def stream_event_turn_id(event: StreamEvent) -> str | None:
    metadata = getattr(event, "metadata", None)
    if isinstance(metadata, dict) and metadata.get("turn_id"):
        return str(metadata.get("turn_id"))
    return None


def _summarize_tool_input(tool_input: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(tool_input, dict):
        return {"type": type(tool_input).__name__}
    return {
        "keys": sorted(str(key) for key in tool_input.keys()),
        "shape": _value_shape(tool_input),
    }


def _value_shape(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return {"type": type(value).__name__, "truncated": True}
    if isinstance(value, dict):
        items = list(value.items())
        shape: dict[str, Any] = {}
        for raw_key, item in items[:_MAX_COLLECTION_ITEMS]:
            item_key = str(raw_key)
            if _SENSITIVE_KEY_RE.search(item_key):
                shape[item_key] = {"type": type(item).__name__, "redacted": True}
            else:
                shape[item_key] = _value_shape(item, depth=depth + 1)
        if len(items) > _MAX_COLLECTION_ITEMS:
            shape["_omitted_count"] = len(items) - _MAX_COLLECTION_ITEMS
        return shape
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        return {
            "type": type(value).__name__,
            "count": len(items),
            "items": [_value_shape(item, depth=depth + 1) for item in items[: min(3, _MAX_COLLECTION_ITEMS)]],
        }
    if isinstance(value, str):
        redacted = _redact_text(_redact_url_query(value))
        return {
            "type": "str",
            "length": len(value),
            "redacted_length": len(redacted),
            "sha256": sha256(redacted.encode("utf-8", errors="replace")).hexdigest(),
        }
    if value is None:
        return {"type": "none"}
    if isinstance(value, bool):
        return {"type": "bool"}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "int", "value": value}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    return {"type": type(value).__name__}


def _sanitize_value(value: Any, *, key: str | None = None, depth: int = 0) -> Any:
    if key == "shape":
        return _sanitize_shape(value)
    if key and _SENSITIVE_KEY_RE.search(key):
        return "<redacted>"
    if key and _PATH_KEY_RE.search(key):
        return _summarize_pathlike(value)
    if depth > _MAX_DEPTH:
        return {"type": type(value).__name__, "truncated": True}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_string(value, key=key)
    if isinstance(value, dict):
        items = list(value.items())
        data: dict[str, Any] = {}
        for raw_key, item in items[:_MAX_COLLECTION_ITEMS]:
            item_key = str(raw_key)
            data[item_key] = _sanitize_value(item, key=item_key, depth=depth + 1)
        if len(items) > _MAX_COLLECTION_ITEMS:
            data["_omitted_count"] = len(items) - _MAX_COLLECTION_ITEMS
        return data
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        data = [_sanitize_value(item, depth=depth + 1) for item in items[:_MAX_COLLECTION_ITEMS]]
        if len(items) > _MAX_COLLECTION_ITEMS:
            data.append({"_omitted_count": len(items) - _MAX_COLLECTION_ITEMS})
        return data
    return _sanitize_string(str(value), key=key)


def _sanitize_shape(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return {"type": type(value).__name__, "truncated": True}
    if isinstance(value, dict):
        items = list(value.items())
        data: dict[str, Any] = {}
        for raw_key, item in items[:_MAX_COLLECTION_ITEMS]:
            data[str(raw_key)] = _sanitize_shape(item, depth=depth + 1)
        if len(items) > _MAX_COLLECTION_ITEMS:
            data["_omitted_count"] = len(items) - _MAX_COLLECTION_ITEMS
        return data
    if isinstance(value, list):
        data = [_sanitize_shape(item, depth=depth + 1) for item in value[:_MAX_COLLECTION_ITEMS]]
        if len(value) > _MAX_COLLECTION_ITEMS:
            data.append({"_omitted_count": len(value) - _MAX_COLLECTION_ITEMS})
        return data
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if value in {"str", "int", "float", "bool", "none", "dict", "list", "tuple", "set"}:
            return value
        return "<redacted>"
    return {"type": type(value).__name__}


def _sanitize_string(value: str, *, key: str | None = None) -> Any:
    value = _redact_text(_redact_url_query(value))
    if key in {"tool_name", "tool_use_id", "phase", "status", "kind", "role", "type", "display_name", "checkpoint"}:
        return value[:_MAX_STRING_CHARS]
    if "\n" in value or len(value) > 80:
        return summarize_text(value, limit=min(_TEXT_PREVIEW_CHARS, _MAX_STRING_CHARS))
    return value[:_MAX_STRING_CHARS]


def _summarize_pathlike(value: Any) -> Any:
    if value in (None, ""):
        return None
    text = str(value)
    if "://" in text:
        return _redact_url_query(text)
    normalized = text.replace("\\", "/").rstrip("/")
    name = normalized.rsplit("/", 1)[-1] if normalized else ""
    return {"name": name, "redacted": True}


def _redact_text(text: str) -> str:
    redacted = text
    for pattern in _SECRET_TEXT_PATTERNS:
        redacted = pattern.sub("<redacted>", redacted)
    return redacted


def _redact_url_query(text: str) -> str:
    if "://" not in text:
        return text
    parts = text.split()
    changed = False
    for index, part in enumerate(parts):
        try:
            parsed = urlsplit(part)
        except ValueError:
            continue
        if not parsed.scheme or not parsed.netloc or not parsed.query:
            continue
        parts[index] = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "<redacted>", parsed.fragment))
        changed = True
    return " ".join(parts) if changed else text
