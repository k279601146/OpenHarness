"""Process-local E2B sandbox registry plus DB-backed lifecycle state."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import datetime
import inspect
import json
import logging
import os
import shlex
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator

if TYPE_CHECKING:
    from openharness.config import Settings
    from openharness.sandbox.e2b_backend import E2BSandboxSession

logger = logging.getLogger(__name__)
try:
    from sqlalchemy.exc import IntegrityError
except Exception:  # pragma: no cover - OpenHarness can run without SQLAlchemy.
    class IntegrityError(Exception):
        pass

USER_SCOPE = "user"
THREAD_SCOPE = "thread"
OVERFLOW_SCOPE = "overflow"

LEASE_GRACE_SECONDS = 60
SANDBOX_HOME = "/home/user"
SANDBOX_TASKS_ROOT = f"{SANDBOX_HOME}/tasks"
SANDBOX_ARTIFACTS_ROOT = f"{SANDBOX_HOME}/artifacts"
SANDBOX_SKILLS_ROOT = f"{SANDBOX_HOME}/.agents/skills"
TASK_MANIFEST_NAME = ".openharness-task.json"
DEFAULT_GC_HIGH_WATERMARK_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_GC_LOW_WATERMARK_BYTES = 6 * 1024 * 1024 * 1024
DEFAULT_TASK_TTL_DAYS = 7
DEFAULT_MIN_TASK_DIRS_TO_KEEP = 5
DEFAULT_STAGING_TTL_HOURS = 24
DEFAULT_TMP_TTL_HOURS = 24
DEFAULT_GC_CHECK_THROTTLE_SECONDS = 3600

_sandbox_registry: dict[str, E2BSandboxSession] = {}
_thread_scope_registry: dict[str, str] = {}
_gc_last_checked: dict[str, float] = {}
_registry_lock = threading.Lock()


@asynccontextmanager
async def _locked_registry() -> AsyncIterator[None]:
    """Serialize process-local registry lifecycle work across event loops."""
    while not _registry_lock.acquire(blocking=False):
        await asyncio.sleep(0.01)
    try:
        yield
    finally:
        _registry_lock.release()


def _registry_key(user_id: int, scope_type: str, scope_key: str) -> str:
    return f"{user_id}:{scope_type}:{scope_key}"


def _locked_space_query(db_session, model):
    """Build a row-lock query that does not eager-load nullable relationships."""
    return db_session.query(model).enable_eagerloads(False).with_for_update(of=model)


def _thread_key(user_id: int, thread_id: str) -> str:
    return f"{user_id}:{thread_id}"


def _task_workspace(thread_id: str) -> str:
    return f"{SANDBOX_TASKS_ROOT}/{thread_id}"


def get_active_sandbox(user_id: int, thread_id: str) -> E2BSandboxSession | None:
    """Return the active sandbox currently leased by a thread."""
    thread_key = _thread_key(user_id, thread_id)
    scope_registry_key = _thread_scope_registry.get(thread_key)
    if scope_registry_key:
        session = _sandbox_registry.get(scope_registry_key)
        if session is not None and session.is_running:
            return session

    for registry_key, session in _sandbox_registry.items():
        if not registry_key.startswith(f"{user_id}:") or not session.is_running:
            continue
        if registry_key.endswith(f":{thread_id}"):
            _thread_scope_registry[thread_key] = registry_key
            return session
    return None


def is_docker_sandbox_active_for(user_id: int, thread_id: str) -> bool:
    """Compatibility helper for callers that still use the Docker-era name."""
    return get_active_sandbox(user_id, thread_id) is not None


def is_docker_sandbox_active() -> bool:
    """Return whether any process-local sandbox is currently running."""
    return any(session.is_running for session in _sandbox_registry.values())


def get_sandbox_session() -> E2BSandboxSession | None:
    """Return the active sandbox for the current engine context when available."""
    try:
        from openharness.contextvars import active_thread_id, active_user_id

        uid = active_user_id.get()
        tid = active_thread_id.get()
        if uid and tid:
            return get_active_sandbox(uid, tid)
    except Exception:
        pass
    return None


get_docker_sandbox = get_sandbox_session


def _resolve_sandbox_data_root(settings: Settings) -> Path:
    """Resolve the local root used for sandbox mirror data."""
    if settings.sandbox.sandbox_data_root:
        return Path(settings.sandbox.sandbox_data_root)

    if os.name == "nt":
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "apps").is_dir():
                return parent / "sandbox-data"
        return Path.cwd() / "sandbox-data"

    return Path("/opt/manus/sandbox-data")


def _ensure_persistent_dirs(data_root: Path, user_id: int, space_id: str) -> tuple[str, str, str]:
    """Create local mirror directories and return workspace, home, and bin paths."""
    user_base = data_root / str(user_id)
    space_base = user_base / "spaces" / space_id

    workspace = space_base / "workspace"
    home = user_base / "shared_assets" / "user-home"
    local_bin = user_base / "shared_assets" / "local-bin"

    for directory in (workspace, home, local_bin):
        directory.mkdir(parents=True, exist_ok=True)

    return str(workspace), str(home), str(local_bin)


async def get_or_start_sandbox(
    settings: Settings,
    user_id: int,
    thread_id: str,
    db_session=None,
) -> E2BSandboxSession | None:
    """Acquire a sandbox for a task, preferring the user's reusable main sandbox."""
    from openharness.sandbox.adapter import SandboxUnavailableError
    from openharness.sandbox.e2b_backend import E2BSandboxSession, get_e2b_availability

    availability = get_e2b_availability(settings)
    if not availability.available:
        if settings.sandbox.fail_if_unavailable:
            raise SandboxUnavailableError(availability.reason or "E2B sandbox is unavailable")
        logger.warning("E2B sandbox unavailable: %s", availability.reason)
        return None

    async with _locked_registry():
        active = get_active_sandbox(user_id, thread_id)
        if active is not None:
            _touch_last_active(db_session, thread_id)
            return active

        space = _acquire_space_record(settings, user_id, thread_id, db_session)
        session = await _connect_or_create_session(settings, space, E2BSandboxSession)

        registry_key = _registry_key(user_id, space.scope_type, space.scope_key)
        _sandbox_registry[registry_key] = session
        _thread_scope_registry[_thread_key(user_id, thread_id)] = registry_key

        await _ensure_remote_task_dirs(session, thread_id)
        await _sync_local_workspace_to_task_dir(session, thread_id)
        await touch_task_manifest(session, thread_id)
        if space.scope_type == USER_SCOPE:
            await maybe_run_sandbox_gc(session, active_thread_id=thread_id)

        space.container_name = session.sandbox_id
        space.status = "running"
        space.active_thread_id = thread_id
        space.last_active_at = datetime.datetime.utcnow()
        space.lease_expires_at = _lease_expires_at(settings)
        space.template_id = settings.sandbox.template_id
        _commit(db_session)

        logger.info(
            "Sandbox acquired: sandbox=%s scope=%s key=%s thread=%s",
            session.sandbox_id,
            space.scope_type,
            space.scope_key,
            thread_id,
        )
        return session


