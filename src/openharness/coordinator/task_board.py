"""Shared DAG task board for multi-agent orchestration."""

from __future__ import annotations

import asyncio
import posixpath
import time
from dataclasses import dataclass, field
from typing import Any, Literal

TaskBoardStatus = Literal["pending", "in_progress", "completed", "failed"]


class TaskBoardError(ValueError):
    """Domain error raised by TaskBoard operations."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class TaskBoardItem:
    """One task node in the shared orchestration DAG."""

    id: str
    subject: str
    description: str = ""
    status: TaskBoardStatus = "pending"
    owner: str | None = None
    blocked_by: list[str] = field(default_factory=list)
    write_scopes: list[str] = field(default_factory=list)
    result_summary: str | None = None
    revision: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


def _normalize_write_scope(raw: str) -> str:
    cleaned = str(raw or "").strip().replace("\\", "/")
    if not cleaned:
        return ""
    normalized = posixpath.normpath(cleaned)
    return "" if normalized == "." else normalized.rstrip("/")


def _scopes_overlap(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    return a.startswith(b + "/") or b.startswith(a + "/")


class TaskBoard:
    """Compare-and-set DAG task board shared across lead and subagents."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskBoardItem] = {}
        self._order: list[str] = []
        self._seq: int = 0
        self._lock = asyncio.Lock()

    def _next_id(self) -> str:
        self._seq += 1
        return f"task-{self._seq}"

    def _would_create_cycle(self, task_id: str, blocked_by: list[str]) -> bool:
        if task_id in blocked_by:
            return True
        visited: set[str] = set()
        stack = list(blocked_by)
        while stack:
            current = stack.pop()
            if current == task_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            node = self._tasks.get(current)
            if node is not None:
                stack.extend(node.blocked_by)
        return False

    def _validate_blocked_by(self, task_id: str, blocked_by: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for dep in blocked_by:
            dep_id = str(dep or "").strip()
            if not dep_id or dep_id in seen:
                continue
            if dep_id not in self._tasks:
                raise TaskBoardError("UNKNOWN_BLOCKER", f"Blocker task '{dep_id}' does not exist")
            seen.add(dep_id)
            normalized.append(dep_id)
        if self._would_create_cycle(task_id, normalized):
            raise TaskBoardError("DEPENDENCY_CYCLE", f"Adding blockers {normalized} to '{task_id}' would create a cycle")
        return normalized

    def _is_ready(self, item: TaskBoardItem) -> bool:
        if item.status != "pending":
            return False
        for dep_id in item.blocked_by:
            dep = self._tasks.get(dep_id)
            if dep is None or dep.status != "completed":
                return False
        return True

    def _write_scope_warnings(self, item: TaskBoardItem) -> list[str]:
        if not item.write_scopes or item.status in {"completed", "failed"}:
            return []
        warnings: list[str] = []
        for other_id in self._order:
            if other_id == item.id:
                continue
            other = self._tasks[other_id]
            if other.status in {"completed", "failed"} or not other.write_scopes:
                continue
            for my_scope in item.write_scopes:
                for other_scope in other.write_scopes:
                    if _scopes_overlap(my_scope, other_scope):
                        warnings.append(
                            f"Scope '{my_scope}' overlaps with active {other.id} ('{other_scope}')"
                        )
        return warnings

    def _to_view(self, item: TaskBoardItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "revision": item.revision,
            "subject": item.subject,
            "description": item.description,
            "status": item.status,
            "owner": item.owner,
            "blocked_by": list(item.blocked_by),
            "write_scopes": list(item.write_scopes),
            "result_summary": item.result_summary,
            "ready": self._is_ready(item),
            "write_scope_warnings": self._write_scope_warnings(item),
        }

    async def create_task(
        self,
        *,
        subject: str,
        description: str = "",
        blocked_by: list[str] | None = None,
        write_scopes: list[str] | None = None,
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Create a new task in the DAG."""
        clean_subject = str(subject or "").strip()
        if not clean_subject:
            raise TaskBoardError("INVALID_SUBJECT", "Task subject cannot be empty")
        async with self._lock:
            task_id = self._next_id()
            deps = self._validate_blocked_by(task_id, list(blocked_by or []))
            scopes = [
                normalized
                for normalized in (_normalize_write_scope(s) for s in (write_scopes or []))
                if normalized
            ]
            clean_owner = str(owner or "").strip() or None
            status: TaskBoardStatus = "in_progress" if clean_owner else "pending"
            item = TaskBoardItem(
                id=task_id,
                subject=clean_subject,
                description=str(description or "").strip(),
                status=status,
                owner=clean_owner,
                blocked_by=deps,
                write_scopes=scopes,
            )
            self._tasks[task_id] = item
            self._order.append(task_id)
            return self._to_view(item)

    async def batch_create(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create multiple tasks atomically, supporting ``ref`` aliases within the batch."""
        if not items:
            return []
        async with self._lock:
            ref_to_id: dict[str, str] = {}
            planned: list[tuple[str, dict[str, Any]]] = []
            for idx, raw in enumerate(items):
                if not isinstance(raw, dict):
                    raise TaskBoardError("INVALID_BATCH_ITEM", f"Batch item at index {idx} must be an object")
                subject = str(raw.get("subject") or "").strip()
                if not subject:
                    raise TaskBoardError("INVALID_SUBJECT", f"Batch item {idx} has empty subject")
                task_id = self._next_id()
                ref = str(raw.get("ref") or raw.get("id") or f"#{idx}").strip()
                ref_to_id[ref] = task_id
                planned.append((task_id, raw))

            created_ids: list[str] = []
            try:
                for task_id, raw in planned:
                    raw_deps = [str(dep).strip() for dep in (raw.get("blocked_by") or []) if str(dep).strip()]
                    resolved_deps = [ref_to_id.get(dep, dep) for dep in raw_deps]
                    # Temporarily register placeholder nodes so cross-references validate cleanly
                    scopes = [
                        normalized
                        for normalized in (_normalize_write_scope(s) for s in (raw.get("write_scopes") or []))
                        if normalized
                    ]
                    clean_owner = str(raw.get("owner") or "").strip() or None
                    item = TaskBoardItem(
                        id=task_id,
                        subject=str(raw.get("subject") or "").strip(),
                        description=str(raw.get("description") or "").strip(),
                        status="in_progress" if clean_owner else "pending",
                        owner=clean_owner,
                        blocked_by=[],
                        write_scopes=scopes,
                    )
                    self._tasks[task_id] = item
                    self._order.append(task_id)
                    created_ids.append(task_id)
                for task_id, raw in planned:
                    raw_deps = [str(dep).strip() for dep in (raw.get("blocked_by") or []) if str(dep).strip()]
                    resolved_deps = [ref_to_id.get(dep, dep) for dep in raw_deps]
                    self._tasks[task_id].blocked_by = self._validate_blocked_by(task_id, resolved_deps)
            except Exception:
                for tid in created_ids:
                    self._tasks.pop(tid, None)
                    if tid in self._order:
                        self._order.remove(tid)
                raise

            return [self._to_view(self._tasks[tid]) for tid in created_ids]

    async def claim_task(
        self,
        *,
        owner: str,
        task_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Atomically claim a ready task (either specific ``task_id`` or next ready)."""
        clean_owner = str(owner or "").strip()
        if not clean_owner:
            raise TaskBoardError("INVALID_OWNER", "Owner name is required to claim a task")
        async with self._lock:
            target: TaskBoardItem | None = None
            if task_id:
                target = self._tasks.get(task_id)
                if target is None:
                    raise TaskBoardError("TASK_NOT_FOUND", f"Task '{task_id}' not found")
                if not self._is_ready(target):
                    raise TaskBoardError(
                        "TASK_NOT_READY",
                        f"Task '{task_id}' is not ready (status={target.status}, blocked_by={target.blocked_by})",
                    )
            else:
                for tid in self._order:
                    candidate = self._tasks[tid]
                    if self._is_ready(candidate):
                        target = candidate
                        break
                if target is None:
                    return None
            target.status = "in_progress"
            target.owner = clean_owner
            target.revision += 1
            target.updated_at = time.time()
            return self._to_view(target)

    async def update_task(
        self,
        *,
        task_id: str,
        status: TaskBoardStatus | None = None,
        owner: str | None = None,
        blocked_by: list[str] | None = None,
        write_scopes: list[str] | None = None,
        result_summary: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Update a task with optional compare-and-set revision enforcement."""
        async with self._lock:
            item = self._tasks.get(task_id)
            if item is None:
                raise TaskBoardError("TASK_NOT_FOUND", f"Task '{task_id}' not found")
            if expected_revision is not None and item.revision != expected_revision:
                raise TaskBoardError(
                    "REVISION_CONFLICT",
                    f"Task '{task_id}' is at revision {item.revision}, expected {expected_revision}",
                )
            if blocked_by is not None:
                item.blocked_by = self._validate_blocked_by(task_id, list(blocked_by))
            if write_scopes is not None:
                item.write_scopes = [
                    normalized
                    for normalized in (_normalize_write_scope(s) for s in write_scopes)
                    if normalized
                ]
            if owner is not None:
                clean_owner = owner.strip()
                item.owner = clean_owner or None
            if status is not None:
                if status == "completed":
                    incomplete_deps = [
                        dep_id
                        for dep_id in item.blocked_by
                        if dep_id in self._tasks and self._tasks[dep_id].status != "completed"
                    ]
                    if incomplete_deps:
                        raise TaskBoardError(
                            "BLOCKED_BY_INCOMPLETE",
                            f"Cannot complete '{task_id}' while blockers {incomplete_deps} are incomplete",
                        )
                item.status = status
                if status == "pending" and owner is None:
                    item.owner = None
            if result_summary is not None:
                item.result_summary = result_summary.strip() or None
            item.revision += 1
            item.updated_at = time.time()
            return self._to_view(item)

    async def get_task(self, task_id: str) -> dict[str, Any]:
        """Return a single task view."""
        async with self._lock:
            item = self._tasks.get(task_id)
            if item is None:
                raise TaskBoardError("TASK_NOT_FOUND", f"Task '{task_id}' not found")
            return self._to_view(item)

    async def list_tasks(self) -> list[dict[str, Any]]:
        """List all tasks in creation order."""
        async with self._lock:
            return [self._to_view(self._tasks[tid]) for tid in self._order]

    async def summary(self) -> dict[str, Any]:
        """Return compact counts + task views for UI/progress events."""
        async with self._lock:
            views = [self._to_view(self._tasks[tid]) for tid in self._order]
        counts = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0, "ready": 0}
        for view in views:
            counts[view["status"]] = counts.get(view["status"], 0) + 1
            if view["ready"]:
                counts["ready"] += 1
        return {
            "total": len(views),
            **counts,
            "tasks": views,
        }
