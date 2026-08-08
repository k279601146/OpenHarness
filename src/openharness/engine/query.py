"""Core tool-aware query loop."""

from __future__ import annotations

import inspect
import logging
import os
import re
import time
import asyncio
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable
from uuid import uuid4

from pydantic import ValidationError

from openharness.api.client import SupportsStreamingMessages
from openharness.api.usage import UsageSnapshot
from openharness.config.paths import get_data_dir
from openharness.engine.messages import (
    ConversationMessage,
    ToolResultBlock,
)
from openharness.engine.stream_events import (
    AgentProgressEvent,
    AssistantTurnComplete,
    CompactProgressEvent,
    ErrorEvent,
    StatusEvent,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from openharness.engine.model_turn import ModelTurnComplete, stream_model_turn
from openharness.engine.tool_progress import run_tool_with_progress
from openharness.engine.turn_state import (
    RunTimingTrace as _RunTimingTrace,
    progress_event as _progress_event,
    query_cancel_reason as _query_cancel_reason,
    query_cancelled as _query_cancelled,
)
from openharness.hooks import HookEvent, HookExecutor
from openharness.permissions.checker import PermissionChecker
from openharness.services.tool_outputs import tool_output_inline_chars, tool_output_preview_chars
from openharness.tools.ask_user_question_tool import AskUserQuestionPaused
from openharness.tools.base import BaseTool, CancellationToken, ToolExecutionContext, ToolResult
from openharness.tools.base import ToolRegistry
from openharness.tools.cron_policy import (
    SCHEDULE_MANAGEMENT_TOOL_NAMES,
    SCHEDULED_RUN_CRON_BLOCK_MESSAGE,
    is_schedule_management_blocked,
)
from openharness.utils.paths import normalize_host_path

AUTO_COMPACT_STATUS_MESSAGE = "Auto-compacting conversation memory to keep things fast and focused."
REACTIVE_COMPACT_STATUS_MESSAGE = "Prompt too long; compacting conversation memory and retrying."
MAX_SAFE_COMPLETION_TOKENS = 256_000

log = logging.getLogger(__name__)


PermissionPrompt = Callable[[str, str], Awaitable[bool]]
AskUserPrompt = Callable[[str | dict[str, Any]], Awaitable[str]]

MAX_TRACKED_READ_FILES = 6
MAX_TRACKED_SKILLS = 8
MAX_TRACKED_ASYNC_AGENT_EVENTS = 8
MAX_TRACKED_ASYNC_AGENT_TASKS = 12
MAX_TRACKED_WORK_LOG = 10
MAX_TRACKED_USER_GOALS = 5
MAX_TRACKED_ACTIVE_ARTIFACTS = 8
MAX_TRACKED_VERIFIED_WORK = 10
AGENT_PROGRESS_HEARTBEAT_SECONDS = 8.0


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((time.monotonic() - started_at) * 1000))


def _format_tool_validation_error(tool_name: str, exc: ValidationError) -> str:
    reasons: list[str] = []
    object_string_fields: list[str] = []
    object_fields_by_tool = {
        "generate_image": {"brief", "output", "edit_policy", "text_policy"},
        "generate_video": {"brief", "output"},
        "create_handdraw_story_video": {"output", "caption_policy", "bgm"},
    }
    object_fields = object_fields_by_tool.get(tool_name, set())
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()) if part != "__root__") or "input"
        error_type = str(error.get("type") or "")
        message = str(error.get("msg") or "invalid value")
        if error_type == "extra_forbidden":
            reasons.append(f"unexpected field `{loc}`")
        elif error_type == "model_type":
            if isinstance(error.get("input"), str):
                reasons.append(f"`{loc}` must be an object, not a JSON string")
                object_string_fields.append(loc)
            else:
                reasons.append(f"`{loc}` must be an object")
        elif error_type.startswith("literal_error"):
            reasons.append(f"`{loc}` has an unsupported value")
        elif error_type == "missing":
            if loc in object_fields:
                reasons.append(f"`{loc}` is required and must be an object")
                object_string_fields.append(loc)
            else:
                reasons.append(f"`{loc}` is required")
        else:
            reasons.append(f"`{loc}`: {message}")
    detail = "; ".join(reasons[:6]) or "input does not match the tool schema"
    if len(reasons) > 6:
        detail += f"; plus {len(reasons) - 6} more issue(s)"
    retry_hint = ""
    if object_string_fields:
        fields = ", ".join(f"`{field}`" for field in object_string_fields[:4])
        retry_hint = f" Retry by calling {tool_name} again with {fields} as nested object values, using {{}} when empty, not quoted JSON."
    return f"invalid_canonical_request: {tool_name} input does not match its tool schema. {detail}.{retry_hint}"


def _safe_request_failure_detail(exc: Exception) -> dict[str, Any] | None:
    body = getattr(exc, "body", None)
    if not isinstance(body, dict) or not body:
        return None
    detail: dict[str, Any] = {}
    for key in ("event_type", "status", "finish_reason", "request_id", "content_chars", "reasoning_chars", "tool_call_count", "hosted_tool_events_seen"):
        value = body.get(key)
        if value not in (None, "", [], {}):
            detail[key] = value
    event_ref = body.get("event_ref")
    if isinstance(event_ref, dict) and event_ref:
        detail["event_ref"] = {
            key: value
            for key, value in event_ref.items()
            if value not in (None, "", [], {})
        }
    incomplete_details = body.get("incomplete_details")
    if isinstance(incomplete_details, dict) and incomplete_details:
        detail["incomplete_details"] = {
            key: value
            for key, value in incomplete_details.items()
            if value not in (None, "", [], {})
        }
    elif isinstance(incomplete_details, str) and incomplete_details:
        match = re.search(r"reason=['\"]?([a-z0-9_:-]+)['\"]?", incomplete_details, re.IGNORECASE)
        if match:
            detail["incomplete_details"] = {"reason": match.group(1)}
    error = body.get("error")
    if error not in (None, "", [], {}):
        detail["error"] = error
    usage = body.get("usage")
    if isinstance(usage, dict) and usage:
        detail["usage"] = usage
    return detail or None


def _concrete_path(path: Path) -> Path:
    return normalize_host_path(Path.cwd(), path)


def _is_prompt_too_long_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        needle in text
        for needle in (
            "prompt too long",
            "context_length_exceeded",
            "context length",
            "maximum context",
            "context window",
            "input tokens exceed",
            "messages resulted in",
            "reduce the length of the messages",
            "configured limit",
            "too many tokens",
            "too large for the model",
            "maximum context length",
            "exceed_context",
            "exceeds the available context size",
            "available context size",
        )
    )


def _bounded_completion_tokens(max_tokens: int, context_window_tokens: int | None = None) -> int:
    """Return a conservative per-request output token cap.

    Some OpenAI-compatible providers reject very large ``max_tokens`` before
    the request reaches model-side context management.  Keep oversized user
    config from making every turn fail while preserving normal defaults.
    """
    limit = MAX_SAFE_COMPLETION_TOKENS
    if context_window_tokens is not None and context_window_tokens > 0:
        limit = min(limit, int(context_window_tokens))
    return max(1, min(int(max_tokens), limit))


def _tool_available_for_context(tool_name: str, context: QueryContext) -> bool:
    if (
        tool_name in SCHEDULE_MANAGEMENT_TOOL_NAMES
        and is_schedule_management_blocked(context.tool_metadata)
    ):
        return False
    return True


def _tool_unavailable_message(tool_name: str, context: QueryContext) -> str:
    if (
        tool_name in SCHEDULE_MANAGEMENT_TOOL_NAMES
        and is_schedule_management_blocked(context.tool_metadata)
    ):
        return SCHEDULED_RUN_CRON_BLOCK_MESSAGE
    return (
        f"{tool_name} is not available for the active model. "
        "Use the model's native image understanding instead."
    )


CORE_TOOL_SCHEMA_NAMES = {
    "ask_user_question",
    "bash",
    "brief",
    "create_folder",
    "deliver_artifact",
    "edit_file",
    "enter_plan_mode",
    "exit_plan_mode",
    "glob",
    "grep",
    "list_mcp_resources",
    "mcp_auth",
    "prepare_web_image_reference",
    "read_file",
    "read_mcp_resource",
    "skill",
    "sleep",
    "todo_write",
    "tool_search",
    "web_fetch",
    "web_search",
    "write_file",
}

MEDIA_TOOL_SCHEMA_NAMES = {"generate_image", "generate_video", "create_handdraw_story_video"}
TASK_TOOL_SCHEMA_NAMES = {
    "agent",
    "send_message",
    "task_create",
    "task_get",
    "task_list",
    "task_output",
    "task_stop",
    "task_update",
    "team_create",
    "team_delete",
}
SCHEDULE_TOOL_SCHEMA_NAMES = set(SCHEDULE_MANAGEMENT_TOOL_NAMES) | {"remote_trigger"}


_WORKSPACE_WRITE_TOOL_NAMES = {"bash", "create_folder", "write_file", "edit_file", "deliver_artifact"}
_TASK_MUTATION_TOOL_NAMES = {
    "agent",
    "send_message",
    "task_create",
    "task_stop",
    "task_update",
    "team_create",
    "team_delete",
}
_SCHEDULE_MUTATION_TOOL_NAMES = {"cron_create", "cron_delete", "cron_toggle", "remote_trigger"}


