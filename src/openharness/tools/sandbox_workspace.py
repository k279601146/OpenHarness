"""Helpers for routing task workspace file tools into E2B sandboxes."""

from __future__ import annotations

import asyncio
import io
import json
import os
import posixpath
import re
import shlex
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, Awaitable, TypeVar

from openharness.config.paths import get_data_dir
from openharness.sandbox import SandboxUnavailableError
from openharness.skills.fingerprint import iter_skill_source_files, skill_source_fingerprint
from openharness.tools.base import ToolExecutionContext
from openharness.utils.paths import normalize_host_path

SANDBOX_WORKSPACE = "/home/user"
SANDBOX_TASKS_ROOT = "/home/user/tasks"
SANDBOX_SKILLS_ROOT = "/home/user/.agents/skills"
SANDBOX_ARTIFACTS_ROOT = "/home/user/artifacts"
SANDBOX_READ_ROOTS = (SANDBOX_WORKSPACE, "/code", "/tmp")
SANDBOX_WRITE_ROOTS = (SANDBOX_WORKSPACE,)
SKILL_ARCHIVE_SYNC_FILE_THRESHOLD = 128
SKILL_ARCHIVE_SYNC_SIZE_THRESHOLD = 8 * 1024 * 1024
SKILL_SYNC_PROGRESS_INTERVAL_SECONDS = 8.0
BUNDLED_SKILL_CONTENT_ROOT = Path(__file__).resolve().parents[1] / "skills" / "bundled" / "content"
BUNDLED_PLUGIN_CONTENT_ROOT = Path(__file__).resolve().parents[1] / "plugins" / "bundled" / "content"

T = TypeVar("T")


