"""Tool for creating local cron-style jobs."""

from __future__ import annotations

import base64
import datetime
import json
import os
import shlex
import sys
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from openharness.services.cron import upsert_cron_job, validate_cron_expression, validate_timezone
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


DEFAULT_TIMEZONE = "Asia/Shanghai"


def _build_saas_task_command(api_dir: str, payload: dict[str, Any]) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    command = " ".join(
        [
            shlex.quote(sys.executable),
            shlex.quote(str(Path(api_dir) / "scheduled_task_runner.py")),
            "--payload-b64",
            shlex.quote(encoded),
        ]
    )
    return f"& {command}" if os.name == "nt" else command


def _frequency_from_schedule(schedule: str) -> str:
    fields = schedule.split()
    if len(fields) != 5:
        return "custom"
    _minute, _hour, day_of_month, month, weekday = fields
    if month != "*":
        return "custom"
    if day_of_month != "*":
        return "monthly"
    if weekday in {"1-5", "MON-FRI", "mon-fri"}:
        return "workdays"
    if weekday != "*":
        return "weekly"
    return "daily"


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _create_saas_scheduled_task(arguments: "CronCreateToolInput", payload: dict[str, Any], context: ToolExecutionContext) -> ToolResult | None:
    metadata = context.metadata or {}
    db = metadata.get("db_session")
    user_id = metadata.get("user_id")
    thread_id = metadata.get("thread_id")
    if db is None or not user_id or not thread_id:
        return None
    if arguments.command:
        return None

    try:
        from models import AgentEvent, AgentThread, ScheduledTask
        from scheduled_task_service import apply_context_defaults, execution_skill_ids, next_run_time, normalize_list, serialize_task
        from scheduled_tasks import scheduled_task_card_payload
    except Exception as exc:
        return ToolResult(
            output=f"Cannot create SaaS scheduled task: scheduled task service is unavailable ({exc}).",
            is_error=True,
        )

    thread = db.query(AgentThread).filter(AgentThread.id == str(thread_id), AgentThread.owner_id == int(user_id)).first()
    if not thread:
        return ToolResult(output="Cannot create scheduled task: context thread not found.", is_error=True)

    title = str(payload.get("title") or arguments.name or "定时任务").strip()[:120] or "定时任务"
    prompt = str(payload.get("message") or arguments.message or "").strip()
    if not prompt:
        return ToolResult(output="Scheduled task requires message.", is_error=True)

    scheduled_run_id = str(metadata.get("scheduled_run_id") or "")
    if scheduled_run_id:
        scheduled_task_id = str(metadata.get("scheduled_task_id") or "")
        scheduled_task_title = str(metadata.get("scheduled_task_title") or "").strip()
        scheduled_task_schedule = str(metadata.get("scheduled_task_schedule") or "").strip()
        existing = None
        if scheduled_task_id:
            existing = (
                db.query(ScheduledTask.id)
                .filter(
                    ScheduledTask.id == scheduled_task_id,
                    ScheduledTask.owner_id == int(user_id),
                    ScheduledTask.deleted_at.is_(None),
                )
                .first()
            )
        elif scheduled_task_title and scheduled_task_schedule:
            existing = (
                db.query(ScheduledTask.id)
                .filter(
                    ScheduledTask.owner_id == int(user_id),
                    ScheduledTask.title == scheduled_task_title,
                    ScheduledTask.schedule == scheduled_task_schedule,
                    ScheduledTask.deleted_at.is_(None),
                )
                .first()
            )
        same_request = (
            (scheduled_task_title and title == scheduled_task_title)
            or (scheduled_task_schedule and arguments.schedule.strip() == scheduled_task_schedule)
        )
        if existing or same_request:
            return ToolResult(
                output=(
                    "Cannot create a scheduled task from inside an existing scheduled task run. "
                    "This run should execute the task content directly instead of creating another schedule."
                ),
                is_error=True,
            )

    task = ScheduledTask(
        id=str(uuid.uuid4()),
        owner_id=int(user_id),
        title=title,
        prompt=prompt,
        schedule=arguments.schedule.strip(),
        frequency=str(payload.get("frequency") or _frequency_from_schedule(arguments.schedule)).strip() or "custom",
        timezone=arguments.timezone or DEFAULT_TIMEZONE,
        enabled=arguments.enabled,
        skip_confirmation=bool(payload.get("skip_confirmation") or payload.get("skipConfirmation") or False),
        run_mode=str(payload.get("run_mode") or "continue_thread"),
        model_id=thread.model_id,
        enabled_skills=execution_skill_ids(thread.enabled_skills),
        selected_connectors=normalize_list(thread.selected_connectors, limit=8),
        preferred_image_model=thread.preferred_image_model,
        preferred_video_model=thread.preferred_video_model,
        is_model_auto_mode=bool(thread.is_model_auto_mode),
        context_type="thread",
        context_thread_id=thread.id,
        cloud_computer=False,
    )
    apply_context_defaults(db, task)
    task.next_run_at = next_run_time(task.schedule, timezone=task.timezone) if task.enabled else None
    db.add(task)
    db.flush()

    turn_id = str(metadata.get("turn_id") or "")
    card_payload = {**scheduled_task_card_payload(task), "turn_id": turn_id or None}
    event = AgentEvent(thread_id=thread.id, type="scheduled_task_card", payload=card_payload)
    db.add(event)
    db.commit()
    db.refresh(task)
    db.refresh(event)

    try:
        import asyncio
        from ws_agent import manager

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(manager.send_event(thread.id, "scheduled_task_card", card_payload))
        except RuntimeError:
            asyncio.run(manager.send_event(thread.id, "scheduled_task_card", card_payload))
    except Exception:
        pass

    try:
        from tasks import _invalidate_task_cache

        _invalidate_task_cache(int(user_id), thread.id)
    except Exception:
        pass

    serialized = _json_safe(serialize_task(task, runs=[]))
    return ToolResult(
        output=(
            f"Created SaaS scheduled task '{task.title}' [{task.schedule}] "
            f"({'enabled' if task.enabled else 'disabled'}). It is visible in Scheduled Tasks."
        ),
        metadata={"scheduled_task": serialized, "scheduled_task_card": _json_safe(card_payload)},
    )