def _tool_execution_group(context: QueryContext, tool_name: str) -> str | None:
    tool = context.tool_registry.get(tool_name)
    if tool is not None:
        explicit_group = getattr(tool, "execution_group", None)
        if explicit_group:
            return str(explicit_group)
        if getattr(tool, "parallel_safe", True) is False:
            return f"tool:{tool_name}"
    if tool_name in _WORKSPACE_WRITE_TOOL_NAMES:
        return "workspace_write"
    if tool_name.startswith("canvas_") and tool_name not in {
        "canvas_get_state",
        "canvas_get_selection",
        "canvas_get_request_references",
    }:
        return "canvas"
    if tool_name in _TASK_MUTATION_TOOL_NAMES:
        return "task_manager"
    if tool_name in _SCHEDULE_MUTATION_TOOL_NAMES:
        return "schedule"
    if tool_name == "todo_write":
        return "turn_state"
    return None


def _metadata_list(metadata: dict[str, object] | None, key: str) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    value = metadata.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip().lower() for item in value if str(item).strip()]


def _metadata_dict(metadata: dict[str, object] | None, key: str) -> dict[str, object]:
    if not isinstance(metadata, dict):
        return {}
    value = metadata.get(key)
    return value if isinstance(value, dict) else {}


def _has_selected_skill(metadata: dict[str, object] | None, *needles: str) -> bool:
    selected = (
        _metadata_list(metadata, "selected_skill_ids")
        + _metadata_list(metadata, "required_skill_ids")
        + _metadata_list(metadata, "invoked_skills")
    )
    if not selected:
        return False
    normalized_needles = tuple(needle.lower() for needle in needles)
    return any(any(needle in skill_id for needle in normalized_needles) for skill_id in selected)


def _has_canvas_context(metadata: dict[str, object] | None) -> bool:
    canvas_request = _metadata_dict(metadata, "canvas_request")
    canvas_context = _metadata_dict(metadata, "canvas_context")
    return bool(canvas_request or canvas_context)


def _has_media_context(metadata: dict[str, object] | None) -> bool:
    canvas_request = _metadata_dict(metadata, "canvas_request")
    request_kind = str(canvas_request.get("kind") or "").lower()
    if request_kind in {"image_generation", "video_generation", "audio_generation", "music_generation"}:
        return True
    if _has_selected_skill(metadata, "image", "video", "media", "drama", "visual"):
        return True
    return False


def _has_schedule_context(metadata: dict[str, object] | None) -> bool:
    scheduled_run = _metadata_dict(metadata, "scheduled_run")
    if scheduled_run.get("scheduled_run_id"):
        return bool(scheduled_run.get("allow_schedule_management"))
    return _has_selected_skill(metadata, "automation", "schedule", "cron")


def _tool_schema_selected_for_context(tool_name: str, context: QueryContext) -> bool:
    metadata = context.tool_metadata
    if tool_name in CORE_TOOL_SCHEMA_NAMES:
        return True
    if tool_name.startswith("connector__"):
        return bool(_metadata_list(metadata, "selected_connector_ids"))
    if tool_name.startswith("canvas_"):
        return _has_canvas_context(metadata)
    if tool_name in MEDIA_TOOL_SCHEMA_NAMES:
        return _has_media_context(metadata)
    if tool_name in SCHEDULE_TOOL_SCHEMA_NAMES:
        return _has_schedule_context(metadata)
    if tool_name in TASK_TOOL_SCHEMA_NAMES:
        return _has_selected_skill(metadata, "agent", "task", "team", "project", "orchestrator")
    return True


def _tool_schemas_for_context(context: QueryContext) -> list[dict[str, Any]]:
    return [
        tool.to_api_schema()
        for tool in context.tool_registry.list_tools()
        if _tool_available_for_context(tool.name, context)
        and _tool_schema_selected_for_context(tool.name, context)
    ]


_TOOL_RATIONALE_FIELDS = ("rationale", "purpose", "thought")


@dataclass(frozen=True)
class _PreparedToolCall:
    tool_name: str
    tool_use_id: str
    tool_input: dict[str, Any]
    rationale: str | None
    display_name: str | None
    start_message: str | None


def _tool_input_fields(tool: BaseTool) -> set[str]:
    fields = getattr(tool.input_model, "model_fields", None)
    if isinstance(fields, dict):
        return set(fields)
    legacy_fields = getattr(tool.input_model, "__fields__", None)
    if isinstance(legacy_fields, dict):
        return set(legacy_fields)
    return set()


def _split_tool_display_context(
    tool: BaseTool | None,
    raw_input: dict[str, Any],
) -> tuple[dict[str, Any], str | None, str | None, str | None]:
    clean_input = dict(raw_input)
    if tool is None:
        return clean_input, None, None, None

    input_fields = _tool_input_fields(tool)
    rationale: str | None = None
    for field_name in _TOOL_RATIONALE_FIELDS:
        if field_name in input_fields:
            value = clean_input.get(field_name)
            if rationale is None and isinstance(value, str) and value.strip():
                rationale = value.strip()
            continue
        value = clean_input.pop(field_name, None)
        if rationale is None and isinstance(value, str) and value.strip():
            rationale = value.strip()

    display_label = tool.display_label() if callable(getattr(tool, "display_label", None)) else None
    start_message = tool.start_message() if callable(getattr(tool, "start_message", None)) else None
    return clean_input, rationale, display_label, start_message


def _stringify_ask_user_scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _normalize_ask_user_question_input(raw_input: dict[str, Any]) -> dict[str, Any]:
    clean_input = dict(raw_input)
    for key in ("question", "purpose"):
        normalized = _stringify_ask_user_scalar(clean_input.get(key))
        if normalized is not None:
            clean_input[key] = normalized

    questions = clean_input.get("questions")
    if not isinstance(questions, list):
        return clean_input

    normalized_questions: list[Any] = []
    for question in questions:
        if not isinstance(question, dict):
            normalized_questions.append(question)
            continue
        next_question = dict(question)
        for key in ("id", "question"):
            normalized = _stringify_ask_user_scalar(next_question.get(key))
            if normalized is not None:
                next_question[key] = normalized
        options = next_question.get("options")
        if isinstance(options, list):
            normalized_options: list[Any] = []
            for option in options:
                if not isinstance(option, dict):
                    normalized_options.append(option)
                    continue
                next_option = dict(option)
                for key in ("label", "value"):
                    normalized = _stringify_ask_user_scalar(next_option.get(key))
                    if normalized is not None:
                        next_option[key] = normalized
                normalized_options.append(next_option)
            next_question["options"] = normalized_options
        normalized_questions.append(next_question)
    clean_input["questions"] = normalized_questions
    return clean_input


def _prepare_tool_call(
    context: QueryContext,
    tool_call: Any,
    *,
    rationale_fallback: str | None = None,
) -> _PreparedToolCall:
    tool = context.tool_registry.get(tool_call.name)
    raw_input = tool_call.input if isinstance(tool_call.input, dict) else {}
    if tool_call.name == "ask_user_question":
        raw_input = _normalize_ask_user_question_input(raw_input)
    clean_input, rationale, display_name, start_message = _split_tool_display_context(tool, raw_input)
    if rationale is None and isinstance(rationale_fallback, str) and rationale_fallback.strip():
        rationale = rationale_fallback.strip()[:800]
    if tool is not None:
        tool_call.input = clean_input
    return _PreparedToolCall(
        tool_name=tool_call.name,
        tool_use_id=tool_call.id,
        tool_input=clean_input,
        rationale=rationale,
        display_name=display_name,
        start_message=start_message,
    )


def _clean_tool_input_for_execution(
    context: QueryContext,
    tool_name: str,
    tool_input: dict[str, object],
) -> dict[str, object]:
    if tool_name == "ask_user_question":
        return _normalize_ask_user_question_input(dict(tool_input))
    tool = context.tool_registry.get(tool_name)
    clean_input, _, _, _ = _split_tool_display_context(tool, dict(tool_input))
    return clean_input


def _extract_completion_token_limit(exc: Exception) -> int | None:
    """Parse provider errors such as "supports at most 128000 completion tokens"."""
    text = str(exc).lower().replace(",", "")
    patterns = (
        r"supports at most\s+(\d+)\s+completion tokens",
        r"at most\s+(\d+)\s+completion tokens",
        r"max(?:imum)?(?:_completion)?[_\s-]tokens.*?(?:<=|less than or equal to|at most)\s+(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return max(1, int(match.group(1)))
            except ValueError:
                return None
    return None


def _is_completion_token_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        ("max_tokens" in text or "max_completion_tokens" in text)
        and ("too large" in text or "at most" in text or "completion tokens" in text)
    )


class MaxTurnsExceeded(RuntimeError):
    """Raised when the agent exceeds the configured max_turns for one user prompt."""

    def __init__(self, max_turns: int) -> None:
        super().__init__(f"Exceeded maximum turn limit ({max_turns})")
        self.max_turns = max_turns


class QueryCancelled(RuntimeError):
    """Raised when a query cancellation token is tripped."""


