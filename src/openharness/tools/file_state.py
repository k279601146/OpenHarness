"""Shared file safety, locking, line-ending, diff, and observation helpers."""

from __future__ import annotations

import asyncio
import codecs
import difflib
import hashlib
import posixpath
import shlex
import uuid
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Literal

READ_MAX_LINE_LENGTH = 2000
READ_MAX_BYTES = 50 * 1024
READ_STREAM_MIN_SIZE = 10 * 1024 * 1024
BINARY_SNIFF_BYTES = 8192

LineEnding = Literal["\n", "\r\n"]

DANGEROUS_PATH_PARTS = frozenset({
    ".git",
    ".ssh",
    ".aws",
    ".azure",
    ".gcp",
    "credentials",
    "secrets",
})

DANGEROUS_FILE_NAMES = frozenset({
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "private.key",
    "secrets.yaml",
    "secrets.yml",
})

_OBSERVATION_METADATA_KEY = "_file_observations"
_MAX_VERSION_HASH_BYTES = 1024 * 1024

_LOOP_LOCKS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]] = (
    weakref.WeakKeyDictionary()
)


@dataclass(frozen=True)
class FileObservation:
    """Observed state of a workspace file in the current session."""

    kind: Literal["present", "absent"]
    version: str | None = None


@asynccontextmanager
async def file_lock(key: str) -> AsyncIterator[None]:
    """Serialize async mutations targeting the same path within an event loop."""
    loop = asyncio.get_running_loop()
    locks = _LOOP_LOCKS.get(loop)
    if locks is None:
        locks = {}
        _LOOP_LOCKS[loop] = locks
    lock = locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        locks[key] = lock
    async with lock:
        yield


def detect_line_endings(text: str) -> LineEnding:
    """Detect whether text primarily uses CRLF or LF line endings."""
    return "\r\n" if "\r\n" in text else "\n"


def normalize_line_endings(text: str) -> str:
    """Convert CRLF line endings to LF for uniform matching and patching."""
    return text.replace("\r\n", "\n")


def restore_line_endings(text: str, eol: LineEnding) -> str:
    """Restore target line endings without introducing doubled CR bytes."""
    normalized = normalize_line_endings(text)
    if eol == "\r\n":
        return normalized.replace("\n", "\r\n")
    return normalized


def is_sensitive_path(rel_parts: tuple[str, ...], file_name: str) -> bool:
    """Return True if a path touches sensitive VCS, cloud, key, or env files."""
    for part in rel_parts:
        lower = part.lower()
        if lower in DANGEROUS_PATH_PARTS or lower in DANGEROUS_FILE_NAMES:
            return True
        if lower == ".env" or lower.startswith(".env."):
            return True
    lower_name = file_name.lower()
    return (
        lower_name in DANGEROUS_FILE_NAMES
        or lower_name == ".env"
        or lower_name.startswith(".env.")
    )


def validate_host_workspace_path(
    path: Path,
    workspace: Path,
    *,
    allow_missing: bool = False,
    operation: str = "modify",
) -> str | None:
    """Validate that a host file path stays within workspace and avoids sensitive paths."""
    resolved_workspace = workspace.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    try:
        rel = resolved_path.relative_to(resolved_workspace)
    except ValueError:
        return f"Refusing to {operation} file outside workspace ({resolved_workspace}): {path}"

    if is_sensitive_path(rel.parts, resolved_path.name):
        return f"Refusing to {operation} sensitive file: {path}"

    if path.exists() and path.is_dir():
        return f"Target path is a directory, not a file: {path}"
    if resolved_path.exists() and resolved_path.is_dir():
        return f"Target path is a directory, not a file: {path}"

    if not allow_missing:
        if not path.exists():
            return f"File not found: {path}"
        if not path.is_file():
            return f"Target path is not a regular file: {path}"
    elif path.exists() and not path.is_file():
        return f"Target path is not a regular file: {path}"

    return None