def _acquire_space_record(settings: Settings, user_id: int, thread_id: str, db_session):
    """Find or create the DB row representing the sandbox lease target."""
    if db_session is None:
        return _ephemeral_space(user_id, thread_id, settings.sandbox.template_id)

    from models import SandboxSpace

    now = datetime.datetime.utcnow()
    main_scope_key = str(user_id)
    main = (
        _locked_space_query(db_session, SandboxSpace)
        .filter_by(user_id=user_id, scope_type=USER_SCOPE, scope_key=main_scope_key)
        .first()
    )

    if main is None:
        space_id = uuid.uuid4().hex[:16]
        ws_path, hm_path, bin_path = _ensure_persistent_dirs(
            _resolve_sandbox_data_root(settings),
            user_id,
            space_id,
        )
        main = SandboxSpace(
            id=space_id,
            user_id=user_id,
            thread_id=None,
            scope_type=USER_SCOPE,
            scope_key=main_scope_key,
            status="created",
            template_id=settings.sandbox.template_id,
            host_workspace_path=ws_path,
            host_home_path=hm_path,
            host_bin_path=bin_path,
        )
        db_session.add(main)
        try:
            _commit(db_session)
        except IntegrityError:
            db_session.rollback()
            main = (
                _locked_space_query(db_session, SandboxSpace)
                .filter_by(user_id=user_id, scope_type=USER_SCOPE, scope_key=main_scope_key)
                .first()
            )
            if main is None:
                raise

    if _space_can_be_leased(main, thread_id, now):
        main.active_thread_id = thread_id
        main.lease_expires_at = _lease_expires_at(settings)
        main.last_active_at = now
        main.template_id = settings.sandbox.template_id
        _commit(db_session)
        return main

    return _create_overflow_space(settings, user_id, thread_id, db_session)