@dataclass
class QueryContext:
    """Context shared across a query run."""

    api_client: SupportsStreamingMessages
    tool_registry: ToolRegistry
    permission_checker: PermissionChecker
    cwd: Path
    model: str
    system_prompt: str
    max_tokens: int
    effort: str | None = None
    context_window_tokens: int | None = None
    auto_compact_threshold_tokens: int | None = None
    permission_prompt: PermissionPrompt | None = None
    ask_user_prompt: AskUserPrompt | None = None
    max_turns: int | None = 200
    hook_executor: HookExecutor | None = None
    tool_metadata: dict[str, object] | None = None
    cancellation_token: CancellationToken | None = None


def _append_capped_unique(bucket: list[Any], value: Any, *, limit: int) -> None:
    if value in bucket:
        bucket.remove(value)
    bucket.append(value)
    if len(bucket) > limit:
        del bucket[:-limit]


def _task_focus_state(tool_metadata: dict[str, object] | None) -> dict[str, object]:
    if tool_metadata is None:
        return {}
    value = tool_metadata.setdefault(
        "task_focus_state",
        {
            "goal": "",
            "recent_goals": [],
            "active_artifacts": [],
            "verified_state": [],
            "next_step": "",
        },
    )
    if isinstance(value, dict):
        value.setdefault("goal", "")
        value.setdefault("recent_goals", [])
        value.setdefault("active_artifacts", [])
        value.setdefault("verified_state", [])
        value.setdefault("next_step", "")
        return value
    replacement = {
        "goal": "",
        "recent_goals": [],
        "active_artifacts": [],
        "verified_state": [],
        "next_step": "",
    }
    tool_metadata["task_focus_state"] = replacement
    return replacement


def _summarize_focus_text(text: str) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return ""
    return normalized[:240]


def remember_user_goal(
    tool_metadata: dict[str, object] | None,
    prompt: str,
) -> None:
    state = _task_focus_state(tool_metadata)
    summary = _summarize_focus_text(prompt)
    if not summary:
        return
    recent_goals = state.setdefault("recent_goals", [])
    if isinstance(recent_goals, list):
        _append_capped_unique(recent_goals, summary, limit=MAX_TRACKED_USER_GOALS)
    state["goal"] = summary


def _remember_active_artifact(
    tool_metadata: dict[str, object] | None,
    artifact: str,
) -> None:
    normalized = artifact.strip()
    if not normalized:
        return
    state = _task_focus_state(tool_metadata)
    artifacts = state.setdefault("active_artifacts", [])
    if isinstance(artifacts, list):
        _append_capped_unique(artifacts, normalized[:240], limit=MAX_TRACKED_ACTIVE_ARTIFACTS)


def _remember_verified_work(
    tool_metadata: dict[str, object] | None,
    entry: str,
) -> None:
    normalized = entry.strip()
    if not normalized:
        return
    bucket = _tool_metadata_bucket(tool_metadata, "recent_verified_work")
    _append_capped_unique(bucket, normalized[:320], limit=MAX_TRACKED_VERIFIED_WORK)
    state = _task_focus_state(tool_metadata)
    verified_state = state.setdefault("verified_state", [])
    if isinstance(verified_state, list):
        _append_capped_unique(verified_state, normalized[:320], limit=MAX_TRACKED_VERIFIED_WORK)


def _tool_metadata_bucket(
    tool_metadata: dict[str, object] | None,
    key: str,
) -> list[Any]:
    if tool_metadata is None:
        return []
    value = tool_metadata.setdefault(key, [])
    if isinstance(value, list):
        return value
    replacement: list[Any] = []
    tool_metadata[key] = replacement
    return replacement


def _remember_read_file(
    tool_metadata: dict[str, object] | None,
    *,
    path: str,
    offset: int,
    limit: int,
    output: str,
) -> None:
    bucket = _tool_metadata_bucket(tool_metadata, "read_file_state")
    preview_lines = [line.strip() for line in output.splitlines()[:6] if line.strip()]
    entry = {
        "path": path,
        "span": f"lines {offset + 1}-{offset + limit}",
        "preview": " | ".join(preview_lines)[:320],
        "timestamp": time.time(),
    }
    if isinstance(bucket, list):
        bucket[:] = [
            existing
            for existing in bucket
            if not isinstance(existing, dict) or str(existing.get("path") or "") != path
        ]
        bucket.append(entry)
        if len(bucket) > MAX_TRACKED_READ_FILES:
            del bucket[:-MAX_TRACKED_READ_FILES]


def _remember_skill_invocation(
    tool_metadata: dict[str, object] | None,
    *,
    skill_name: str,
) -> None:
    bucket = _tool_metadata_bucket(tool_metadata, "invoked_skills")
    normalized = skill_name.strip()
    if not normalized:
        return
    if normalized in bucket:
        bucket.remove(normalized)
    bucket.append(normalized)
    if len(bucket) > MAX_TRACKED_SKILLS:
        del bucket[:-MAX_TRACKED_SKILLS]


def _remember_async_agent_activity(
    tool_metadata: dict[str, object] | None,
    *,
    tool_name: str,
    tool_input: dict[str, object],
    output: str,
) -> None:
    bucket = _tool_metadata_bucket(tool_metadata, "async_agent_state")
    if tool_name == "agent":
        description = str(tool_input.get("description") or tool_input.get("prompt") or "").strip()
        summary = f"Spawned async agent. {description}".strip()
        if output.strip():
            summary = f"{summary} [{output.strip()[:180]}]".strip()
    elif tool_name == "send_message":
        target = str(tool_input.get("task_id") or "").strip()
        summary = f"Sent follow-up message to async agent {target}".strip()
    else:
        summary = output.strip()[:220] or f"Async agent activity via {tool_name}"
    bucket.append(summary)
    if len(bucket) > MAX_TRACKED_ASYNC_AGENT_EVENTS:
        del bucket[:-MAX_TRACKED_ASYNC_AGENT_EVENTS]


def _parse_spawned_agent_identity(
    output: str,
    metadata: dict[str, object] | None = None,
) -> tuple[str, str] | None:
    if isinstance(metadata, dict):
        agent_id = str(metadata.get("agent_id") or "").strip()
        task_id = str(metadata.get("task_id") or "").strip()
        if agent_id and task_id:
            return agent_id, task_id
    match = re.search(r"Spawned agent (.+?) \(task_id=(\S+?)(?:[,)]|$)", output.strip())
    if match is None:
        return None
    return match.group(1).strip(), match.group(2).strip()


def _remember_async_agent_task(
    tool_metadata: dict[str, object] | None,
    *,
    tool_name: str,
    tool_input: dict[str, object],
    output: str,
    result_metadata: dict[str, object] | None = None,
) -> None:
    if tool_name != "agent":
        return
    identity = _parse_spawned_agent_identity(output, result_metadata)
    if identity is None:
        return
    agent_id, task_id = identity
    bucket = _tool_metadata_bucket(tool_metadata, "async_agent_tasks")
    description = str(tool_input.get("description") or tool_input.get("prompt") or "").strip()
    entry = {
        "agent_id": agent_id,
        "task_id": task_id,
        "description": description[:240],
        "status": "spawned",
        "notification_sent": False,
        "spawned_at": time.time(),
    }
    bucket[:] = [
        existing
        for existing in bucket
        if not isinstance(existing, dict) or str(existing.get("task_id") or "") != task_id
    ]
    bucket.append(entry)
    if len(bucket) > MAX_TRACKED_ASYNC_AGENT_TASKS:
        del bucket[:-MAX_TRACKED_ASYNC_AGENT_TASKS]


def _remember_work_log(
    tool_metadata: dict[str, object] | None,
    *,
    entry: str,
) -> None:
    bucket = _tool_metadata_bucket(tool_metadata, "recent_work_log")
    normalized = entry.strip()
    if not normalized:
        return
    bucket.append(normalized[:320])
    if len(bucket) > MAX_TRACKED_WORK_LOG:
        del bucket[:-MAX_TRACKED_WORK_LOG]


def _update_plan_mode(tool_metadata: dict[str, object] | None, mode: str) -> None:
    if tool_metadata is None:
        return
    tool_metadata["permission_mode"] = mode