def compute_unified_diff(filename: str, original: str, updated: str) -> tuple[str, int, int]:
    """Compute a unified diff with LF-normalized comparison and added/removed line counts."""
    orig_lines = normalize_line_endings(original).splitlines()
    new_lines = normalize_line_endings(updated).splitlines()
    diff_lines = list(
        difflib.unified_diff(
            orig_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
        )
    )
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    return "\n".join(diff_lines), added, removed


def bytes_version(data: bytes) -> str:
    """Return a deterministic content version token for an in-memory payload."""
    digest = hashlib.sha256(data).hexdigest()[:16]
    return f"bytes:{len(data)}:{digest}"


def host_file_version(path: Path) -> str | None:
    """Return a version token for a host file, or None if the path does not exist."""
    try:
        st = path.stat()
    except OSError:
        return None
    base = f"stat:{st.st_dev}:{st.st_ino}:{st.st_size}:{st.st_mtime_ns}:{st.st_ctime_ns}"
    if st.st_size <= _MAX_VERSION_HASH_BYTES:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            return f"{base}:{digest}"
        except OSError:
            return base
    return base


def _observation_store(context: Any, *, create: bool = False) -> dict[str, FileObservation] | None:
    metadata = getattr(context, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    store = metadata.get(_OBSERVATION_METADATA_KEY)
    if store is None and create:
        store = {}
        metadata[_OBSERVATION_METADATA_KEY] = store
    return store if isinstance(store, dict) else None


def host_observation_key(path: Path) -> str:
    """Normalize a host path into a stable session observation key."""
    return f"host:{path.resolve(strict=False)}"


def sandbox_observation_key(sandbox_path: str) -> str:
    """Normalize an E2B sandbox path into a stable session observation key."""
    return f"e2b:{posixpath.normpath(sandbox_path)}"


def observe_file(context: Any, key: str, version: str) -> None:
    """Record that a file was observed or written at a specific version."""
    store = _observation_store(context, create=True)
    if store is not None:
        store[key] = FileObservation(kind="present", version=version)


def observe_absent(context: Any, key: str) -> None:
    """Record that a path was observed to be absent (e.g. after delete or move-away)."""
    store = _observation_store(context, create=True)
    if store is not None:
        store[key] = FileObservation(kind="absent", version=None)


def check_mutation_guard(
    context: Any,
    key: str,
    *,
    current_version: str | None,
    operation: Literal["create_or_replace", "update", "delete"],
    display_path: str,
) -> str | None:
    """Enforce read-before-edit (when enabled) and stale-version protection."""
    metadata = getattr(context, "metadata", None)
    enforce_read_before_edit = bool(
        isinstance(metadata, dict) and metadata.get("enforce_file_observation")
    )
    store = _observation_store(context, create=False)
    prior = store.get(key) if store is not None else None

    if operation == "create_or_replace" and current_version is None:
        # Creating a brand-new file does not require prior read unless it used to exist.
        if prior is not None and prior.kind == "present":
            return (
                f"FS_STALE_VERSION: File {display_path} was deleted externally since it was last "
                "read or written. Re-check the directory state before recreating it."
            )
        return None

    if prior is None:
        if enforce_read_before_edit:
            action = "overwriting" if operation == "create_or_replace" else f"{operation}ing"
            return (
                f"FS_NOT_OBSERVED: Read {display_path} with read_file before {action} it."
            )
        return None

    if current_version is None:
        if prior.kind == "present":
            return (
                f"FS_STALE_VERSION: File {display_path} no longer exists on disk since it was last "
                "read or written."
            )
        return None

    if prior.kind == "absent":
        return (
            f"FS_STALE_VERSION: File {display_path} was created externally after it was observed "
            "as absent. Read it before modifying."
        )

    if prior.version != current_version:
        return (
            f"FS_STALE_VERSION: File {display_path} has changed since it was last read or written. "
            "Re-read the file with read_file and retry with fresh context."
        )

    return None


async def atomic_write_sandbox_text(
    session: Any,
    sandbox_path: str,
    content: str,
    *,
    create_directories: bool = True,
) -> None:
    """Write text atomically inside an E2B sandbox via sibling temp file and mv -f."""
    parent = posixpath.dirname(sandbox_path) or "/home/user"
    filename = posixpath.basename(sandbox_path) or "file"
    temp_path = posixpath.join(parent, f".{filename}.openharness-tmp-{uuid.uuid4().hex}.part")
    if create_directories:
        mk_proc = await session.exec_command(f"mkdir -p {shlex.quote(parent)}")
        communicate = getattr(mk_proc, "communicate", None)
        if callable(communicate):
            await communicate()
    try:
        await session.write_file(temp_path, content)
        proc = await session.exec_command(
            "set -e; "
            f"chmod --reference={shlex.quote(sandbox_path)} {shlex.quote(temp_path)} 2>/dev/null || true; "
            f"mv -f {shlex.quote(temp_path)} {shlex.quote(sandbox_path)}"
        )
        stdout = b""
        stderr = b""
        communicate = getattr(proc, "communicate", None)
        if callable(communicate):
            stdout, stderr = await communicate()
        returncode = getattr(proc, "returncode", getattr(proc, "exit_code", 0))
        if returncode not in (0, None):
            details = (stderr or stdout or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(details or f"mv failed with exit code {returncode}")
    except Exception:
        try:
            rm_proc = await session.exec_command(f"rm -f {shlex.quote(temp_path)}")
            communicate = getattr(rm_proc, "communicate", None)
            if callable(communicate):
                await communicate()
        except Exception:
            pass
        raise


@dataclass(frozen=True)
class ReadWindowResult:
    """Rendered bounded file read output and window metadata."""

    output: str
    total_lines: int
    lines_returned: int
    truncated: bool
    truncated_by_bytes: bool
    has_truncated_lines: bool


def format_read_window(
    lines: list[str],
    *,
    offset: int,
    limit: int,
    display_path: str,
    total_lines: int | None = None,
) -> ReadWindowResult:
    """Format a bounded numbered line slice with line-length and byte caps.

    Continuation footers are appended only when the requested slice does not
    reach EOF (more lines remain, or byte budget / line length truncated output),
    preserving full compatibility when the entire file fits cleanly.
    """
    actual_total = total_lines if total_lines is not None else len(lines)
    if total_lines is None:
        selected = lines[offset : offset + limit]
    else:
        selected = lines[:limit]

    if not selected:
        if actual_total > 0 and offset >= actual_total:
            msg = (
                f"(no content in selected range for {display_path}; "
                f"total_lines={actual_total}, valid offset range is 0..{actual_total - 1})"
            )
        else:
            msg = f"(no content in selected range for {display_path})"
        return ReadWindowResult(
            output=msg,
            total_lines=actual_total,
            lines_returned=0,
            truncated=False,
            truncated_by_bytes=False,
            has_truncated_lines=False,
        )

    rendered: list[str] = []
    byte_count = 0
    truncated_by_bytes = False
    has_truncated_lines = False

    for index, raw_line in enumerate(selected):
        line_num = offset + index + 1
        line_text = raw_line
        if len(line_text) > READ_MAX_LINE_LENGTH:
            line_text = (
                f"{line_text[:READ_MAX_LINE_LENGTH]}... "
                f"[line truncated at {READ_MAX_LINE_LENGTH} chars, full length {len(raw_line)}]"
            )
            has_truncated_lines = True

        formatted = f"{line_num:>6}\t{line_text}"
        entry_bytes = len(formatted.encode("utf-8")) + (1 if rendered else 0)
        if rendered and byte_count + entry_bytes > READ_MAX_BYTES:
            truncated_by_bytes = True
            break
        rendered.append(formatted)
        byte_count += entry_bytes

    lines_returned = len(rendered)
    next_offset = offset + lines_returned
    more_lines_exist = next_offset < actual_total
    truncated = more_lines_exist or truncated_by_bytes or has_truncated_lines

    output = "\n".join(rendered)
    if more_lines_exist or truncated_by_bytes:
        reason = "byte limit reached" if truncated_by_bytes else "line limit reached"
        start_line_1 = offset + 1
        end_line_1 = offset + lines_returned
        output += (
            f"\n\n[Showing lines {start_line_1}-{end_line_1} of {actual_total} "
            f"({reason}). Use offset={next_offset} to continue reading.]"
        )
    elif has_truncated_lines:
        output += (
            f"\n\n[Note: one or more lines exceeded {READ_MAX_LINE_LENGTH} characters and were truncated.]"
        )

    return ReadWindowResult(
        output=output,
        total_lines=actual_total,
        lines_returned=lines_returned,
        truncated=truncated,
        truncated_by_bytes=truncated_by_bytes,
        has_truncated_lines=has_truncated_lines,
    )


def stream_host_text_window(
    path: Path,
    *,
    offset: int,
    limit: int,
    chunk_size: int = 256 * 1024,
) -> ReadWindowResult:
    """Stream a large host text file incrementally to collect a bounded window + exact line count."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    line_index = 0
    window_lines: list[str] = []

    def _push_line(line: str) -> None:
        nonlocal line_index
        if offset <= line_index < offset + limit:
            window_lines.append(line)
        line_index += 1

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            text = decoder.decode(chunk, final=False)
            if not text:
                continue
            pending += text
            lines = pending.split("\n")
            pending = lines.pop()
            for line in lines:
                if line.endswith("\r"):
                    line = line[:-1]
                _push_line(line)

        tail = decoder.decode(b"", final=True)
        pending += tail
        if pending:
            lines = pending.split("\n")
            for idx, line in enumerate(lines):
                if idx == len(lines) - 1 and line == "":
                    continue
                if line.endswith("\r"):
                    line = line[:-1]
                _push_line(line)

    return format_read_window(
        window_lines,
        offset=offset,
        limit=limit,
        display_path=str(path),
        total_lines=line_index,
    )


VCS_EXCLUDE_DIRS = (".git", ".svn", ".hg", ".bzr", ".jj", ".sl")
SEARCH_NOISE_DIRS = frozenset(
    VCS_EXCLUDE_DIRS + ("node_modules", "__pycache__", ".venv")
)
GREP_MAX_LINE_CHARS = 2000


def rg_vcs_exclude_args() -> list[str]:
    """Build ripgrep --glob exclusion flags for VCS metadata directories."""
    args: list[str] = []
    for vcs_dir in VCS_EXCLUDE_DIRS:
        args.extend(["--glob", f"!**/{vcs_dir}", "--glob", f"!**/{vcs_dir}/**"])
    return args


def is_ignored_search_relpath(rel_path: Path | str, *, pattern: str = "") -> bool:
    """Return True when a relative path traverses an ignored VCS/cache directory."""
    parts = Path(rel_path).parts if isinstance(rel_path, str) else rel_path.parts
    for part in parts[:-1]:
        if part in SEARCH_NOISE_DIRS and part not in pattern:
            return True
    if parts and parts[-1] in VCS_EXCLUDE_DIRS and parts[-1] not in pattern:
        return True
    return False


def sample_across_top_level(paths: list[str], limit: int) -> list[str]:
    """Select up to `limit` paths fairly across top-level directory buckets."""
    if len(paths) <= limit or limit <= 0:
        return paths[:limit]

    buckets: dict[str, list[str]] = {}
    for entry in sorted(paths):
        normalized = entry.replace("\\", "/")
        top = normalized.split("/", 1)[0] if "/" in normalized else "."
        buckets.setdefault(top, []).append(entry)

    selected: list[str] = []
    keys = list(buckets.keys())
    depth = 0
    while len(selected) < limit:
        progressed = False
        for key in keys:
            bucket = buckets[key]
            if depth < len(bucket):
                selected.append(bucket[depth])
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
        depth += 1
    return sorted(selected)


def truncate_search_line(line: str, max_chars: int = GREP_MAX_LINE_CHARS) -> str:
    """Cap excessively long grep match lines while keeping output readable."""
    if len(line) <= max_chars:
        return line
    return f"{line[:max_chars]}... [truncated]"