async def _emit_progress(
    context: ToolExecutionContext,
    phase: str,
    message: str,
    *,
    status: str = "running",
    path: str | None = None,
    detail: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if context.progress_callback is None:
        return
    payload: dict[str, Any] = {
        "phase": phase,
        "status": status,
        "message": message,
        "workspace": "e2b" if uses_e2b_task_workspace(context) else "host",
    }
    if path:
        payload["path"] = path
    if detail:
        payload["detail"] = detail
    if metadata:
        payload["metadata"] = metadata
    await context.progress_callback(payload)


async def _await_with_progress(
    awaitable: Awaitable[T],
    context: ToolExecutionContext,
    phase: str,
    message: str,
    *,
    path: str | None = None,
    detail: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> T:
    task = asyncio.create_task(awaitable)
    started = time.monotonic()
    while True:
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=SKILL_SYNC_PROGRESS_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            elapsed = int(time.monotonic() - started)
            heartbeat_detail = f"{detail}; elapsed {elapsed}s" if detail else f"elapsed {elapsed}s"
            await _emit_progress(
                context,
                phase,
                message,
                path=path,
                detail=heartbeat_detail,
                metadata=metadata,
            )
        except asyncio.CancelledError:
            task.cancel()
            raise


def uses_e2b_task_workspace(context: ToolExecutionContext) -> bool:
    metadata = context.metadata or {}
    explicit_backend = metadata.get("workspace_backend")
    if explicit_backend is not None:
        return str(explicit_backend).lower() == "e2b"

    settings = metadata.get("settings")
    sandbox = getattr(settings, "sandbox", None)
    return bool(
        getattr(sandbox, "enabled", False)
        and getattr(sandbox, "backend", None) == "e2b"
        and metadata.get("user_id") is not None
        and metadata.get("thread_id")
    )


async def get_e2b_task_session(context: ToolExecutionContext):
    if not uses_e2b_task_workspace(context):
        return None
    metadata = context.metadata or {}
    if metadata.get("user_id") is None or not metadata.get("thread_id"):
        raise SandboxUnavailableError("E2B workspace requires user_id and thread_id")
    if metadata.get("settings") is None:
        raise SandboxUnavailableError("E2B workspace requires sandbox settings")

    from openharness.sandbox.session import get_active_sandbox, get_or_start_sandbox

    user_id = int(metadata["user_id"])
    thread_id = str(metadata["thread_id"])
    session = get_active_sandbox(user_id, thread_id)
    if session is None:
        session = await get_or_start_sandbox(
            metadata["settings"],
            user_id,
            thread_id,
            db_session=metadata.get("db_session"),
        )
    if session is None or not session.is_running:
        raise SandboxUnavailableError("E2B task workspace is not running")
    return session


def to_sandbox_path(
    context: ToolExecutionContext,
    candidate: str | None,
    *,
    for_write: bool = False,
) -> str:
    workspace = sandbox_primary_workspace(context)
    raw = str(candidate or ".").strip()
    if raw in {"", ".", "~"}:
        path = workspace
    elif _looks_like_windows_path(raw):
        path = _host_path_to_sandbox_path(context.cwd, raw, workspace=workspace)
    else:
        normalized = raw.replace("\\", "/")
        if normalized.startswith("/"):
            path = posixpath.normpath(normalized)
        else:
            path = posixpath.normpath(posixpath.join(workspace, normalized))

    roots = sandbox_write_roots(context) if for_write else sandbox_read_roots(context)
    if not _is_under_any(path, roots):
        scope = "write" if for_write else "read/search"
        allowed = ", ".join(roots)
        raise ValueError(f"Sandbox path is outside the allowed {scope} roots ({allowed}): {path}")
    return path


def sandbox_primary_workspace(context: ToolExecutionContext) -> str:
    value = str((context.metadata or {}).get("primary_workspace") or SANDBOX_WORKSPACE).strip()
    if not value.startswith("/"):
        return SANDBOX_WORKSPACE
    return posixpath.normpath(value) or SANDBOX_WORKSPACE


def sandbox_task_workspace(thread_id: str) -> str:
    return posixpath.join(SANDBOX_TASKS_ROOT, str(thread_id).strip("/"))


def sandbox_skills_root(context: ToolExecutionContext) -> str:
    value = str((context.metadata or {}).get("sandbox_skills_root") or SANDBOX_SKILLS_ROOT).strip()
    if not value.startswith("/"):
        return SANDBOX_SKILLS_ROOT
    return posixpath.normpath(value) or SANDBOX_SKILLS_ROOT


def sandbox_artifacts_root(context: ToolExecutionContext) -> str:
    value = str((context.metadata or {}).get("sandbox_artifacts_root") or SANDBOX_ARTIFACTS_ROOT).strip()
    if not value.startswith("/"):
        return SANDBOX_ARTIFACTS_ROOT
    return posixpath.normpath(value) or SANDBOX_ARTIFACTS_ROOT


def sandbox_read_roots(context: ToolExecutionContext) -> tuple[str, ...]:
    workspace = sandbox_primary_workspace(context)
    skills = sandbox_skills_root(context)
    artifacts = sandbox_artifacts_root(context)
    return (workspace, skills, artifacts, "/code", "/tmp")


def sandbox_write_roots(context: ToolExecutionContext) -> tuple[str, ...]:
    workspace = sandbox_primary_workspace(context)
    artifacts = sandbox_artifacts_root(context)
    return (workspace, artifacts)


def sandbox_skill_dir(context: ToolExecutionContext, skill: Any) -> str:
    raw_name = str(getattr(skill, "command_name", None) or getattr(skill, "name", None) or "skill")
    safe_name = _safe_sandbox_name(raw_name)
    return posixpath.join(sandbox_skills_root(context), safe_name)


def preinstalled_bundled_skill_dir(context: ToolExecutionContext, skill: Any) -> str | None:
    """Return the sandbox path for bundled skills baked into the E2B template."""
    source = getattr(skill, "source", None)
    if source not in {"bundled", "plugin"}:
        return None
    base_dir = getattr(skill, "base_dir", None)
    if not base_dir:
        return None
    try:
        source_dir = Path(str(base_dir)).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    roots = [BUNDLED_SKILL_CONTENT_ROOT]
    if source == "plugin":
        roots = [BUNDLED_PLUGIN_CONTENT_ROOT]
    for root in roots:
        try:
            source_dir.relative_to(root.resolve())
            return sandbox_skill_dir(context, skill)
        except (OSError, RuntimeError, ValueError):
            continue
    return None


async def ensure_skill_installed_in_sandbox(context: ToolExecutionContext, skill: Any) -> str:
    """Materialize a host-side skill package into the active E2B runtime."""
    skill_name = str(getattr(skill, "command_name", None) or getattr(skill, "name", None) or "skill")
    await _emit_progress(context, "sandbox_start", "正在准备 E2B 沙箱...", metadata={"skill": skill_name})
    session = await get_e2b_task_session(context)
    target_root = sandbox_skill_dir(context, skill)
    base_dir = getattr(skill, "base_dir", None)
    if not base_dir:
        await _emit_progress(
            context,
            "skill_ready",
            f"技能 {skill_name} 已可用。",
            status="success",
            path=target_root,
            metadata={"skill": skill_name},
        )
        return target_root

    source_dir = Path(str(base_dir)).expanduser().resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Skill package source is unavailable for {getattr(skill, 'name', 'skill')}")

    fingerprint = _skill_source_fingerprint(source_dir)
    marker_path = f"{target_root}/.openharness-sync.json"
    await _emit_progress(
        context,
        "skill_check",
        f"正在检查沙箱中的 {skill_name} 技能缓存...",
        path=target_root,
        metadata={"skill": skill_name},
    )
    current = await _read_optional_sandbox_text(session, marker_path)
    if current:
        try:
            current_data = json.loads(current)
            if current_data.get("fingerprint") == fingerprint:
                await _emit_progress(
                    context,
                    "skill_ready",
                    f"沙箱中已有最新的 {skill_name} 技能，直接复用。",
                    status="success",
                    path=target_root,
                    metadata={"skill": skill_name, "cache_hit": True},
                )
                return target_root
        except json.JSONDecodeError:
            pass

    manifest = _skill_source_manifest(source_dir)
    if _should_archive_sync(manifest):
        await _sync_skill_archive(session, source_dir, target_root, fingerprint, context=context, skill_name=skill_name, manifest=manifest)
        await _touch_sandbox_last_active(context)
        await _emit_progress(
            context,
            "skill_ready",
            f"技能 {skill_name} 已同步到沙箱。",
            status="success",
            path=target_root,
            metadata={"skill": skill_name, **manifest},
        )
        return target_root

    await _emit_progress(
        context,
        "skill_upload",
        f"正在同步 {skill_name} 技能文件到 E2B 沙箱...",
        path=target_root,
        detail=f"{manifest['file_count']} files, {manifest['total_size']} bytes",
        metadata={"skill": skill_name, **manifest},
    )
    await session.exec_command(f"mkdir -p {shlex.quote(target_root)}")
    for root, dirs, files in os.walk(source_dir):
        root_path = Path(root)
        rel_dir = root_path.relative_to(source_dir).as_posix()
        sandbox_dir = target_root if rel_dir == "." else f"{target_root}/{rel_dir}"
        await session.exec_command(f"mkdir -p {shlex.quote(sandbox_dir)}")
        for dirname in dirs:
            await session.exec_command(f"mkdir -p {shlex.quote(f'{sandbox_dir}/{dirname}')}")
        for filename in files:
            local_path = root_path / filename
            sandbox_path = f"{sandbox_dir}/{filename}"
            content = local_path.read_bytes()
            if hasattr(session, "write_file_binary"):
                await session.write_file_binary(sandbox_path, content)
            else:
                await session.write_file(sandbox_path, content.decode("utf-8", errors="replace"))

    await session.write_file(
        marker_path,
        json.dumps({"fingerprint": fingerprint}, ensure_ascii=False, sort_keys=True),
    )
    await session.exec_command(
        f"find {shlex.quote(target_root + '/scripts')} -type f -name '*.py' "
        "-exec chmod +x {} \\; 2>/dev/null || true"
    )
    await _touch_sandbox_last_active(context)
    await _emit_progress(
        context,
        "skill_ready",
        f"技能 {skill_name} 已同步到沙箱。",
        status="success",
        path=target_root,
        metadata={"skill": skill_name, **manifest},
    )
    return target_root


async def sandbox_path_status(session: Any, path: str) -> str:
    quoted = shlex.quote(path)
    process = await session.exec_command(
        f"if test -d {quoted}; then printf dir; "
        f"elif test -f {quoted}; then printf file; "
        f"elif test -e {quoted}; then printf other; "
        "else printf missing; fi"
    )
    stdout, _stderr = await process.communicate()
    return stdout.decode("utf-8", errors="replace").strip() or "missing"


async def sandbox_file_size(session: Any, path: str) -> int:
    process = await session.exec_command(f"stat -c %s {shlex.quote(path)} 2>/dev/null || printf 0")
    stdout, _stderr = await process.communicate()
    try:
        return int(stdout.decode("utf-8", errors="replace").strip() or "0")
    except ValueError:
        return 0


async def sandbox_glob(session: Any, root: str, pattern: str, *, limit: int) -> list[str]:
    payload = json.dumps({"root": root, "pattern": pattern, "limit": limit})
    script = (
        "python3 - <<'PY'\n"
        "import glob, json, os\n"
        f"data = json.loads({json.dumps(payload)})\n"
        "root = os.path.normpath(data['root'])\n"
        "pattern = data['pattern'] or '*'\n"
        "limit = int(data['limit'])\n"
        "matches = glob.glob(os.path.join(root, pattern), recursive=True)\n"
        "rendered = []\n"
        "for path in sorted(matches):\n"
        "    rel = os.path.relpath(path, root)\n"
        "    rendered.append(rel if rel != '.' else os.path.basename(path))\n"
        "    if len(rendered) >= limit:\n"
        "        break\n"
        "print('\\n'.join(rendered))\n"
        "PY"
    )
    process = await session.exec_command(script)
    stdout, _stderr = await process.communicate()
    text = stdout.decode("utf-8", errors="replace").strip()
    return [line for line in text.splitlines() if line]


async def sandbox_grep(
    session: Any,
    root: str,
    *,
    pattern: str,
    file_glob: str,
    case_sensitive: bool,
    limit: int,
) -> str:
    payload = json.dumps(
        {
            "root": root,
            "pattern": pattern,
            "file_glob": file_glob or "**/*",
            "case_sensitive": case_sensitive,
            "limit": limit,
        }
    )
    script = (
        "python3 - <<'PY'\n"
        "import glob, json, os, re\n"
        f"data = json.loads({json.dumps(payload)})\n"
        "root = os.path.normpath(data['root'])\n"
        "flags = 0 if data['case_sensitive'] else re.IGNORECASE\n"
        "try:\n"
        "    rx = re.compile(data['pattern'], flags)\n"
        "except re.error as exc:\n"
        "    print(f\"(invalid regex pattern {data['pattern']!r}: {exc})\")\n"
        "    raise SystemExit(0)\n"
        "paths = [root] if os.path.isfile(root) else glob.glob(os.path.join(root, data['file_glob']), recursive=True)\n"
        "count = 0\n"
        "for path in sorted(paths):\n"
        "    if count >= int(data['limit']):\n"
        "        break\n"
        "    if not os.path.isfile(path):\n"
        "        continue\n"
        "    try:\n"
        "        raw = open(path, 'rb').read()\n"
        "    except OSError:\n"
        "        continue\n"
        "    if b'\\x00' in raw:\n"
        "        continue\n"
        "    text = raw.decode('utf-8', errors='replace')\n"
        "    rel = os.path.relpath(path, root if os.path.isdir(root) else os.path.dirname(root))\n"
        "    for line_no, line in enumerate(text.splitlines(), 1):\n"
        "        if rx.search(line):\n"
        "            print(f\"{rel}:{line_no}:{line}\")\n"
        "            count += 1\n"
        "            if count >= int(data['limit']):\n"
        "                break\n"
        "if count == 0:\n"
        "    print('(no matches)')\n"
        "PY"
    )
    process = await session.exec_command(script)
    stdout, _stderr = await process.communicate()
    return stdout.decode("utf-8", errors="replace").strip() or "(no matches)"


def _looks_like_windows_path(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("\\\\"))


def _host_path_to_sandbox_path(cwd: Path, value: str, *, workspace: str) -> str:
    host_path = normalize_host_path(cwd, value)
    try:
        rel = host_path.relative_to(Path(cwd).resolve())
    except ValueError as exc:
        raise ValueError(f"Host path is outside the task workspace and cannot be mapped to E2B: {host_path}") from exc
    rel_posix = PurePosixPath(*rel.parts).as_posix()
    return posixpath.normpath(posixpath.join(workspace, rel_posix))


def _is_under_any(path: str, roots: tuple[str, ...]) -> bool:
    normalized = posixpath.normpath(path)
    return any(normalized == root or normalized.startswith(root.rstrip("/") + "/") for root in roots)


def _safe_sandbox_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    return cleaned or "skill"


def _skill_source_fingerprint(source_dir: Path) -> str:
    return skill_source_fingerprint(source_dir)


async def _read_optional_sandbox_text(session: Any, path: str) -> str | None:
    try:
        process = await session.exec_command(
            f"if test -f {shlex.quote(path)}; then cat {shlex.quote(path)}; fi"
        )
        stdout, _stderr = await process.communicate()
    except Exception:
        return None
    text = stdout.decode("utf-8", errors="replace") if isinstance(stdout, (bytes, bytearray)) else str(stdout)
    return text or None


def _iter_skill_files(source_dir: Path):
    for path in iter_skill_source_files(source_dir):
        yield path, path.relative_to(source_dir).as_posix(), path.stat()


def _skill_source_manifest(source_dir: Path) -> dict[str, int]:
    total_size = 0
    file_count = 0
    for _path, _rel, stat in _iter_skill_files(source_dir):
        file_count += 1
        total_size += stat.st_size
    return {"file_count": file_count, "total_size": total_size}


def _should_archive_sync(manifest: dict[str, int]) -> bool:
    return (
        manifest["file_count"] >= SKILL_ARCHIVE_SYNC_FILE_THRESHOLD
        or manifest["total_size"] >= SKILL_ARCHIVE_SYNC_SIZE_THRESHOLD
    )


def _skill_archive_cache_path(skill_safe_name: str, fingerprint: str) -> Path:
    cache_dir = get_data_dir() / "skill_archives"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{skill_safe_name}-{fingerprint}.tar.gz"


def _write_skill_archive(source_dir: Path, archive_path: Path, marker_payload: str) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f"{archive_path.name}.", suffix=".tmp", dir=archive_path.parent, delete=False) as tmp:
        temp_path = Path(tmp.name)
    try:
        with tarfile.open(temp_path, "w:gz") as archive:
            for path, rel, _stat in _iter_skill_files(source_dir):
                archive.add(path, arcname=rel, recursive=False)
            marker_info = tarfile.TarInfo(".openharness-sync.json")
            marker_bytes = marker_payload.encode("utf-8")
            marker_info.size = len(marker_bytes)
            marker_info.mode = 0o644
            archive.addfile(marker_info, io.BytesIO(marker_bytes))
        os.replace(temp_path, archive_path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


async def _get_or_create_skill_archive(
    source_dir: Path,
    safe_name: str,
    fingerprint: str,
    marker_payload: str,
    *,
    context: ToolExecutionContext,
    skill_name: str,
    target_root: str,
    manifest: dict[str, int],
) -> tuple[Path, bool]:
    archive_path = _skill_archive_cache_path(safe_name, fingerprint)
    if archive_path.exists() and archive_path.stat().st_size > 0:
        await _emit_progress(
            context,
            "skill_package",
            f"已复用本地缓存的 {skill_name} 技能归档。",
            status="success",
            path=target_root,
            detail=f"{archive_path.stat().st_size} bytes",
            metadata={"skill": skill_name, "archive_cache_hit": True, **manifest},
        )
        return archive_path, True

    package_detail = f"{manifest['file_count']} files, {manifest['total_size']} bytes"
    await _emit_progress(
        context,
        "skill_package",
        f"正在打包 {skill_name} 技能文件...",
        path=target_root,
        detail=package_detail,
        metadata={"skill": skill_name, "archive_cache_hit": False, **manifest},
    )
    await _await_with_progress(
        asyncio.to_thread(_write_skill_archive, source_dir, archive_path, marker_payload),
        context,
        "skill_package",
        f"正在打包 {skill_name} 技能文件...",
        path=target_root,
        detail=package_detail,
        metadata={"skill": skill_name, "archive_cache_hit": False, **manifest},
    )
    await _emit_progress(
        context,
        "skill_package",
        f"{skill_name} 技能归档已打包完成。",
        status="success",
        path=target_root,
        detail=f"{archive_path.stat().st_size} bytes",
        metadata={"skill": skill_name, "archive_cache_hit": False, "archive_size": archive_path.stat().st_size, **manifest},
    )
    return archive_path, False


async def _sync_skill_archive(
    session: Any,
    source_dir: Path,
    target_root: str,
    fingerprint: str,
    *,
    context: ToolExecutionContext,
    skill_name: str,
    manifest: dict[str, int],
) -> None:
    safe_name = _safe_sandbox_name(source_dir.name)
    sandbox_archive_path = f"/tmp/openharness-skill-{safe_name}-{fingerprint[:12]}.tar.gz"
    temp_target = f"{target_root}.tmp-{fingerprint[:12]}"
    marker_payload = json.dumps({"fingerprint": fingerprint}, ensure_ascii=False, sort_keys=True)

    local_archive, cache_hit = await _get_or_create_skill_archive(
        source_dir,
        safe_name,
        fingerprint,
        marker_payload,
        context=context,
        skill_name=skill_name,
        target_root=target_root,
        manifest=manifest,
    )
    archive_size = local_archive.stat().st_size
    await _emit_progress(
        context,
        "skill_upload",
        f"正在上传 {skill_name} 技能归档到 E2B 沙箱...",
        path=sandbox_archive_path,
        detail=f"{archive_size} bytes",
        metadata={"skill": skill_name, "archive_size": archive_size, "archive_cache_hit": cache_hit, **manifest},
    )
    archive_bytes = await _await_with_progress(
        asyncio.to_thread(local_archive.read_bytes),
        context,
        "skill_upload",
        f"正在读取 {skill_name} 技能归档准备上传...",
        path=sandbox_archive_path,
        detail=f"{archive_size} bytes",
        metadata={"skill": skill_name, "archive_size": archive_size, "archive_cache_hit": cache_hit, **manifest},
    )
    await _await_with_progress(
        session.write_file_binary(sandbox_archive_path, archive_bytes),
        context,
        "skill_upload",
        f"正在上传 {skill_name} 技能归档到 E2B 沙箱...",
        path=sandbox_archive_path,
        detail=f"{archive_size} bytes",
        metadata={"skill": skill_name, "archive_size": archive_size, "archive_cache_hit": cache_hit, **manifest},
    )
    await _emit_progress(
        context,
        "skill_extract",
        f"正在沙箱内解压安装 {skill_name} 技能...",
        path=target_root,
        metadata={"skill": skill_name, **manifest},
    )
    command = (
        "set -e; "
        f"trap 'rm -f {shlex.quote(sandbox_archive_path)}' EXIT; "
        f"rm -rf {shlex.quote(temp_target)} && "
        f"mkdir -p {shlex.quote(temp_target)} && "
        f"tar -xzf {shlex.quote(sandbox_archive_path)} -C {shlex.quote(temp_target)} && "
        f"rm -rf {shlex.quote(target_root)} && "
        f"mv {shlex.quote(temp_target)} {shlex.quote(target_root)} && "
        f"(test -d {shlex.quote(target_root + '/scripts')} && "
        f"find {shlex.quote(target_root + '/scripts')} -type f -name '*.py' "
        "-exec chmod +x {} \\; 2>/dev/null || true)"
    )
    process = await _await_with_progress(
        session.exec_command(command),
        context,
        "skill_extract",
        f"正在沙箱内解压安装 {skill_name} 技能...",
        path=target_root,
        metadata={"skill": skill_name, **manifest},
    )
    stdout, stderr = await _await_with_progress(
        process.communicate(),
        context,
        "skill_extract",
        f"正在沙箱内解压安装 {skill_name} 技能...",
        path=target_root,
        metadata={"skill": skill_name, **manifest},
    )
    if getattr(process, "returncode", 0) != 0:
        details = (stderr or stdout or b"").decode("utf-8", errors="replace")
        raise RuntimeError(f"Failed to extract skill archive in sandbox: {details.strip()}")


async def _touch_sandbox_last_active(context: ToolExecutionContext) -> None:
    metadata = context.metadata or {}
    db_session = metadata.get("db_session")
    thread_id = metadata.get("thread_id")
    if db_session is None or not thread_id:
        return
    try:
        from openharness.sandbox.session import _touch_last_active

        _touch_last_active(db_session, str(thread_id))
    except Exception:
        return