def _record_tool_carryover(
    context: QueryContext,
    *,
    tool_name: str,
    tool_input: dict[str, object],
    tool_output: str,
    tool_result_metadata: dict[str, object] | None,
    is_error: bool,
    resolved_file_path: str | None,
) -> None:
    if is_error:
        return
    if resolved_file_path is not None:
        _remember_active_artifact(context.tool_metadata, resolved_file_path)
    if tool_name == "read_file" and resolved_file_path is not None:
        offset = int(tool_input.get("offset") or 0)
        limit = int(tool_input.get("limit") or 200)
        _remember_read_file(
            context.tool_metadata,
            path=resolved_file_path,
            offset=offset,
            limit=limit,
            output=tool_output,
        )
        _remember_verified_work(
            context.tool_metadata,
            f"Inspected file {resolved_file_path} (lines {offset + 1}-{offset + limit})",
        )
    elif tool_name == "skill":
        _remember_skill_invocation(
            context.tool_metadata,
            skill_name=str(tool_input.get("name") or ""),
        )
        skill_name = str(tool_input.get("name") or "").strip()
        if skill_name:
            _remember_active_artifact(context.tool_metadata, f"skill:{skill_name}")
            _remember_verified_work(context.tool_metadata, f"Loaded skill {skill_name}")
    elif tool_name in {"agent", "send_message"}:
        _remember_async_agent_activity(
            context.tool_metadata,
            tool_name=tool_name,
            tool_input=tool_input,
            output=tool_output,
        )
        _remember_async_agent_task(
            context.tool_metadata,
            tool_name=tool_name,
            tool_input=tool_input,
            output=tool_output,
            result_metadata=tool_result_metadata,
        )
        description = str(tool_input.get("description") or tool_input.get("prompt") or tool_name).strip()
        _remember_verified_work(
            context.tool_metadata,
            f"Confirmed async-agent activity via {tool_name}: {description[:180]}",
        )
    elif tool_name == "enter_plan_mode":
        _update_plan_mode(context.tool_metadata, "plan")
    elif tool_name == "exit_plan_mode":
        _update_plan_mode(context.tool_metadata, "default")
    elif tool_name == "web_fetch":
        url = str(tool_input.get("url") or "").strip()
        if url:
            _remember_active_artifact(context.tool_metadata, url)
            _remember_verified_work(context.tool_metadata, f"Fetched remote content from {url}")
    elif tool_name == "web_search":
        query = str(tool_input.get("query") or "").strip()
        if query:
            _remember_verified_work(context.tool_metadata, f"Ran web search for {query[:180]}")
    elif tool_name == "glob":
        pattern = str(tool_input.get("pattern") or "").strip()
        if pattern:
            _remember_verified_work(context.tool_metadata, f"Expanded glob pattern {pattern[:180]}")
    elif tool_name == "grep":
        pattern = str(tool_input.get("pattern") or "").strip()
        if pattern:
            _remember_verified_work(context.tool_metadata, f"Checked repository matches for grep pattern {pattern[:180]}")
    elif tool_name == "bash":
        command = str(tool_input.get("command") or "").strip()
        summary = tool_output.splitlines()[0].strip() if tool_output.strip() else "no output"
        _remember_verified_work(
            context.tool_metadata,
            f"Ran bash command {command[:160]} [{summary[:120]}]",
        )
    if tool_name == "read_file" and resolved_file_path is not None:
        _remember_work_log(
            context.tool_metadata,
            entry=f"Read file {resolved_file_path}",
        )
    elif tool_name == "bash":
        command = str(tool_input.get("command") or "").strip()
        summary = tool_output.splitlines()[0].strip() if tool_output.strip() else "no output"
        _remember_work_log(
            context.tool_metadata,
            entry=f"Ran bash: {command[:160]} [{summary[:120]}]",
        )
    elif tool_name == "grep":
        pattern = str(tool_input.get("pattern") or "").strip()
        _remember_work_log(
            context.tool_metadata,
            entry=f"Searched with grep pattern={pattern[:160]}",
        )
    elif tool_name == "skill":
        _remember_work_log(
            context.tool_metadata,
            entry=f"Loaded skill {str(tool_input.get('name') or '').strip()}",
        )
    elif tool_name in {"agent", "send_message"}:
        _remember_work_log(
            context.tool_metadata,
            entry=f"Async agent action via {tool_name}",
        )
    elif tool_name == "enter_plan_mode":
        _remember_work_log(context.tool_metadata, entry="Entered plan mode")
    elif tool_name == "exit_plan_mode":
        _remember_work_log(context.tool_metadata, entry="Exited plan mode")


def _tool_artifact_dir(workspace_dir: Path | None = None) -> Path:
    if workspace_dir is not None:
        try:
            artifact_dir = workspace_dir.resolve() / ".openharness" / "tool_artifacts"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            return artifact_dir
        except OSError:
            pass
    artifact_dir = get_data_dir() / "tool_artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def _safe_tool_artifact_name(tool_name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", tool_name.strip())
    return (normalized or "tool")[:80]


def _offload_tool_output_if_needed(
    *,
    tool_name: str,
    tool_use_id: str,
    output: str,
    workspace_dir: Path | None = None,
    expose_artifact_path: bool = True,
) -> tuple[str, Path | None]:
    inline_limit = tool_output_inline_chars()
    if len(output) <= inline_limit:
        return output, None

    artifact_path = (
        _tool_artifact_dir(workspace_dir)
        / f"{time.strftime('%Y%m%d-%H%M%S')}-{_safe_tool_artifact_name(tool_name)}-{uuid4().hex[:12]}.txt"
    )
    artifact_path.write_text(output, encoding="utf-8", errors="replace")
    preview = output[:tool_output_preview_chars()]
    omitted = max(0, len(output) - len(preview))
    inline = (
        "[Tool output truncated]\n"
        f"Tool: {tool_name}\n"
        f"Tool use id: {tool_use_id}\n"
        f"Original size: {len(output)} chars\n"
        f"Inline preview: first {len(preview)} chars"
    )
    if expose_artifact_path:
        inline = inline.replace(
            f"Inline preview: first {len(preview)} chars",
            f"Full output saved to: {artifact_path}\nInline preview: first {len(preview)} chars",
        )
    if omitted:
        inline += f" ({omitted} chars omitted)"
    if preview:
        inline += f"\n\nPreview:\n{preview}"
    return inline, artifact_path