def _space_can_be_leased(space: Any, thread_id: str, now: datetime.datetime) -> bool:
    if space.status == "destroyed":
        return False
    if space.active_thread_id in (None, "", thread_id):
        return True
    if space.lease_expires_at and space.lease_expires_at < now:
        logger.warning(
            "sandbox_lease_expired_reclaimed: scope=%s key=%s active_thread=%s",
            space.scope_type,
            space.scope_key,
            space.active_thread_id,
        )
        return True
    return False


def _create_overflow_space(settings: Settings, user_id: int, thread_id: str, db_session):
    from models import SandboxSpace

    existing = (
        _locked_space_query(db_session, SandboxSpace)
        .filter_by(user_id=user_id, scope_type=OVERFLOW_SCOPE, scope_key=thread_id)
        .first()
    )
    if existing is not None and existing.status != "destroyed":
        existing.active_thread_id = thread_id
        existing.lease_expires_at = _lease_expires_at(settings)
        existing.last_active_at = datetime.datetime.utcnow()
        existing.template_id = settings.sandbox.template_id
        _commit(db_session)
        return existing

    space_id = uuid.uuid4().hex[:16]
    ws_path, hm_path, bin_path = _ensure_persistent_dirs(
        _resolve_sandbox_data_root(settings),
        user_id,
        space_id,
    )
    space = SandboxSpace(
        id=space_id,
        user_id=user_id,
        thread_id=thread_id,
        scope_type=OVERFLOW_SCOPE,
        scope_key=thread_id,
        status="created",
        active_thread_id=thread_id,
        lease_expires_at=_lease_expires_at(settings),
        template_id=settings.sandbox.template_id,
        host_workspace_path=ws_path,
        host_home_path=hm_path,
        host_bin_path=bin_path,
    )
    db_session.add(space)
    try:
        _commit(db_session)
    except IntegrityError:
        db_session.rollback()
        existing = (
            _locked_space_query(db_session, SandboxSpace)
            .filter_by(user_id=user_id, scope_type=OVERFLOW_SCOPE, scope_key=thread_id)
            .first()
        )
        if existing is None:
            raise
        existing.active_thread_id = thread_id
        existing.lease_expires_at = _lease_expires_at(settings)
        existing.last_active_at = datetime.datetime.utcnow()
        existing.template_id = settings.sandbox.template_id
        _commit(db_session)
        return existing
    return space


