"""Structured DAG task board tool for multi-agent orchestration."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from openharness.coordinator.task_board import TaskBoard, TaskBoardError, TaskBoardStatus
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class TaskBoardBatchItemInput(BaseModel):
    """One task item in a ``batch_create`` request."""

    ref: str | None = Field(default=None, description="Optional local alias referenced by blocked_by in the same batch")
    subject: str = Field(description="Short action-oriented task title")
    description: str = Field(default="", description="Detailed task instructions and acceptance criteria")
    blocked_by: list[str] = Field(default_factory=list, description="Task IDs or batch refs that must complete first")
    write_scopes: list[str] = Field(default_factory=list, description="Advisory file or directory prefixes touched by this task")
    owner: str | None = Field(default=None, description="Optional initial agent owner")


class TaskBoardToolInput(BaseModel):
    """Arguments for interacting with the shared orchestration task board."""

    action: Literal["create", "batch_create", "claim", "update", "list", "get"] = Field(
        description="Task board operation to perform"
    )
    task_id: str | None = Field(default=None, description="Target task ID (for get, claim, update)")
    subject: str | None = Field(default=None, description="Task title (for create)")
    description: str | None = Field(default=None, description="Task description (for create)")
    status: TaskBoardStatus | None = Field(default=None, description="New task status (for update)")
    owner: str | None = Field(default=None, description="Agent name claiming or owning the task")
    blocked_by: list[str] | None = Field(default=None, description="Task IDs blocking this task")
    write_scopes: list[str] | None = Field(default=None, description="Advisory file/directory scopes")
    result_summary: str | None = Field(default=None, description="Completion or failure summary (for update)")
    expected_revision: int | None = Field(default=None, description="Optional CAS revision check (for update)")
    items: list[TaskBoardBatchItemInput] = Field(default_factory=list, description="Batch task definitions (for batch_create)")


def get_or_create_task_board(metadata: dict[str, Any] | None) -> TaskBoard:
    """Return the shared TaskBoard from metadata, creating one if absent."""
    if isinstance(metadata, dict):
        existing = metadata.get("task_board")
        if isinstance(existing, TaskBoard):
            return existing
        board = TaskBoard()
        metadata["task_board"] = board
        return board
    return TaskBoard()


class TaskBoardTool(BaseTool):
    """Manage a shared dependency-aware task board across lead and subagents."""

    name = "task_board"
    display_name = "Task Board"
    default_start_message = "正在更新任务编排看板..."
    description = (
        "Manage a shared dependency-aware (DAG) task board across lead and subagents. "
        "Supports batch_create with blocked_by dependencies, atomic claim of ready tasks, "
        "write_scopes overlap warnings, and compare-and-set status updates."
    )
    input_model = TaskBoardToolInput
    parallel_safe = False
    execution_group = "task_board"

    def is_read_only(self, arguments: TaskBoardToolInput) -> bool:
        return arguments.action in {"list", "get"}

    def is_concurrency_safe(self, arguments: TaskBoardToolInput) -> bool:
        return arguments.action in {"list", "get"}

    async def execute(self, arguments: TaskBoardToolInput, context: ToolExecutionContext) -> ToolResult:
        board = get_or_create_task_board(context.metadata)
        caller_name = str(context.metadata.get("subagent_name") or "lead")
        try:
            if arguments.action == "create":
                view = await board.create_task(
                    subject=arguments.subject or "",
                    description=arguments.description or "",
                    blocked_by=arguments.blocked_by,
                    write_scopes=arguments.write_scopes,
                    owner=arguments.owner,
                )
                result_payload: Any = view
            elif arguments.action == "batch_create":
                if not arguments.items:
                    return ToolResult(output="batch_create requires at least one item", is_error=True)
                views = await board.batch_create([item.model_dump() for item in arguments.items])
                result_payload = {"created": views, "count": len(views)}
            elif arguments.action == "claim":
                claimed = await board.claim_task(
                    owner=arguments.owner or caller_name,
                    task_id=arguments.task_id,
                )
                if claimed is None:
                    return ToolResult(
                        output=json.dumps({"claimed": None, "message": "No ready tasks available"}, ensure_ascii=False),
                        metadata={"task_board_summary": await board.summary()},
                    )
                result_payload = {"claimed": claimed}
            elif arguments.action == "update":
                if not arguments.task_id:
                    return ToolResult(output="update requires task_id", is_error=True)
                updated = await board.update_task(
                    task_id=arguments.task_id,
                    status=arguments.status,
                    owner=arguments.owner,
                    blocked_by=arguments.blocked_by,
                    write_scopes=arguments.write_scopes,
                    result_summary=arguments.result_summary,
                    expected_revision=arguments.expected_revision,
                )
                result_payload = updated
            elif arguments.action == "get":
                if not arguments.task_id:
                    return ToolResult(output="get requires task_id", is_error=True)
                result_payload = await board.get_task(arguments.task_id)
            else:
                result_payload = await board.summary()
        except TaskBoardError as exc:
            return ToolResult(output=f"{exc.code}: {exc}", is_error=True)

        summary = await board.summary()
        if arguments.action not in {"list", "get"} and context.progress_callback is not None:
            try:
                await context.progress_callback(
                    {
                        "phase": "task_board_updated",
                        "status": "info",
                        "message": (
                            f"任务看板已更新：共 {summary['total']} 项，"
                            f"进行中 {summary['in_progress']}，已完成 {summary['completed']}，就绪 {summary['ready']}"
                        ),
                        "metadata": {
                            "action": arguments.action,
                            "caller": caller_name,
                            "task_board": summary,
                        },
                    }
                )
            except Exception:
                pass

        return ToolResult(
            output=json.dumps(result_payload, ensure_ascii=False, indent=2),
            metadata={"task_board": summary},
        )