async def run_query(
    context: QueryContext,
    messages: list[ConversationMessage],
) -> AsyncIterator[tuple[StreamEvent, UsageSnapshot | None]]:
    """Run the conversation loop until the model stops requesting tools.

    Auto-compaction is checked at the start of each turn.  When the
    estimated token count exceeds the model's auto-compact threshold,
    the engine first tries a cheap microcompact (clearing old tool result
    content) and, if that is not enough, performs a full LLM-based
    summarization of older messages.
    """
    from openharness.services.compact import (
        AutoCompactState,
        auto_compact_if_needed,
    )

    compact_state = AutoCompactState()
    reactive_compact_attempted = False
    last_compaction_result: tuple[list[ConversationMessage], bool] = (messages, False)
    effective_max_tokens = _bounded_completion_tokens(
        context.max_tokens,
        context.context_window_tokens,
    )
    reported_token_clamp = False

    async def _stream_compaction(
        *,
        trigger: str,
        force: bool = False,
    ) -> AsyncIterator[tuple[StreamEvent, UsageSnapshot | None]]:
        nonlocal last_compaction_result
        progress_queue: asyncio.Queue[CompactProgressEvent] = asyncio.Queue()

        async def _progress(event: CompactProgressEvent) -> None:
            await progress_queue.put(event)

        task = asyncio.create_task(
            auto_compact_if_needed(
                messages,
                api_client=context.api_client,
                model=context.model,
                system_prompt=context.system_prompt,
                state=compact_state,
                progress_callback=_progress,
                force=force,
                trigger=trigger,
                hook_executor=context.hook_executor,
                carryover_metadata=context.tool_metadata,
                context_window_tokens=context.context_window_tokens,
                auto_compact_threshold_tokens=context.auto_compact_threshold_tokens,
            )
        )
        while True:
            try:
                event = await asyncio.wait_for(progress_queue.get(), timeout=0.05)
                yield event, None
            except asyncio.TimeoutError:
                if task.done():
                    break
                continue
        while not progress_queue.empty():
            yield progress_queue.get_nowait(), None
        last_compaction_result = await task
        return

    turn_count = 0
    while context.max_turns is None or turn_count < context.max_turns:
        turn_count += 1
        turn_trace = _RunTimingTrace(turn_id=f"turn_{uuid4().hex[:12]}", turn_index=turn_count)
        yield _progress_event(
            "turn_start",
            "",
            status="info",
            workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
            metadata={"message_count": len(messages)},
            timing=turn_trace,
        ), None
        if _query_cancelled(context):
            yield _progress_event(
                "turn_aborted",
                "",
                status="error",
                workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                metadata={"reason": _query_cancel_reason(context)},
                timing=turn_trace,
            ), None
            return
        if effective_max_tokens != context.max_tokens and not reported_token_clamp:
            reported_token_clamp = True
            yield StatusEvent(
                message=(
                    "Requested max_tokens="
                    f"{context.max_tokens} exceeds the safe per-request output cap; "
                    f"using {effective_max_tokens}."
                )
            ), None
        # --- auto-compact check before calling the model ---------------
        async for event, usage in _stream_compaction(trigger="auto"):
            yield event, usage
        compacted_messages, was_compacted = last_compaction_result
        if compacted_messages is not messages:
            messages[:] = compacted_messages
        # ---------------------------------------------------------------

        model_result: ModelTurnComplete | None = None
        try:
            async for item in stream_model_turn(
                context=context,
                messages=messages,
                effective_max_tokens=effective_max_tokens,
                tool_schemas=_tool_schemas_for_context(context),
                heartbeat_seconds=AGENT_PROGRESS_HEARTBEAT_SECONDS,
                timing=turn_trace,
            ):
                if isinstance(item, ModelTurnComplete):
                    model_result = item
                    continue
                yield item
        except Exception as exc:
            error_msg = str(exc)
            failure_detail = _safe_request_failure_detail(exc)
            if _is_completion_token_limit_error(exc):
                supported_limit = _extract_completion_token_limit(exc)
                if supported_limit is not None and effective_max_tokens > supported_limit:
                    previous_max_tokens = effective_max_tokens
                    effective_max_tokens = supported_limit
                    yield StatusEvent(
                        message=(
                            f"Model rejected max_tokens={previous_max_tokens}; "
                            f"retrying with provider limit {effective_max_tokens}."
                        )
                    ), None
                    turn_count = max(0, turn_count - 1)
                    continue
            if not reactive_compact_attempted and _is_prompt_too_long_error(exc):
                reactive_compact_attempted = True
                yield StatusEvent(message=REACTIVE_COMPACT_STATUS_MESSAGE), None
                async for event, usage in _stream_compaction(trigger="reactive", force=True):
                    yield event, usage
                compacted_messages, was_compacted = last_compaction_result
                if compacted_messages is not messages:
                    messages[:] = compacted_messages
                if was_compacted:
                    continue
            if "connect" in error_msg.lower() or "timeout" in error_msg.lower() or "network" in error_msg.lower():
                yield ErrorEvent(
                    message=f"Network error: {error_msg}. Check your internet connection and try again.",
                    detail=failure_detail,
                ), None
            else:
                yield ErrorEvent(message=f"API error: {error_msg}", detail=failure_detail), None
            turn_metadata: dict[str, Any] = {"reason": error_msg, "stage": "model_request"}
            if failure_detail:
                turn_metadata["provider_error_detail"] = failure_detail
            yield _progress_event(
                "turn_aborted",
                "",
                status="error",
                workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                metadata=turn_metadata,
                timing=turn_trace,
            ), None
            return

        if model_result is None:
            if _query_cancelled(context):
                return
            raise RuntimeError("Model stream finished without a final message")
        final_message = model_result.message
        usage = model_result.usage

        
        coordinator_context_message: ConversationMessage | None = None
        
        # === 升级版：多格式全兼容提取文本 ===
        sys_prompt = context.system_prompt
        if isinstance(sys_prompt, list):
            extracted_prompts = []
            for item in sys_prompt:
                if isinstance(item, str):
                    extracted_prompts.append(item)
                elif isinstance(item, dict):
                    # 兼容不同大模型客户端常见的字典键名：text 或 content
                    text_val = item.get("text") or item.get("content") or ""
                    if text_val:
                        extracted_prompts.append(text_val)
            sys_prompt = "\n".join(extracted_prompts)
        elif isinstance(sys_prompt, dict):
            sys_prompt = sys_prompt.get("text") or sys_prompt.get("content") or ""
        # ==================================
            
        if sys_prompt.startswith("You are a **coordinator**."):
            if messages and messages[-1].role == "user" and messages[-1].text.startswith("# Coordinator User Context"):
                coordinator_context_message = messages.pop()

        if final_message.role == "assistant" and final_message.is_effectively_empty():
            log.warning("dropping empty assistant message from provider response")
            yield ErrorEvent(
                message=(
                    "Model returned an empty assistant message. "
                    "The turn was ignored to keep the session healthy."
                )
            ), usage
            yield _progress_event(
                "turn_aborted",
                "",
                status="error",
                workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                metadata={"reason": "empty_assistant_message"},
                timing=turn_trace,
            ), None
            return

        if not final_message.tool_uses:
            yield _progress_event(
                "turn_complete",
                "",
                status="success",
                workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                metadata={"tool_call_count": 0, "usage": usage.model_dump()},
                timing=turn_trace,
            ), None

        messages.append(final_message)
        yield AssistantTurnComplete(message=final_message, usage=usage), usage

        if coordinator_context_message is not None:
            messages.append(coordinator_context_message)

        if not final_message.tool_uses:
            if context.hook_executor is not None:
                await context.hook_executor.execute(
                    HookEvent.STOP,
                    {
                        "event": HookEvent.STOP.value,
                        "stop_reason": "tool_uses_empty",
                    },
                )
            return

        tool_calls = final_message.tool_uses
        tool_rationale_fallback = final_message.text.strip()
        if _query_cancelled(context):
            yield _progress_event(
                "turn_aborted",
                "",
                status="error",
                workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                metadata={"reason": _query_cancel_reason(context), "stage": "before_tools"},
                timing=turn_trace,
            ), None
            return

        if len(tool_calls) == 1:
            # Single tool: sequential (stream events immediately)
            tc = tool_calls[0]
            prepared = _prepare_tool_call(context, tc, rationale_fallback=tool_rationale_fallback)
            result: ToolResultBlock | None = None
            yield ToolExecutionStarted(
                tool_name=prepared.tool_name,
                tool_input=prepared.tool_input,
                tool_use_id=prepared.tool_use_id,
                rationale=prepared.rationale,
                display_name=prepared.display_name,
                start_message=prepared.start_message,
            ), None
            yield _progress_event(
                "tool_start",
                prepared.start_message or f"正在执行工具 {prepared.tool_name}...",
                tool_name=prepared.tool_name,
                tool_use_id=prepared.tool_use_id,
                workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                metadata={
                    key: value
                    for key, value in {
                        "rationale": prepared.rationale,
                        "display_name": prepared.display_name,
                    }.items()
                    if value
                },
                timing=turn_trace,
            ), None
            try:
                async for progress_event, result in _run_tool_with_progress(
                    context,
                    prepared.tool_name,
                    prepared.tool_use_id,
                    prepared.tool_input,
                    timing=turn_trace,
                ):
                    if progress_event is not None:
                        yield progress_event, None
            except AskUserQuestionPaused:
                raise
            except QueryCancelled as exc:
                yield _progress_event(
                    "turn_aborted",
                    "",
                    status="error",
                    workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                    metadata={"reason": str(exc) or _query_cancel_reason(context), "stage": "tool_execution"},
                    timing=turn_trace,
                ), None
                return
            except Exception as exc:
                log.exception("tool execution raised: name=%s id=%s", prepared.tool_name, prepared.tool_use_id)
                result = ToolResultBlock(
                    tool_use_id=prepared.tool_use_id,
                    content=f"Tool {prepared.tool_name} failed: {type(exc).__name__}: {exc}",
                    is_error=True,
                )
            if result is None:
                result = ToolResultBlock(
                    tool_use_id=prepared.tool_use_id,
                    content=f"Tool {prepared.tool_name} failed: missing execution result",
                    is_error=True,
                )
            yield ToolExecutionCompleted(
                tool_name=prepared.tool_name,
                output=result.content,
                is_error=result.is_error,
                metadata=result.result_metadata,
                tool_use_id=prepared.tool_use_id,
            ), None
            yield _progress_event(
                "tool_complete",
                f"工具 {prepared.tool_name} 执行{'失败' if result.is_error else '完成'}",
                status="error" if result.is_error else "success",
                tool_name=prepared.tool_name,
                tool_use_id=prepared.tool_use_id,
                workspace=str((result.result_metadata or {}).get("workspace") or (context.tool_metadata or {}).get("workspace_backend") or ""),
                metadata=result.result_metadata,
                timing=turn_trace,
            ), None
            tool_results = [result]
        else:
            # Multiple tools: execute concurrently, emit events after
            prepared_calls = [
                _prepare_tool_call(context, tc, rationale_fallback=tool_rationale_fallback)
                for tc in tool_calls
            ]
            for prepared in prepared_calls:
                yield ToolExecutionStarted(
                    tool_name=prepared.tool_name,
                    tool_input=prepared.tool_input,
                    tool_use_id=prepared.tool_use_id,
                    rationale=prepared.rationale,
                    display_name=prepared.display_name,
                    start_message=prepared.start_message,
                ), None
                yield _progress_event(
                    "tool_start",
                    prepared.start_message or f"正在执行工具 {prepared.tool_name}...",
                    tool_name=prepared.tool_name,
                    tool_use_id=prepared.tool_use_id,
                    workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                    metadata={
                        key: value
                        for key, value in {
                            "rationale": prepared.rationale,
                            "display_name": prepared.display_name,
                        }.items()
                        if value
                    },
                    timing=turn_trace,
                ), None

            result_queue: asyncio.Queue[tuple[_PreparedToolCall, AgentProgressEvent | None, ToolResultBlock | BaseException | None]] = asyncio.Queue()
            execution_group_locks: dict[str, asyncio.Lock] = {}

            async def _run(prepared: _PreparedToolCall):
                group = _tool_execution_group(context, prepared.tool_name)
                queued_at = time.monotonic()
                try:
                    lock = execution_group_locks.setdefault(group, asyncio.Lock()) if group else None
                    if lock is None:
                        async for progress_event, result in _run_tool_with_progress(
                            context,
                            prepared.tool_name,
                            prepared.tool_use_id,
                            prepared.tool_input,
                            timing=turn_trace,
                        ):
                            await result_queue.put((prepared, progress_event, result))
                    else:
                        async with lock:
                            queued_ms = _elapsed_ms(queued_at)
                            await result_queue.put(
                                (
                                    prepared,
                                    _progress_event(
                                        "tool_dispatch",
                                        "",
                                        status="info",
                                        tool_name=prepared.tool_name,
                                        tool_use_id=prepared.tool_use_id,
                                        workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                                        metadata={"execution_group": group, "queued_ms": queued_ms},
                                        timing=turn_trace,
                                    ),
                                    None,
                                )
                            )
                            async for progress_event, result in _run_tool_with_progress(
                                context,
                                prepared.tool_name,
                                prepared.tool_use_id,
                                prepared.tool_input,
                                timing=turn_trace,
                            ):
                                await result_queue.put((prepared, progress_event, result))
                except BaseException as exc:
                    await result_queue.put((prepared, None, exc))

            tasks = [asyncio.create_task(_run(prepared)) for prepared in prepared_calls]
            raw_results_by_id: dict[str, ToolResultBlock | BaseException] = {}
            while len(raw_results_by_id) < len(tool_calls):
                prepared, progress_event, result = await result_queue.get()
                if progress_event is not None:
                    yield progress_event, None
                if result is not None:
                    if isinstance(result, QueryCancelled):
                        for running_task in tasks:
                            if not running_task.done():
                                running_task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                        yield _progress_event(
                            "turn_aborted",
                            "",
                            status="error",
                            workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                            metadata={"reason": str(result) or _query_cancel_reason(context), "stage": "tool_execution"},
                            timing=turn_trace,
                        ), None
                        return
                    raw_results_by_id[prepared.tool_use_id] = result

            await asyncio.gather(*tasks, return_exceptions=True)
            cancellation = next(
                (result for result in raw_results_by_id.values() if isinstance(result, QueryCancelled)),
                None,
            )
            if cancellation is not None:
                yield _progress_event(
                    "turn_aborted",
                    "",
                    status="error",
                    workspace=str((context.tool_metadata or {}).get("workspace_backend") or ""),
                    metadata={"reason": str(cancellation) or _query_cancel_reason(context), "stage": "tool_execution"},
                    timing=turn_trace,
                ), None
                return
            tool_results = []
            for prepared in prepared_calls:
                result = raw_results_by_id.get(prepared.tool_use_id)
                if isinstance(result, AskUserQuestionPaused):
                    raise result
                if isinstance(result, BaseException):
                    log.exception(
                        "tool execution raised: name=%s id=%s",
                        prepared.tool_name,
                        prepared.tool_use_id,
                        exc_info=result,
                    )
                    result = ToolResultBlock(
                        tool_use_id=prepared.tool_use_id,
                        content=f"Tool {prepared.tool_name} failed: {type(result).__name__}: {result}",
                        is_error=True,
                    )
                if result is None:
                    result = ToolResultBlock(
                        tool_use_id=prepared.tool_use_id,
                        content=f"Tool {prepared.tool_name} failed: missing execution result",
                        is_error=True,
                    )
                tool_results.append(result)

            for prepared, result in zip(prepared_calls, tool_results):
                yield ToolExecutionCompleted(
                    tool_name=prepared.tool_name,
                    output=result.content,
                    is_error=result.is_error,
                    metadata=result.result_metadata,
                    tool_use_id=prepared.tool_use_id,
                ), None
                yield _progress_event(
                    "tool_complete",
                    f"工具 {prepared.tool_name} 执行{'失败' if result.is_error else '完成'}",
                    status="error" if result.is_error else "success",
                    tool_name=prepared.tool_name,
                    tool_use_id=prepared.tool_use_id,
                    workspace=str((result.result_metadata or {}).get("workspace") or (context.tool_metadata or {}).get("workspace_backend") or ""),
                    metadata=result.result_metadata,
                    timing=turn_trace,
                ), None

        messages.append(ConversationMessage(role="user", content=tool_results))

    if context.max_turns is not None:
        raise MaxTurnsExceeded(context.max_turns)
    raise RuntimeError("Query loop exited without a max_turns limit or final response")