def _ephemeral_space(user_id: int, thread_id: str, template_id: str):
    return type(
        "EphemeralSandboxSpace",
        (),
        {
            "id": uuid.uuid4().hex[:16],
            "user_id": user_id,
            "thread_id": thread_id,
            "scope_type": OVERFLOW_SCOPE,
            "scope_key": thread_id,
            "container_name": None,
            "status": "created",
            "active_thread_id": thread_id,
            "lease_expires_at": None,
            "template_id": template_id,
            "last_active_at": datetime.datetime.utcnow(),
        },
    )()


async def _connect_or_create_session(settings: Settings, space: Any, session_cls):
    """Resume an existing E2B sandbox, or create a replacement when resume fails."""
    if space.container_name and space.status in ("running", "suspended"):
        session = session_cls(
            settings=settings,
            template_id=settings.sandbox.template_id,
            sandbox_id=space.container_name,
        )
        try:
            await session.resume()
            return session
        except Exception as exc:
            logger.warning(
                "sandbox_resume_failed_recreated: scope=%s key=%s sandbox=%s error=%s",
                space.scope_type,
                space.scope_key,
                space.container_name,
                exc,
            )

    session = session_cls(settings=settings, template_id=settings.sandbox.template_id)
    await session.start()
    return session


async def _ensure_remote_task_dirs(session: E2BSandboxSession, thread_id: str) -> None:
    workspace = _task_workspace(thread_id)
    await session.exec_command(
        "mkdir -p "
        f"{shlex.quote(workspace)} "
        f"{shlex.quote(SANDBOX_ARTIFACTS_ROOT)} "
        f"{shlex.quote(SANDBOX_SKILLS_ROOT)}"
    )


async def _sync_local_workspace_to_task_dir(session: E2BSandboxSession, thread_id: str) -> None:
    """Upload any existing local task mirror into the sandbox task directory."""
    try:
        project_root = _project_root()
        if project_root is None:
            return
        local_ws = project_root / "temp_workspaces" / thread_id
        if not local_ws.is_dir():
            return

        target_root = _task_workspace(thread_id)
        logger.info("Syncing local workspace %s to sandbox task dir %s", local_ws, target_root)
        for root, _dirs, files in os.walk(local_ws):
            root_path = Path(root)
            rel_dir = root_path.relative_to(local_ws).as_posix()
            sandbox_dir = target_root if rel_dir == "." else f"{target_root}/{rel_dir}"
            await session.exec_command(f"mkdir -p {shlex.quote(sandbox_dir)}")
            for filename in files:
                local_file_path = root_path / filename
                rel_path = local_file_path.relative_to(local_ws).as_posix()
                sandbox_path = f"{target_root}/{rel_path}"
                try:
                    await session.write_file_binary(sandbox_path, local_file_path.read_bytes())
                except Exception as exc:
                    logger.warning("Failed to sync file %s: %s", local_file_path, exc)
    except Exception as exc:
        logger.warning("Late startup sync failed: %s", exc)


async def touch_task_manifest(
    session: E2BSandboxSession,
    thread_id: str,
    *,
    delivered_artifact_paths: list[str] | None = None,
    scanned: bool = False,
) -> None:
    """Update the task workspace manifest used by sandbox GC."""
    now = _utc_iso()
    workspace = _task_workspace(thread_id)
    manifest_path = _task_manifest_path(thread_id)
    payload = {
        "thread_id": thread_id,
        "last_active_at": now,
        "workspace_gc_eligible_at": _utc_iso(
            datetime.datetime.utcnow() + datetime.timedelta(days=DEFAULT_TASK_TTL_DAYS)
        ),
    }
    if scanned:
        payload["last_scanned_at"] = now
    if delivered_artifact_paths:
        payload["delivered_artifact_paths"] = delivered_artifact_paths

    script = (
        "python3 - <<'PY'\n"
        "import json, os\n"
        f"manifest_path = {json.dumps(manifest_path)}\n"
        f"workspace = {json.dumps(workspace)}\n"
        f"updates = json.loads({json.dumps(json.dumps(payload))})\n"
        "os.makedirs(workspace, exist_ok=True)\n"
        "data = {}\n"
        "try:\n"
        "    with open(manifest_path, 'r', encoding='utf-8') as f:\n"
        "        data = json.load(f)\n"
        "except Exception:\n"
        "    data = {}\n"
        "delivered = data.get('delivered_artifact_paths')\n"
        "if not isinstance(delivered, list):\n"
        "    delivered = []\n"
        "for path in updates.pop('delivered_artifact_paths', []) or []:\n"
        "    if path and path not in delivered:\n"
        "        delivered.append(path)\n"
        "data.update(updates)\n"
        "data['delivered_artifact_paths'] = delivered[-500:]\n"
        "tmp_path = manifest_path + '.tmp'\n"
        "with open(tmp_path, 'w', encoding='utf-8') as f:\n"
        "    json.dump(data, f, ensure_ascii=False, sort_keys=True)\n"
        "os.replace(tmp_path, manifest_path)\n"
        "PY"
    )
    try:
        await session.exec_command(script)
    except Exception as exc:
        logger.warning("Failed to update task manifest for %s: %s", thread_id, exc)


