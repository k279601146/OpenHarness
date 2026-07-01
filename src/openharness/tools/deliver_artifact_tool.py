"""Host-side delivery bridge for files generated inside the sandbox."""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from openharness.sandbox.session import get_active_sandbox, get_sandbox_session, touch_task_manifest
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.sandbox_workspace import (
    get_e2b_task_session,
    sandbox_read_roots,
    to_sandbox_path,
    uses_e2b_task_workspace,
)


class DeliverArtifactInput(BaseModel):
    """Arguments for delivering sandbox artifacts to the host/UI layer."""

    sandbox_path: str | None = Field(
        default=None,
        description="Single absolute sandbox file path, normally under /home/user.",
    )
    paths: list[str] | None = Field(
        default=None,
        description="Multiple absolute sandbox file paths to deliver in one call.",
    )
    filename: str | None = Field(
        default=None,
        description="Optional output filename. Required only when renaming a single file or naming a zip bundle.",
    )
    package_as_zip: bool = Field(
        default=False,
        description="When true, deliver all provided paths as one zip file.",
    )

    @model_validator(mode="after")
    def validate_paths(self) -> "DeliverArtifactInput":
        candidates = self.paths or ([self.sandbox_path] if self.sandbox_path else [])
        if not candidates:
            raise ValueError("Provide sandbox_path or paths")
        return self