async def _execute_tool_call(
    context: QueryContext,
    tool_name: str,
    tool_use_id: str,
    tool_input: dict[str, object],
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    *,
    allow_media_split: bool = True,
) -> ToolResultBlock:
    tool_input = _clean_tool_input_for_execution(context, tool_name, tool_input)
    if allow_media_split and _is_media_generation_tool(tool_name):
        output_count = _media_output_count(tool_name, tool_input)
        if output_count > 1:
            return await _execute_media_generation_batch(
                context,
                tool_name,
                tool_use_id,
                tool_input,
                output_count=output_count,
                progress_callback=progress_callback,
            )

    if context.hook_executor is not None:
        pre_hooks = await context.hook_executor.execute(
            HookEvent.PRE_TOOL_USE,
            {"tool_name": tool_name, "tool_input": tool_input, "event": HookEvent.PRE_TOOL_USE.value},
        )
        if pre_hooks.blocked:
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=pre_hooks.reason or f"pre_tool_use hook blocked {tool_name}",
                is_error=True,
            )

    log.debug("tool_call start: %s id=%s", tool_name, tool_use_id)

    tool = context.tool_registry.get(tool_name)
    if tool is None:
        log.warning("unknown tool: %s", tool_name)
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=f"Unknown tool: {tool_name}",
            is_error=True,
        )

    if not _tool_available_for_context(tool_name, context):
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=_tool_unavailable_message(tool_name, context),
            is_error=True,
        )

    try:
        parsed_input = tool.input_model.model_validate(tool_input)
    except ValidationError as exc:
        log.warning("invalid input for %s: %s", tool_name, exc)
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=_format_tool_validation_error(tool_name, exc),
            is_error=True,
            result_metadata={"error_code": "invalid_canonical_request", "tool_name": tool_name},
        )
    except Exception as exc:
        log.warning("invalid input for %s: %s", tool_name, exc)
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=f"invalid_canonical_request: {tool_name} input could not be validated.",
            is_error=True,
            result_metadata={"error_code": "invalid_canonical_request", "tool_name": tool_name},
        )

    # Normalize common tool inputs before permission checks so path rules apply
    # consistently across built-in tools that use `file_path`, `path`, or
    # directory-scoped roots such as `glob`/`grep`.
    _file_path = _resolve_permission_file_path(context.cwd, tool_input, parsed_input)
    _command = _extract_permission_command(tool_input, parsed_input)
    log.debug("permission check: %s read_only=%s path=%s cmd=%s",
              tool_name, tool.is_read_only(parsed_input), _file_path, _command and _command[:80])
    decision = context.permission_checker.evaluate(
        tool_name,
        is_read_only=tool.is_read_only(parsed_input),
        file_path=_file_path,
        command=_command,
    )
    if not decision.allowed:
        if decision.requires_confirmation and context.permission_prompt is not None:
            log.debug("permission prompt for %s: %s", tool_name, decision.reason)
            if context.hook_executor is not None:
                await context.hook_executor.execute(
                    HookEvent.NOTIFICATION,
                    {
                        "event": HookEvent.NOTIFICATION.value,
                        "notification_type": "permission_prompt",
                        "tool_name": tool_name,
                        "reason": decision.reason,
                    },
                )
            confirmed = await context.permission_prompt(tool_name, decision.reason)
            if not confirmed:
                log.debug("permission denied by user for %s", tool_name)
                return ToolResultBlock(
                    tool_use_id=tool_use_id,
                    content=decision.reason or f"Permission denied for {tool_name}",
                    is_error=True,
                )
        else:
            log.debug("permission blocked for %s: %s", tool_name, decision.reason)
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=decision.reason or f"Permission denied for {tool_name}",
                is_error=True,
            )

    if _query_cancelled(context):
        raise QueryCancelled(_query_cancel_reason(context))

    tool_metadata = context.tool_metadata or {}
    existing_reservation = tool_metadata.get("media_billing_reservation")
    media_reservation: dict[str, Any] | None = existing_reservation if isinstance(existing_reservation, dict) else None
    media_billing_disabled = bool(tool_metadata.get("media_billing_disabled"))
    media_billing_defer_failure_release = bool(tool_metadata.get("media_billing_defer_failure_release"))
    hook = tool_metadata.get("hook")
    if _is_media_generation_tool(tool_name) and not media_billing_disabled and hook is not None and hasattr(hook, "reserve_media_tool_usage"):
        try:
            media_reservation = hook.reserve_media_tool_usage(tool_name, tool_input, tool_use_id, {})
        except Exception as exc:
            log.warning("media usage reservation failed: name=%s id=%s error=%s", tool_name, tool_use_id, exc)
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=f"Media billing reservation failed: {exc}",
                is_error=True,
            )
        if str((media_reservation or {}).get("billing_status") or "") == "recorded":
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content="Media generation was already recorded for this tool_use_id; skipping duplicate provider call.",
                is_error=False,
                result_metadata={
                    "media_billing_status": "recorded",
                    "media_billing_resource_log_id": media_reservation.get("resource_log_id"),
                    "media_billing_request_id": media_reservation.get("billing_request_id"),
                },
            )

    log.debug("executing %s ...", tool_name)
    t0 = time.monotonic()
    media_execution_slot: dict[str, Any] | None = None
    try:
        if (
            _is_media_generation_tool(tool_name)
            and hook is not None
            and hasattr(hook, "acquire_media_execution_slot")
            and not hasattr(hook, "get_media_gateway_runtime_candidate")
        ):
            try:
                media_execution_slot = await _maybe_await(
                    hook.acquire_media_execution_slot(tool_name, tool_input, tool_use_id)
                )
            except Exception as exc:
                log.warning("media execution slot acquisition failed: name=%s id=%s error=%s", tool_name, tool_use_id, exc)
                release_metadata: dict[str, Any] = {}
                if media_reservation and hook is not None and hasattr(hook, "release_media_tool_usage"):
                    try:
                        released = hook.release_media_tool_usage(
                            media_reservation,
                            reason="media_execution_slot_failed",
                            tool_metadata={"error": str(exc)},
                        )
                        if isinstance(released, dict):
                            release_metadata.update(released)
                    except Exception as release_exc:
                        log.exception("media usage reservation release failed after slot acquisition error: name=%s id=%s", tool_name, tool_use_id)
                        return ToolResultBlock(
                            tool_use_id=tool_use_id,
                            content=f"Media billing release failed after concurrency limit error: {type(release_exc).__name__}: {release_exc}",
                            is_error=True,
                        )
                return ToolResultBlock(
                    tool_use_id=tool_use_id,
                    content=f"Media execution concurrency limit failed: {type(exc).__name__}: {exc}",
                    is_error=True,
                    result_metadata=release_metadata,
                )
        result = await tool.execute(
            parsed_input,
            ToolExecutionContext(
                cwd=_concrete_path(context.cwd),
                metadata={
                    "tool_registry": context.tool_registry,
                    "ask_user_prompt": context.ask_user_prompt,
                    "tool_name": tool_name,
                    "tool_use_id": tool_use_id,
                    **tool_metadata,
                    "media_billing_reservation": media_reservation,
                },
                hook_executor=context.hook_executor,
                progress_callback=progress_callback,
                cancellation_token=context.cancellation_token,
            ),
        )
    except (QueryCancelled, asyncio.CancelledError):
        if media_reservation and hook is not None and hasattr(hook, "release_media_tool_usage"):
            try:
                await _maybe_await(
                    hook.release_media_tool_usage(
                        media_reservation,
                        reason="tool_cancelled",
                        tool_metadata={"cancel_reason": _query_cancel_reason(context)},
                    )
                )
            except Exception:
                log.exception("media usage reservation release failed after cancellation: name=%s id=%s", tool_name, tool_use_id)
        raise
    finally:
        if media_execution_slot and hook is not None and hasattr(hook, "release_media_execution_slot"):
            try:
                await _maybe_await(hook.release_media_execution_slot(media_execution_slot))
            except Exception:
                log.debug("media execution slot release failed", exc_info=True)
    elapsed = time.monotonic() - t0
    log.debug("executed %s in %.2fs err=%s output_len=%d",
              tool_name, elapsed, result.is_error, len(result.output or ""))
    result_metadata = dict(result.metadata or {})
    if media_reservation and hook is not None and not media_billing_defer_failure_release and not result_metadata.get("media_billing_status"):
        if result.is_error:
            try:
                result_metadata.update(
                    hook.release_media_tool_usage(
                        media_reservation,
                        reason="media_tool_failed",
                        tool_metadata={"error": result.output},
                    )
                )
            except Exception as exc:
                log.exception("media usage reservation release failed: name=%s id=%s", tool_name, tool_use_id)
                result = ToolResult(
                    output=f"Media billing release failed after provider error: {type(exc).__name__}: {exc}",
                    is_error=True,
                    metadata=result_metadata,
                )
        else:
            try:
                result_metadata.update(hook.commit_media_tool_usage(media_reservation, result_metadata))
            except Exception as exc:
                log.exception("media usage reservation commit failed: name=%s id=%s", tool_name, tool_use_id)
                result = ToolResult(
                    output=f"Media billing commit failed after provider success: {type(exc).__name__}: {exc}",
                    is_error=True,
                    metadata=result_metadata,
                )
    inline_output, artifact_path = _offload_tool_output_if_needed(
        tool_name=tool_name,
        tool_use_id=tool_use_id,
        output=result.output,
        workspace_dir=_concrete_path(context.cwd),
        expose_artifact_path=str((context.tool_metadata or {}).get("workspace_backend") or "").lower() != "e2b",
    )
    if artifact_path is not None:
        _remember_active_artifact(context.tool_metadata, str(artifact_path))
    tool_result = ToolResultBlock(
        tool_use_id=tool_use_id,
        content=inline_output,
        is_error=result.is_error,
        result_metadata=result_metadata,
    )
    _record_tool_carryover(
        context,
        tool_name=tool_name,
        tool_input=tool_input,
        tool_output=tool_result.content,
        tool_result_metadata=result.metadata,
        is_error=tool_result.is_error,
        resolved_file_path=_file_path,
    )
    if context.hook_executor is not None:
        await context.hook_executor.execute(
            HookEvent.POST_TOOL_USE,
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_output": tool_result.content,
                "tool_is_error": tool_result.is_error,
                "event": HookEvent.POST_TOOL_USE.value,
            },
        )
    return tool_result