async def run_sandbox_gc(
    session: E2BSandboxSession,
    *,
    active_thread_id: str,
    high_watermark_bytes: int = DEFAULT_GC_HIGH_WATERMARK_BYTES,
    low_watermark_bytes: int = DEFAULT_GC_LOW_WATERMARK_BYTES,
    task_ttl_days: int = DEFAULT_TASK_TTL_DAYS,
    min_task_dirs_to_keep: int = DEFAULT_MIN_TASK_DIRS_TO_KEEP,
    staging_ttl_hours: int = DEFAULT_STAGING_TTL_HOURS,
    tmp_ttl_hours: int = DEFAULT_TMP_TTL_HOURS,
) -> dict[str, Any]:
    """Best-effort GC for E2B hot workspaces and staging files."""
    payload = {
        "home": SANDBOX_HOME,
        "tasks_root": SANDBOX_TASKS_ROOT,
        "artifacts_root": SANDBOX_ARTIFACTS_ROOT,
        "skills_root": SANDBOX_SKILLS_ROOT,
        "active_thread_id": active_thread_id,
        "high_watermark_bytes": int(high_watermark_bytes),
        "low_watermark_bytes": int(low_watermark_bytes),
        "task_ttl_days": int(task_ttl_days),
        "min_task_dirs_to_keep": int(min_task_dirs_to_keep),
        "staging_ttl_hours": int(staging_ttl_hours),
        "tmp_ttl_hours": int(tmp_ttl_hours),
        "manifest_name": TASK_MANIFEST_NAME,
    }
    script = _sandbox_gc_script(payload)
    try:
        result = await session.exec_command(script)
        stdout = await _process_stdout(result)
        data = json.loads(stdout or "{}")
        if data.get("deleted_task_dirs") or data.get("deleted_skill_dirs"):
            logger.info("sandbox_gc_completed: %s", data)
        return data
    except Exception as exc:
        logger.warning("Sandbox GC failed: %s", exc)
        return {"error": str(exc)}


async def maybe_run_sandbox_gc(
    session: E2BSandboxSession,
    *,
    active_thread_id: str,
    force_check: bool = False,
    throttle_seconds: int = DEFAULT_GC_CHECK_THROTTLE_SECONDS,
) -> dict[str, Any]:
    """Run the cheap high-watermark check with process-local throttling."""
    sandbox_id = str(getattr(session, "sandbox_id", None) or id(session))
    now = asyncio.get_running_loop().time()
    if not force_check and now - _gc_last_checked.get(sandbox_id, 0.0) < throttle_seconds:
        return {"skipped": "throttled"}
    _gc_last_checked[sandbox_id] = now
    return await run_sandbox_gc(session, active_thread_id=active_thread_id)


def _task_manifest_path(thread_id: str) -> str:
    return f"{_task_workspace(thread_id)}/{TASK_MANIFEST_NAME}"


