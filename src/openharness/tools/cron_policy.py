"""Shared cron tool execution policy."""

from __future__ import annotations

from typing import Any

from openharness.tools.base import ToolResult


SCHEDULE_MANAGEMENT_TOOL_NAMES = frozenset(
    {"cron_create", "cron_list", "cron_toggle", "cron_delete"}
)
SCHEDULED_RUN_CRON_BLOCK_MESSAGE = (
    "Schedule management tools are unavailable while executing an existing scheduled task run. "
    "Execute the scheduled task's business work directly."
)


def _scheduled_run_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    nested = metadata.get("scheduled_run")
    if isinstance(nested, dict):
        merged = dict(nested)
        merged.update(metadata)
        return merged
    return metadata


def is_schedule_management_blocked(metadata: dict[str, Any] | None) -> bool:
    scheduled = _scheduled_run_metadata(metadata)
    if not scheduled.get("scheduled_run_id"):
        return False
    return not bool(scheduled.get("allow_schedule_management"))


def scheduled_run_cron_block_result(metadata: dict[str, Any] | None) -> ToolResult | None:
    if not is_schedule_management_blocked(metadata):
        return None
    return ToolResult(
        output=SCHEDULED_RUN_CRON_BLOCK_MESSAGE,
        is_error=True,
        metadata={"error_code": "scheduled_run_schedule_management_blocked"},
    )