async def _run_tool_with_progress(
    context: QueryContext,
    tool_name: str,
    tool_use_id: str,
    tool_input: dict[str, object],
    *,
    timing: _RunTimingTrace | None = None,
):
    async for event, result in run_tool_with_progress(
        context,
        tool_name,
        tool_use_id,
        tool_input,
        execute_tool_call=_execute_tool_call,
        query_cancelled_error=QueryCancelled,
        heartbeat_seconds=AGENT_PROGRESS_HEARTBEAT_SECONDS,
        logger=log,
        timing=timing,
    ):
        yield event, result


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _is_media_generation_tool(tool_name: str) -> bool:
    return str(tool_name or "").lower() in {"generate_image", "generate_video"}


def _media_kind_for_tool(tool_name: str) -> str:
    return "video" if str(tool_name or "").lower() == "generate_video" else "image"


def _media_output_count(tool_name: str, tool_input: dict[str, object]) -> int:
    kind = _media_kind_for_tool(tool_name)
    count = 1
    output = tool_input.get("output") if isinstance(tool_input.get("output"), dict) else {}
    try:
        count = max(count, int(output.get("count") or 0))
    except (TypeError, ValueError):
        pass
    if kind != "video":
        for key in ("outputCount", "output_count", "num_images", "num_videos", "count", "n", "batch_size", "batchSize"):
            try:
                count = max(count, int(tool_input.get(key) or 0))
            except (TypeError, ValueError):
                continue
    sequential_options = tool_input.get("sequential_image_generation_options")
    if isinstance(sequential_options, dict):
        try:
            count = max(count, int(sequential_options.get("max_images") or 0))
        except (TypeError, ValueError):
            pass
    return count


def _media_batch_concurrency(kind: str) -> int:
    env_name = "MEDIA_VIDEO_BATCH_CONCURRENCY" if kind == "video" else "MEDIA_IMAGE_BATCH_CONCURRENCY"
    default = 2 if kind == "video" else 3
    return _bounded_media_int(os.getenv(env_name), default=default, minimum=1, maximum=16)