def _utc_iso(value: datetime.datetime | None = None) -> str:
    current = value or datetime.datetime.utcnow()
    return current.replace(microsecond=0).isoformat() + "Z"


async def _process_stdout(process: Any) -> str:
    if hasattr(process, "communicate") and inspect.iscoroutinefunction(process.communicate):
        stdout, _stderr = await process.communicate()
        if isinstance(stdout, (bytes, bytearray)):
            return stdout.decode("utf-8", errors="replace")
        return str(stdout or "")
    stdout = getattr(process, "stdout_str", "")
    return stdout if isinstance(stdout, str) else str(stdout or "")


def _sandbox_gc_script(payload: dict[str, Any]) -> str:
    return (
        "python3 - <<'PY'\n"
        "import json, os, shutil, time\n"
        f"cfg = json.loads({json.dumps(json.dumps(payload))})\n"
        "now = time.time()\n"
        "def fs_used_bytes(path):\n"
        "    try:\n"
        "        st = os.statvfs(path)\n"
        "        return int((st.f_blocks - st.f_bfree) * st.f_frsize)\n"
        "    except OSError:\n"
        "        return 0\n"
        "result = {\n"
        "    'before_bytes': fs_used_bytes(cfg['home']),\n"
        "    'after_bytes': 0,\n"
        "    'skipped': None,\n"
        "    'deleted_task_dirs': [],\n"
        "    'deleted_staging_files': [],\n"
        "    'deleted_tmp_files': [],\n"
        "    'deleted_skill_dirs': [],\n"
        "}\n"
        "if result['before_bytes'] <= cfg['high_watermark_bytes']:\n"
        "    result['after_bytes'] = result['before_bytes']\n"
        "    result['skipped'] = 'below_high_watermark'\n"
        "    print(json.dumps(result, sort_keys=True))\n"
        "    raise SystemExit(0)\n"
        "def path_size(path):\n"
        "    total = 0\n"
        "    if not os.path.exists(path):\n"
        "        return 0\n"
        "    if os.path.isfile(path):\n"
        "        try: return os.path.getsize(path)\n"
        "        except OSError: return 0\n"
        "    for root, dirs, files in os.walk(path):\n"
        "        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]\n"
        "        for name in files:\n"
        "            file_path = os.path.join(root, name)\n"
        "            if os.path.islink(file_path):\n"
        "                continue\n"
        "            try: total += os.path.getsize(file_path)\n"
        "            except OSError: pass\n"
        "    return total\n"
        "def newest_mtime(path):\n"
        "    latest = 0.0\n"
        "    if not os.path.exists(path):\n"
        "        return latest\n"
        "    try: latest = max(latest, os.path.getmtime(path))\n"
        "    except OSError: pass\n"
        "    for root, dirs, files in os.walk(path):\n"
        "        for name in dirs + files:\n"
        "            try: latest = max(latest, os.path.getmtime(os.path.join(root, name)))\n"
        "            except OSError: pass\n"
        "    return latest\n"
        "def remove_old_files(root, older_than_seconds, bucket):\n"
        "    if not os.path.isdir(root):\n"
        "        return\n"
        "    cutoff = now - older_than_seconds\n"
        "    for current_root, dirs, files in os.walk(root, topdown=False):\n"
        "        for name in files:\n"
        "            path = os.path.join(current_root, name)\n"
        "            try:\n"
        "                if os.path.getmtime(path) < cutoff:\n"
        "                    os.remove(path)\n"
        "                    bucket.append(path)\n"
        "            except OSError:\n"
        "                pass\n"
        "        for name in dirs:\n"
        "            path = os.path.join(current_root, name)\n"
        "            try:\n"
        "                if not os.listdir(path):\n"
        "                    os.rmdir(path)\n"
        "            except OSError:\n"
        "                pass\n"
        "remove_old_files(cfg['artifacts_root'], cfg['staging_ttl_hours'] * 3600, result['deleted_staging_files'])\n"
        "remove_old_files('/tmp', cfg['tmp_ttl_hours'] * 3600, result['deleted_tmp_files'])\n"
        "home = cfg['home']\n"
        "def task_entries():\n"
        "    tasks_root = cfg['tasks_root']\n"
        "    entries = []\n"
        "    if not os.path.isdir(tasks_root):\n"
        "        return entries\n"
        "    for name in os.listdir(tasks_root):\n"
        "        path = os.path.join(tasks_root, name)\n"
        "        if not os.path.isdir(path) or name == cfg['active_thread_id']:\n"
        "            continue\n"
        "        manifest_path = os.path.join(path, cfg['manifest_name'])\n"
        "        mtime = newest_mtime(path)\n"
        "        try:\n"
        "            with open(manifest_path, 'r', encoding='utf-8') as f:\n"
        "                manifest = json.load(f)\n"
        "            raw = manifest.get('last_active_at') or ''\n"
        "            if raw.endswith('Z'):\n"
        "                from datetime import datetime\n"
        "                mtime = max(mtime, datetime.fromisoformat(raw[:-1]).timestamp())\n"
        "        except Exception:\n"
        "            pass\n"
        "        entries.append({'name': name, 'path': path, 'mtime': mtime, 'size': path_size(path)})\n"
        "    return sorted(entries, key=lambda item: item['mtime'])\n"
        "def delete_dir(path, bucket):\n"
        "    try:\n"
        "        shutil.rmtree(path)\n"
        "        bucket.append(path)\n"
        "        return True\n"
        "    except OSError:\n"
        "        return False\n"
        "entries = task_entries()\n"
        "ttl_cutoff = now - cfg['task_ttl_days'] * 86400\n"
        "while len(entries) > cfg['min_task_dirs_to_keep'] and entries and entries[0]['mtime'] < ttl_cutoff:\n"
        "    item = entries.pop(0)\n"
        "    delete_dir(item['path'], result['deleted_task_dirs'])\n"
        "current = path_size(home)\n"
        "if current > cfg['high_watermark_bytes']:\n"
        "    entries = task_entries()\n"
        "    while len(entries) > cfg['min_task_dirs_to_keep'] and current > cfg['low_watermark_bytes']:\n"
        "        item = entries.pop(0)\n"
        "        if delete_dir(item['path'], result['deleted_task_dirs']):\n"
        "            current = max(0, current - item['size'])\n"
        "if path_size(home) > cfg['high_watermark_bytes'] and os.path.isdir(cfg['skills_root']):\n"
        "    skills = []\n"
        "    for name in os.listdir(cfg['skills_root']):\n"
        "        path = os.path.join(cfg['skills_root'], name)\n"
        "        if os.path.isdir(path):\n"
        "            skills.append({'path': path, 'mtime': newest_mtime(path), 'size': path_size(path)})\n"
        "    skills.sort(key=lambda item: item['mtime'])\n"
        "    current = path_size(home)\n"
        "    while skills and current > cfg['low_watermark_bytes']:\n"
        "        item = skills.pop(0)\n"
        "        if delete_dir(item['path'], result['deleted_skill_dirs']):\n"
        "            current = max(0, current - item['size'])\n"
        "result['after_bytes'] = path_size(home)\n"
        "print(json.dumps(result, sort_keys=True))\n"
        "PY"
    )