class DeliverArtifactTool(BaseTool):
    """Copy sandbox-generated files to the host workspace for download/persistence."""

    name = "deliver_artifact"
    description = (
        "Publish files generated inside the sandbox when they are not already available as "
        "agent_artifact outputs. Use this for files created by shell/code steps that still need "
        "a downloadable, persistent artifact. Media generation outputs are already published "
        "individually, but their E2B mirror paths may be included as members when the user asks "
        "for a zip bundle. Supports one file, multiple files, or a zip bundle."
    )
    input_model = DeliverArtifactInput
    requires_sandbox = False

    async def execute(
        self,
        arguments: DeliverArtifactInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        await _emit_progress(context, "artifact_scan", "正在检查需要交付的产物...")
        raw_paths = arguments.paths or ([arguments.sandbox_path] if arguments.sandbox_path else [])
        try:
            requested_paths = [
                to_sandbox_path(context, path) if uses_e2b_task_workspace(context) else _normalize_sandbox_path(path)
                for path in raw_paths
                if path
            ]
        except Exception as exc:
            return ToolResult(output=f"Invalid artifact path: {exc}", is_error=True)
        if not requested_paths:
            return ToolResult(output="No sandbox paths were provided.", is_error=True)

        reused: list[dict] = []
        if not arguments.package_as_zip:
            requested_paths = _filter_already_published_paths(context, requested_paths, reused)
            if not requested_paths:
                reused_paths = [
                    _artifact_display_path(artifact)
                    for artifact in reused
                    if _artifact_display_path(artifact)
                ]
                await _emit_progress(
                    context,
                    "artifact_ready",
                    "产物已交付过，已复用现有下载链接。",
                    status="success",
                    detail="\n".join(reused_paths),
                    metadata={
                        "artifact_paths": [],
                        "reused_artifact_paths": reused_paths,
                        "delivery_skipped": True,
                        "delivery_required": False,
                        "terminal_noop": True,
                        "skip_reason": "already_published_or_mirror",
                    },
                )
                return ToolResult(
                    output=(
                        "Artifact delivery skipped because the requested sandbox path is already "
                        "published. Do not call deliver_artifact again for this single file; "
                        "include it only as a member when creating a requested zip bundle.\n"
                        + "\n".join(f"- {path}" for path in reused_paths)
                    ).strip(),
                    metadata={
                        "artifact_paths": [],
                        "reused_artifact_paths": reused_paths,
                        "delivery_skipped": True,
                        "delivery_required": False,
                        "terminal_noop": True,
                        "skip_reason": "already_published_or_mirror",
                        **({"workspace": "e2b"} if uses_e2b_task_workspace(context) else {}),
                    },
                )

        if uses_e2b_task_workspace(context):
            try:
                await _emit_progress(context, "sandbox_start", "正在准备 E2B 沙箱以读取产物...", workspace="e2b")
                session = await get_e2b_task_session(context)
            except Exception as exc:
                await _emit_progress(context, "artifact_ready", "产物交付失败：E2B 沙箱不可用。", status="error", detail=str(exc), workspace="e2b")
                return ToolResult(output=f"E2B sandbox session is not available: {exc}", is_error=True)
        else:
            session = _resolve_sandbox_session(context)

        if session is None or not getattr(session, "is_running", False):
            await _emit_progress(context, "artifact_sync", "正在从宿主工作区交付产物...", workspace="host")
            return await _deliver_host_paths(arguments, context, requested_paths)

        await _emit_progress(
            context,
            "artifact_scan",
            "正在展开产物路径...",
            workspace="e2b" if uses_e2b_task_workspace(context) else "host",
            detail="\n".join(requested_paths[:20]),
        )
        sandbox_paths = await _expand_requested_paths(session, requested_paths)
        if not sandbox_paths:
            return ToolResult(output="No sandbox paths were provided.", is_error=True)

        for path in sandbox_paths:
            if not _is_allowed_sandbox_path(context, path):
                return ToolResult(
                    output=f"Refusing to deliver path outside the sandbox user area/current task sandbox area: {path}",
                    is_error=True,
                )

        thread_id = str(context.metadata.get("thread_id") or "default")
        output_dir = _resolve_output_dir(context.cwd, thread_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        delivered: list[Path] = []
        delivered_sources: list[str | None] = []
        try:
            if arguments.package_as_zip or _contains_directory_request(requested_paths, sandbox_paths):
                await _emit_progress(
                    context,
                    "artifact_read",
                    f"正在读取 {len(sandbox_paths)} 个沙箱产物并打包...",
                    workspace="e2b" if uses_e2b_task_workspace(context) else "host",
                )
                zip_name = _safe_filename(arguments.filename or "artifacts.zip")
                if not zip_name.lower().endswith(".zip"):
                    zip_name += ".zip"
                local_zip = _unique_path(output_dir / zip_name)
                with zipfile.ZipFile(local_zip, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                    for sandbox_path in sandbox_paths:
                        content = await session.read_file_binary(sandbox_path)
                        bundle.writestr(_safe_archive_name(sandbox_path), _ensure_bytes(content))
                delivered.append(local_zip)
                delivered_sources.append(None)
            else:
                await _emit_progress(
                    context,
                    "artifact_read",
                    f"正在读取 {len(sandbox_paths)} 个沙箱产物...",
                    workspace="e2b" if uses_e2b_task_workspace(context) else "host",
                )
                for index, sandbox_path in enumerate(sandbox_paths):
                    filename = (
                        _safe_filename(arguments.filename)
                        if arguments.filename and len(sandbox_paths) == 1
                        else _safe_filename(os.path.basename(sandbox_path) or f"artifact_{index + 1}")
                    )
                    content = await session.read_file_binary(sandbox_path)
                    content_bytes = _ensure_bytes(content)
                    existing = _find_existing_artifact(context, content_bytes)
                    if existing:
                        reused.append(existing)
                        continue

                    local_path = _unique_path(output_dir / filename)
                    local_path.write_bytes(content_bytes)
                    delivered.append(local_path)
                    delivered_sources.append(sandbox_path)
        except Exception as exc:
            await _emit_progress(context, "artifact_ready", "产物交付失败。", status="error", detail=str(exc))
            return ToolResult(output=f"Failed to deliver artifact: {exc}", is_error=True)

        await _emit_progress(
            context,
            "artifact_sync",
            "正在同步产物到可下载目录...",
            workspace="e2b" if uses_e2b_task_workspace(context) else "host",
            detail="\n".join(str(path) for path in delivered),
        )
        hook = context.metadata.get("hook")
        if hook is not None:
            for local_path, source_sandbox_path in zip(delivered, delivered_sources):
                await _call_hook_on_artifact(
                    hook,
                    str(local_path),
                    reason=f"Delivered sandbox artifact: {local_path.name}",
                    sandbox_session=session,
                    source_tool="deliver_artifact",
                    tool_use_id=_context_tool_use_id(context),
                    origin="sandbox_generated",
                    sandbox_path=source_sandbox_path,
                    sandbox_path_role="canonical" if source_sandbox_path else None,
                    metadata={"source_sandbox_paths": sandbox_paths} if source_sandbox_path is None else None,
                )

        lines = ["Delivered artifact(s):"]
        lines.extend(f"- {path}" for path in delivered)
        if reused:
            lines.append("Reused existing artifact(s):")
            lines.extend(f"- {path}" for path in (_artifact_display_path(artifact) for artifact in reused) if path)
        if uses_e2b_task_workspace(context):
            try:
                await touch_task_manifest(
                    session,
                    thread_id,
                    delivered_artifact_paths=sandbox_paths,
                )
            except Exception:
                pass
        await _emit_progress(
            context,
            "artifact_ready",
            "产物已可下载。" if delivered else "产物已存在，已复用下载链接。",
            status="success",
            workspace="e2b" if uses_e2b_task_workspace(context) else "host",
            detail="\n".join([*(str(path) for path in delivered), *(_artifact_display_path(artifact) or "" for artifact in reused)]),
            metadata={"artifact_paths": [str(path) for path in delivered], "reused_artifact_paths": [_artifact_display_path(artifact) for artifact in reused if _artifact_display_path(artifact)]},
        )
        return ToolResult(
            output="\n".join(lines),
            metadata={
                "artifact_paths": [str(path) for path in delivered],
                "reused_artifact_paths": [_artifact_display_path(artifact) for artifact in reused if _artifact_display_path(artifact)],
                **({"workspace": "e2b"} if uses_e2b_task_workspace(context) else {}),
            },
        )


def _resolve_sandbox_session(context: ToolExecutionContext):
    user_id = context.metadata.get("user_id")
    thread_id = context.metadata.get("thread_id")
    if user_id is not None and thread_id:
        try:
            session = get_active_sandbox(int(user_id), str(thread_id))
            if session is not None:
                return session
        except (TypeError, ValueError):
            pass
    return get_sandbox_session()


def _find_existing_artifact(context: ToolExecutionContext, content: bytes) -> dict | None:
    hook = context.metadata.get("hook")
    finder = getattr(hook, "find_artifact_by_content", None)
    if finder is None:
        return None
    try:
        existing = finder(content)
    except Exception:
        return None
    if not isinstance(existing, dict):
        return None
    return existing


def _artifact_display_path(artifact: dict) -> str | None:
    value = artifact.get("url") or artifact.get("file_path") or artifact.get("path")
    return str(value) if value else None


def _filter_already_published_paths(
    context: ToolExecutionContext,
    requested_paths: list[str],
    reused: list[dict],
) -> list[str]:
    hook = context.metadata.get("hook")
    finder = getattr(hook, "find_artifact_by_sandbox_path", None)
    if finder is None:
        return requested_paths

    remaining: list[str] = []
    for path in requested_paths:
        try:
            existing = finder(path)
        except Exception:
            existing = None
        if not isinstance(existing, dict):
            remaining.append(path)
            continue
        role = str(existing.get("sandbox_path_role") or "")
        state = str(existing.get("publish_state") or "")
        if state == "published" or role in {"workspace_mirror", "input_mirror"}:
            reused.append(existing)
        else:
            remaining.append(path)
    return remaining


async def _deliver_host_paths(
    arguments: DeliverArtifactInput,
    context: ToolExecutionContext,
    requested_paths: list[str],
) -> ToolResult:
    cwd = Path(context.cwd).resolve()
    host_paths = [_resolve_host_path(cwd, path) for path in requested_paths]
    missing = [str(path) for path in host_paths if not path.exists()]
    if missing:
        return ToolResult(
            output=(
                "No active sandbox session is available, and these host paths were not found:\n"
                + "\n".join(f"- {path}" for path in missing)
            ),
            is_error=True,
        )
    outside = [str(path) for path in host_paths if not _is_allowed_host_path(cwd, path)]
    if outside:
        return ToolResult(
            output="Refusing to deliver host path outside the workspace:\n" + "\n".join(f"- {path}" for path in outside),
            is_error=True,
        )

    thread_id = str(context.metadata.get("thread_id") or "default")
    output_dir = _resolve_output_dir(cwd, thread_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    delivered: list[Path] = []
    try:
        if arguments.package_as_zip or any(path.is_dir() for path in host_paths):
            zip_name = _safe_filename(arguments.filename or "artifacts.zip")
            if not zip_name.lower().endswith(".zip"):
                zip_name += ".zip"
            local_zip = _unique_path(output_dir / zip_name)
            with zipfile.ZipFile(local_zip, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for host_path in host_paths:
                    for file_path in _iter_host_files(host_path):
                        bundle.write(file_path, _safe_host_archive_name(cwd, file_path))
            delivered.append(local_zip)
        else:
            for index, host_path in enumerate(host_paths):
                filename = (
                    _safe_filename(arguments.filename)
                    if arguments.filename and len(host_paths) == 1
                    else _safe_filename(host_path.name or f"artifact_{index + 1}")
                )
                local_path = _unique_path(output_dir / filename)
                if host_path.resolve() == local_path.resolve():
                    delivered.append(host_path)
                else:
                    local_path.write_bytes(host_path.read_bytes())
                    delivered.append(local_path)
    except Exception as exc:
        return ToolResult(output=f"Failed to deliver host artifact: {exc}", is_error=True)

    hook = context.metadata.get("hook")
    if hook is not None:
        for local_path in delivered:
            await _call_hook_on_artifact(
                hook,
                str(local_path),
                reason=f"Delivered host artifact: {local_path.name}",
                source_tool="deliver_artifact",
                tool_use_id=_context_tool_use_id(context),
                origin="host_generated",
            )

    lines = ["Delivered artifact(s):"]
    lines.extend(f"- {path}" for path in delivered)
    return ToolResult(output="\n".join(lines), metadata={"artifact_paths": [str(path) for path in delivered]})


async def _emit_progress(
    context: ToolExecutionContext,
    phase: str,
    message: str,
    *,
    status: str = "running",
    workspace: str | None = None,
    path: str | None = None,
    detail: str | None = None,
    metadata: dict | None = None,
) -> None:
    if context.progress_callback is None:
        return
    payload = {
        "phase": phase,
        "status": status,
        "message": message,
        "workspace": workspace or ("e2b" if uses_e2b_task_workspace(context) else "host"),
    }
    if path:
        payload["path"] = path
    if detail:
        payload["detail"] = detail
    if metadata:
        payload["metadata"] = metadata
    await context.progress_callback(payload)


def _resolve_host_path(cwd: Path, path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    return candidate.resolve()


def _is_allowed_host_path(cwd: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(cwd)
        return True
    except ValueError:
        return False


def _iter_host_files(path: Path):
    if path.is_file():
        yield path
        return
    for item in path.rglob("*"):
        if item.is_file():
            yield item


def _safe_host_archive_name(cwd: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(cwd)
    except ValueError:
        rel = Path(path.name)
    parts = [_safe_filename(part) for part in rel.parts if part not in {"", ".", ".."}]
    return "/".join(parts) or "artifact"


def _resolve_output_dir(cwd: Path, thread_id: str) -> Path:
    parts = cwd.resolve().parts
    if "temp_workspaces" in parts:
        idx = parts.index("temp_workspaces")
        return Path(*parts[: idx + 1]) / thread_id
    return cwd.resolve()


def _normalize_sandbox_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def _is_allowed_sandbox_path(context: ToolExecutionContext, path: str) -> bool:
    normalized = path.rstrip("/")
    roots = sandbox_read_roots(context) if uses_e2b_task_workspace(context) else ("/home/user",)
    return any(normalized == root or normalized.startswith(root.rstrip("/") + "/") for root in roots)


async def _expand_requested_paths(session, requested_paths: list[str]) -> list[str]:
    expanded: list[str] = []
    for path in requested_paths:
        if await _sandbox_path_is_dir(session, path):
            expanded.extend(await _list_sandbox_files(session, path))
        else:
            expanded.append(path)
    return expanded


async def _sandbox_path_is_dir(session, path: str) -> bool:
    try:
        result = await session.exec_command(f"test -d {_shell_quote(path)} && printf dir || true")
        return getattr(result, "stdout_str", "").strip() == "dir"
    except Exception:
        return False


async def _list_sandbox_files(session, directory: str) -> list[str]:
    result = await session.exec_command(f"find {_shell_quote(directory)} -type f")
    output = getattr(result, "stdout_str", "") or ""
    return [line.strip() for line in output.splitlines() if line.strip()]


def _contains_directory_request(requested_paths: list[str], expanded_paths: list[str]) -> bool:
    return len(requested_paths) != len(expanded_paths)


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _ensure_bytes(content) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, bytearray):
        return bytes(content)
    if isinstance(content, memoryview):
        return content.tobytes()
    if isinstance(content, str):
        return content.encode("utf-8")
    return bytes(content)


def _safe_filename(filename: str) -> str:
    cleaned = os.path.basename(filename.strip().replace("\\", "/"))
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", cleaned).strip(" .")
    return cleaned or "artifact"


def _safe_archive_name(sandbox_path: str) -> str:
    rel = sandbox_path.removeprefix("/home/user/").strip("/")
    parts = [_safe_filename(part) for part in rel.split("/") if part not in {"", ".", ".."}]
    return "/".join(parts) or "artifact"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for idx in range(1, 1000):
        candidate = parent / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate unique path for {path}")


def _context_tool_use_id(context: ToolExecutionContext) -> str | None:
    value = context.metadata.get("tool_use_id")
    return str(value) if value else None


async def _call_hook_on_artifact(hook, file_path: str, **kwargs) -> None:
    try:
        await hook.on_artifact(file_path, **kwargs)
    except TypeError:
        legacy_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in {"reason", "sandbox_session", "url"}
        }
        await hook.on_artifact(file_path, **legacy_kwargs)