def _bounded_media_int(raw: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _image_subtask_variant(tool_input: dict[str, object], index: int) -> str:
    brief = tool_input.get("brief") if isinstance(tool_input.get("brief"), dict) else {}
    variants = brief.get("variants") if isinstance(brief, dict) else None
    if not isinstance(variants, list) or len(variants) < index:
        return ""
    return str(variants[index - 1] or "").strip()


def _image_subtask_prompt(prompt: object, *, index: int, output_count: int, variant: str) -> str:
    base_prompt = str(prompt or "").strip()
    slot_instruction = (
        f"This is image {index} of {output_count}. Generate exactly one standalone image for this slot. "
        "Do not create a collage, grid, contact sheet, split-screen, comparison layout, or multiple variants inside one image."
    )
    parts = [base_prompt, slot_instruction]
    if variant:
        parts.append(f"Variant for this image: {variant}")
    return "\n\n".join(part for part in parts if part)


def _media_subtask_input(
    tool_input: dict[str, object],
    *,
    index: int,
    kind: str,
    allowed_fields: set[str] | None = None,
    output_count: int | None = None,
) -> dict[str, object]:
    item = dict(tool_input)
    if kind != "video":
        for key in ("outputCount", "output_count", "count", "n", "num_images", "num_videos", "batch_size", "batchSize"):
            if key in tool_input and (allowed_fields is None or key in allowed_fields):
                item[key] = 1
            else:
                item.pop(key, None)
        item.pop("sequential_image_generation_options", None)
    output = dict(item.get("output") if isinstance(item.get("output"), dict) else {})
    output["count"] = 1
    item["output"] = output
    if kind != "video":
        item.pop("out", None)
        item.pop("out_dir", None)
        variant = _image_subtask_variant(tool_input, index)
        item["prompt"] = _image_subtask_prompt(
            item.get("prompt"),
            index=index,
            output_count=max(1, int(output_count or 1)),
            variant=variant,
        )
        brief = dict(item.get("brief") if isinstance(item.get("brief"), dict) else {})
        if variant:
            brief["variants"] = [variant]
        else:
            brief.pop("variants", None)
        item["brief"] = brief
    return item


def _media_subtask_artifact_metadata(context: QueryContext, *, index: int, output_count: int) -> dict[str, object]:
    canvas_request = (context.tool_metadata or {}).get("canvas_request")
    if not isinstance(canvas_request, dict):
        return {"media_branch_index": index - 1, "media_output_count": output_count}
    target_node_ids = canvas_request.get("targetNodeIds") or canvas_request.get("target_node_ids")
    target_node_id = ""
    if isinstance(target_node_ids, list) and len(target_node_ids) >= index:
        target_node_id = str(target_node_ids[index - 1] or "")
    elif index == 1:
        target_node_id = str(canvas_request.get("targetNodeId") or canvas_request.get("target_node_id") or "")
    metadata: dict[str, object] = {
        "media_branch_index": index - 1,
        "media_output_count": output_count,
        "canvas_branch_index": index - 1,
        "canvas_output_count": output_count,
    }
    request_id = str(canvas_request.get("id") or "")
    if request_id:
        metadata["canvas_request_id"] = request_id
    kind = str(canvas_request.get("kind") or "")
    if kind:
        metadata["canvas_generation_kind"] = kind
    if target_node_id:
        metadata["canvas_target_node_id"] = target_node_id
    if isinstance(target_node_ids, list):
        metadata["canvas_target_node_ids"] = [str(item) for item in target_node_ids if str(item)]
    return metadata


async def _execute_media_generation_batch(
    context: QueryContext,
    tool_name: str,
    tool_use_id: str,
    tool_input: dict[str, object],
    *,
    output_count: int,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> ToolResultBlock:
    kind = _media_kind_for_tool(tool_name)
    concurrency = _media_batch_concurrency(kind)
    semaphore = asyncio.Semaphore(concurrency)
    hook = (context.tool_metadata or {}).get("hook")
    tool_lookup = getattr(context.tool_registry, "get", None)
    tool = tool_lookup(tool_name) if callable(tool_lookup) else None
    results: list[ToolResultBlock | None] = [None] * output_count

    async def run_one(index: int) -> None:
        sub_tool_use_id = f"{tool_use_id}:{kind}:{index}"
        sub_input = _media_subtask_input(
            tool_input,
            index=index,
            kind=kind,
            allowed_fields=_tool_input_fields(tool) if tool is not None else None,
            output_count=output_count,
        )
        artifact_metadata = _media_subtask_artifact_metadata(context, index=index, output_count=output_count)
        reservation: dict[str, Any] | None = None
        async with semaphore:
            if tool is not None:
                try:
                    tool.input_model.model_validate(sub_input)
                except ValidationError as exc:
                    results[index - 1] = ToolResultBlock(
                        tool_use_id=sub_tool_use_id,
                        content=_format_tool_validation_error(tool_name, exc),
                        is_error=True,
                        result_metadata={"error_code": "invalid_canonical_request", "tool_name": tool_name, **artifact_metadata},
                    )
                    return
            if progress_callback is not None:
                await progress_callback(
                    {
                        "phase": "media_subtask_start",
                        "status": "running",
                        "message": f"{'视频' if kind == 'video' else '图片'}生成 {index}/{output_count} 已开始。",
                        "tool_name": tool_name,
                        "tool_use_id": sub_tool_use_id,
                        "metadata": artifact_metadata,
                    }
                )
            if hook is not None and hasattr(hook, "reserve_media_tool_usage"):
                try:
                    reservation = hook.reserve_media_tool_usage(tool_name, sub_input, sub_tool_use_id, {"output_count": 1})
                except Exception as exc:
                    results[index - 1] = ToolResultBlock(
                        tool_use_id=sub_tool_use_id,
                        content=f"Media billing reservation failed: {type(exc).__name__}: {exc}",
                        is_error=True,
                        result_metadata={"media_billing_status": "failed", **artifact_metadata},
                    )
                    return
                if str((reservation or {}).get("billing_status") or "") == "recorded":
                    results[index - 1] = ToolResultBlock(
                        tool_use_id=sub_tool_use_id,
                        content="Media generation was already recorded for this subtask tool_use_id; skipping duplicate provider call.",
                        is_error=False,
                        result_metadata={"media_billing_status": "recorded", **artifact_metadata},
                    )
                    return
            last_result: ToolResultBlock | None = None
            max_attempts = 1 if hook is not None and hasattr(hook, "get_media_gateway_runtime_candidate") else 2
            for attempt in range(max_attempts):
                sub_metadata = {
                    **(context.tool_metadata or {}),
                    "media_billing_disabled": True,
                    "media_billing_reservation": reservation,
                    "media_billing_defer_failure_release": True,
                    "media_artifact_metadata": {
                        **artifact_metadata,
                        "media_retry_count": attempt,
                    },
                }
                sub_context = replace(context, tool_metadata=sub_metadata)
                last_result = await _execute_tool_call(
                    sub_context,
                    tool_name,
                    sub_tool_use_id,
                    sub_input,
                    progress_callback=progress_callback,
                    allow_media_split=False,
                )
                if not last_result.is_error:
                    break
                if not _is_retryable_media_error(last_result.content):
                    break
                if attempt + 1 < max_attempts and progress_callback is not None:
                    await progress_callback(
                        {
                            "phase": "media_subtask_retry",
                            "status": "running",
                            "message": f"{'视频' if kind == 'video' else '图片'}生成 {index}/{output_count} 失败，正在重试。",
                            "tool_name": tool_name,
                            "tool_use_id": sub_tool_use_id,
                            "metadata": artifact_metadata,
                        }
                    )
            if last_result is None:
                last_result = ToolResultBlock(
                    tool_use_id=sub_tool_use_id,
                    content=f"Tool {tool_name} failed: missing execution result",
                    is_error=True,
                    result_metadata=artifact_metadata,
                )
            if last_result.is_error:
                await _emit_canvas_subtask_error(hook, artifact_metadata, last_result.content)
            billing_metadata: dict[str, Any] = {}
            if reservation and hook is not None and not (last_result.result_metadata or {}).get("media_billing_status"):
                try:
                    if last_result.is_error:
                        billing_metadata = hook.release_media_tool_usage(
                            reservation,
                            reason="media_subtask_failed",
                            tool_metadata={"error": last_result.content},
                        )
                    else:
                        billing_metadata = hook.commit_media_tool_usage(reservation, last_result.result_metadata)
                except Exception as exc:
                    last_result = ToolResultBlock(
                        tool_use_id=sub_tool_use_id,
                        content=f"Media billing settlement failed: {type(exc).__name__}: {exc}",
                        is_error=True,
                        result_metadata={**last_result.result_metadata, **artifact_metadata},
                    )
            results[index - 1] = ToolResultBlock(
                tool_use_id=sub_tool_use_id,
                content=last_result.content,
                is_error=last_result.is_error,
                result_metadata={
                    **(last_result.result_metadata or {}),
                    **artifact_metadata,
                    **billing_metadata,
                },
            )

    await asyncio.gather(*(run_one(index) for index in range(1, output_count + 1)))
    completed = [item for item in results if item is not None]
    successes = [item for item in completed if not item.is_error]
    artifact_paths: list[str] = []
    for item in successes:
        paths = (item.result_metadata or {}).get("artifact_paths")
        if isinstance(paths, list):
            artifact_paths.extend(str(path) for path in paths if str(path).strip())
    content_lines = [
        f"{tool_name} media batch completed: {len(successes)}/{output_count} succeeded.",
        *[
            f"[{idx + 1}] {'failed' if item.is_error else 'succeeded'}: {item.content}"
            for idx, item in enumerate(completed)
        ],
    ]
    return ToolResultBlock(
        tool_use_id=tool_use_id,
        content="\n\n".join(content_lines),
        is_error=len(successes) == 0,
        result_metadata={
            "media_batch": True,
            "media_batch_kind": kind,
            "media_batch_output_count": output_count,
            "media_batch_success_count": len(successes),
            "media_batch_failure_count": output_count - len(successes),
            "media_billing_status": "recorded" if successes else "refunded",
            "artifact_paths": artifact_paths,
        },
    )


def _is_retryable_media_error(message: str) -> bool:
    text = str(message or "").lower()
    non_retryable_markers = (
        "usage_limit",
        "billing",
        "reservation",
        "commit",
        "refund",
        "auth",
        "unauthorized",
        "forbidden",
        "invalid input",
        "invalid parameter",
        "content policy",
        "safety",
        "moderation",
        "not supported",
        "unsupported",
        "pricing_not_configured",
        "media_model_pricing_not_configured",
    )
    if any(marker in text for marker in non_retryable_markers):
        return False
    retryable_markers = (
        "timeout",
        "timed out",
        "429",
        "rate limit",
        "rate_limited",
        "temporarily",
        "connection",
        "network",
        "5xx",
        " 500",
        " 502",
        " 503",
        " 504",
        "poll",
    )
    return any(marker in text for marker in retryable_markers)


async def _emit_canvas_subtask_error(hook: Any, metadata: dict[str, object], message: str) -> None:
    if hook is None or not hasattr(hook, "_emit"):
        return
    target_node_id = str(metadata.get("canvas_target_node_id") or "")
    if not target_node_id:
        return
    try:
        await hook._emit(
            "canvas_ops",
            {
                "ops": [
                    {
                        "type": "update_node",
                        "id": target_node_id,
                        "metadata": {
                            "status": "error",
                            "errorDetails": (message or "生成失败")[:1000],
                        },
                    }
                ],
                "request_id": metadata.get("canvas_request_id"),
                "message": "画布生成失败，已更新节点状态。",
            },
            save=False,
        )
    except Exception:
        log.debug("failed to emit canvas subtask error", exc_info=True)


def _resolve_permission_file_path(
    cwd: Path,
    raw_input: dict[str, object],
    parsed_input: object,
) -> str | None:
    for key in ("file_path", "path", "root"):
        value = raw_input.get(key)
        if isinstance(value, str) and value.strip():
            return str(normalize_host_path(cwd, value))

    for attr in ("file_path", "path", "root"):
        value = getattr(parsed_input, attr, None)
        if isinstance(value, str) and value.strip():
            return str(normalize_host_path(cwd, value))

    return None


def _extract_permission_command(
    raw_input: dict[str, object],
    parsed_input: object,
) -> str | None:
    value = raw_input.get("command")
    if isinstance(value, str) and value.strip():
        return value

    value = getattr(parsed_input, "command", None)
    if isinstance(value, str) and value.strip():
        return value

    return None