def _project_root() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "apps").is_dir():
            return parent
    return None


def _lease_expires_at(settings: Settings) -> datetime.datetime:
    ttl = int(getattr(settings.sandbox, "idle_timeout_seconds", 300) or 300)
    return datetime.datetime.utcnow() + datetime.timedelta(seconds=ttl + LEASE_GRACE_SECONDS)


async def suspend_sandbox(user_id: int, thread_id: str, db_session=None) -> None:
    """Release the sandbox lease held by a task."""
    async with _locked_registry():
        await _suspend_sandbox_locked(user_id, thread_id, db_session)


async def _suspend_sandbox_locked(user_id: int, thread_id: str, db_session: Any) -> None:
    thread_key = _thread_key(user_id, thread_id)
    registry_key = _thread_scope_registry.pop(thread_key, None)
    session = _sandbox_registry.pop(registry_key, None) if registry_key else None
    space = _find_space_for_thread(db_session, user_id, thread_id)

    if space is not None and space.scope_type == OVERFLOW_SCOPE:
        if session is not None:
            await session.destroy()
        elif space.container_name:
            from openharness.config import Settings
            from openharness.sandbox.e2b_backend import E2BSandboxSession

            overflow_session = E2BSandboxSession(
                settings=Settings(),
                template_id=space.template_id or "",
                sandbox_id=space.container_name,
            )
            await overflow_session.destroy()
        space.status = "destroyed"
        space.destroyed_at = datetime.datetime.utcnow()
        space.active_thread_id = None
        space.lease_expires_at = None
        _commit(db_session)
        return

    if session is not None:
        await maybe_run_sandbox_gc(session, active_thread_id=thread_id, force_check=True)
        await session.suspend()

    if space is not None:
        space.status = "suspended"
        space.active_thread_id = None
        space.lease_expires_at = None
        space.last_active_at = datetime.datetime.utcnow()
        _commit(db_session)