class CronCreateToolInput(BaseModel):
    """Arguments for cron job creation."""

    name: str = Field(description="Unique cron job name")
    schedule: str = Field(
        description=(
            "Cron schedule expression (e.g. '*/5 * * * *' for every 5 minutes, "
            "'0 9 * * 1-5' for weekdays at 9am)"
        ),
    )
    command: str | None = Field(default=None, description="Shell command to run when triggered")
    message: str | None = Field(default=None, description="Instruction for an agent_turn cron job")
    timezone: str | None = Field(
        default=None,
        description=(
            "IANA timezone for interpreting cron schedule. If omitted, use the user's default timezone "
            f"({DEFAULT_TIMEZONE}) and do not ask a timezone-only clarification."
        ),
    )
    cwd: str | None = Field(default=None, description="Optional working directory override")
    enabled: bool = Field(default=True, description="Whether the job is active")
    payload: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional nanobot-style payload. Example: "
            "{'kind': 'agent_turn', 'message': 'check GitHub', 'deliver': True, 'channel': 'feishu', 'to': 'ou_xxx'}."
        ),
    )
    notify: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional notification target. Example: "
            "{'type': 'feishu_dm', 'user_open_id': 'ou_xxx'} to send job output to a Feishu private chat."
        ),
    )


class CronCreateTool(BaseTool):
    """Create or replace a local cron job."""

    name = "cron_create"
    description = (
        "Create or replace a local cron job with a standard cron expression. "
        f"When the user gives a local time without a timezone, default to {DEFAULT_TIMEZONE}; "
        "ask about timezone only when another region, multiple locales, or material ambiguity is involved. "
        "Use 'oh cron start' to run the scheduler daemon."
    )
    input_model = CronCreateToolInput

    async def execute(
        self,
        arguments: CronCreateToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        if not validate_cron_expression(arguments.schedule):
            return ToolResult(
                output=(
                    f"Invalid cron expression: {arguments.schedule!r}\n"
                    "Use standard 5-field format: minute hour day month weekday\n"
                    "Examples: '*/5 * * * *' (every 5 min), '0 9 * * 1-5' (weekdays 9am)"
                ),
                is_error=True,
            )
        if not validate_timezone(arguments.timezone):
            return ToolResult(output=f"Invalid timezone: {arguments.timezone!r}", is_error=True)
        effective_timezone = arguments.timezone or DEFAULT_TIMEZONE

        payload = dict(arguments.payload or {})
        if arguments.message:
            payload.setdefault("kind", "agent_turn")
            payload.setdefault("message", arguments.message)
        if arguments.notify is not None:
            payload.setdefault("deliver", True)
            if str(arguments.notify.get("type") or "").strip().lower() == "feishu_dm":
                payload.setdefault("channel", "feishu")
                payload.setdefault("to", arguments.notify.get("user_open_id") or arguments.notify.get("open_id"))

        if payload and not payload.get("message") and not arguments.command:
            return ToolResult(output="Cron job requires payload.message, message, or command.", is_error=True)
        if not payload and not arguments.command:
            return ToolResult(output="Cron job requires command or message.", is_error=True)

        saas_result = _create_saas_scheduled_task(arguments, payload, context)
        if saas_result is not None:
            return saas_result

        saas_user_id = context.metadata.get("user_id")
        saas_api_dir = context.metadata.get("saas_api_dir")
        saas_thread_id = context.metadata.get("thread_id")

        job = {
            "name": arguments.name,
            "schedule": arguments.schedule,
            "timezone": effective_timezone,
            "cwd": arguments.cwd or str(context.cwd),
            "enabled": arguments.enabled,
        }
        if arguments.command is not None:
            job["command"] = arguments.command
        if payload:
            if saas_user_id and saas_api_dir and not arguments.command:
                payload["kind"] = "saas_agent_task"
                payload.setdefault("title", arguments.name)
                payload.setdefault("user_id", saas_user_id)
                payload.setdefault("source", "chat")
                payload.setdefault("origin_thread_id", saas_thread_id)
                job["title"] = str(payload.get("title") or arguments.name)
                job["description"] = str(payload.get("message") or "")
                job["source"] = "chat"
                job["created_by_user_id"] = saas_user_id
                job["origin_thread_id"] = saas_thread_id
                job["command"] = _build_saas_task_command(
                    str(saas_api_dir),
                    {
                        "user_id": saas_user_id,
                        "title": payload.get("title") or arguments.name,
                        "prompt": payload.get("message"),
                    },
                )
            else:
                payload.setdefault("kind", "agent_turn")
            job["payload"] = payload
        if arguments.notify is not None:
            job["notify"] = arguments.notify
        upsert_cron_job(job)
        status = "enabled" if arguments.enabled else "disabled"
        return ToolResult(
            output=f"Created cron job '{arguments.name}' [{arguments.schedule}] ({status})"
        )
