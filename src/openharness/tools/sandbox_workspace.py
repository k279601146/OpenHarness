"""Helpers for routing task workspace file tools into E2B sandboxes."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import shlex
from pathlib import Path, PurePosixPath
from typing import Any

from openharness.sandbox import SandboxUnavailableError
from openharness.tools.base import ToolExecutionContext
from openharness.utils.paths import normalize_host_path

SANDBOX_WORKSPACE = "/home/user"
SANDBOX_SKILLS_ROOT = "/home/user/.agents/skills"
SANDBOX_ARTIFACTS_ROOT = "/home/user/artifacts"
SANDBOX_READ_ROOTS = (SANDBOX_WORKSPACE, "/code", "/tmp")
SANDBOX_WRITE_ROOTS = (SANDBOX_WORKSPACE,)


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
    return (workspace, "/code", "/tmp")


def sandbox_write_roots(context: ToolExecutionContext) -> tuple[str, ...]:
    return (sandbox_primary_workspace(context),)


def sandbox_skill_dir(context: ToolExecutionContext, skill: Any) -> str:
    raw_name = str(getattr(skill, "command_name", None) or getattr(skill, "name", None) or "skill")
    safe_name = _safe_sandbox_name(raw_name)
    return posixpath.join(sandbox_skills_root(context), safe_name)


async def ensure_skill_installed_in_sandbox(context: ToolExecutionContext, skill: Any) -> str:
    """Materialize a host-side skill package into the active E2B runtime."""
    session = await get_e2b_task_session(context)
    target_root = sandbox_skill_dir(context, skill)
    base_dir = getattr(skill, "base_dir", None)
    if not base_dir:
        return target_root

    source_dir = Path(str(base_dir)).expanduser().resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Skill package source is unavailable for {getattr(skill, 'name', 'skill')}")

    fingerprint = _skill_source_fingerprint(source_dir)
    marker_path = f"{target_root}/.openharness-sync.json"
    current = await _read_optional_sandbox_text(session, marker_path)
    if current:
        try:
            current_data = json.loads(current)
            if current_data.get("fingerprint") == fingerprint:
                return target_root
        except json.JSONDecodeError:
            pass

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
    hasher = hashlib.sha256()
    for path in sorted(item for item in source_dir.rglob("*") if item.is_file()):
        rel = path.relative_to(source_dir).as_posix()
        stat = path.stat()
        hasher.update(rel.encode("utf-8"))
        hasher.update(str(stat.st_size).encode("ascii"))
        hasher.update(str(int(stat.st_mtime_ns)).encode("ascii"))
    return hasher.hexdigest()


async def _read_optional_sandbox_text(session: Any, path: str) -> str | None:
    try:
        content = await session.read_file_binary(path)
    except Exception:
        return None
    if isinstance(content, str):
        return content
    return bytes(content).decode("utf-8", errors="replace")


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