async def destroy_sandbox(user_id: int, thread_id: str, db_session=None) -> None:
    """Destroy the sandbox currently associated with a task."""
    async with _locked_registry():
        await _destroy_sandbox_locked(user_id, thread_id, db_session)


async def _destroy_sandbox_locked(user_id: int, thread_id: str, db_session: Any) -> None:
    thread_key = _thread_key(user_id, thread_id)
    registry_key = _thread_scope_registry.pop(thread_key, None)
    session = _sandbox_registry.pop(registry_key, None) if registry_key else None
    if session is not None:
        await session.destroy()

    space = _find_space_for_thread(db_session, user_id, thread_id)
    if space is not None:
        space.status = "destroyed"
        space.active_thread_id = None
        space.lease_expires_at = None
        space.destroyed_at = datetime.datetime.utcnow()
        _commit(db_session)


async def stop_docker_sandbox() -> None:
    """Legacy no-op retained for UI shutdown compatibility."""
    pass


def _find_space_for_thread(db_session, user_id: int, thread_id: str):
    if db_session is None:
        return None
    try:
        from models import SandboxSpace

        return (
            db_session.query(SandboxSpace)
            .filter(
                SandboxSpace.user_id == user_id,
                SandboxSpace.active_thread_id == thread_id,
                SandboxSpace.status.in_(["running", "suspended", "created"]),
            )
            .order_by(SandboxSpace.scope_type.desc())
            .first()
        )
    except Exception as exc:
        logger.warning("Failed to find SandboxSpace for thread release: %s", exc)
        return None


def _touch_last_active(db_session, thread_id: str) -> None:
    """Update last_active_at for the sandbox associated with a thread."""
    if db_session is None:
        return
    try:
        space = _find_space_for_thread(db_session, 0, thread_id)
        if space is None:
            from models import SandboxSpace

            space = (
                db_session.query(SandboxSpace)
                .filter(
                    (SandboxSpace.active_thread_id == thread_id)
                    | (SandboxSpace.thread_id == thread_id)
                    | ((SandboxSpace.scope_type == OVERFLOW_SCOPE) & (SandboxSpace.scope_key == thread_id))
                )
                .first()
            )
        if space:
            space.last_active_at = datetime.datetime.utcnow()
            _commit(db_session)
    except Exception:
        pass


def _commit(db_session) -> None:
    if db_session is not None:
        db_session.commit()
