from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re
import subprocess
import time
from typing import Any, Callable

from openharness.tools.base import ToolExecutionContext


VIDEOGEN_EVENT_PREFIX = "VIDEOGEN_EVENT:"


@dataclass(frozen=True)
class MediaSubprocessResult:
    returncode: int
    output: str
    metadata: dict[str, Any]


@dataclass
class _VideoSubmissionState:
    submitted: bool = False


def _status_code(output: str) -> str | None:
    match = re.search(r"\b(4\d\d|5\d\d)\b", output or "")
    return match.group(1) if match else None


def _retryable_failure(output: str, *, kind: str) -> tuple[bool, str]:
    normalized = (output or "").lower()
    status_code = _status_code(output)
    if status_code in {"400", "422"}:
        return False, status_code
    if any(marker in normalized for marker in ("content policy", "safety", "moderation", "invalid argument", "unsupported")):
        return False, status_code or "invalid_request"
    if kind == "video" and any(marker in normalized for marker in ("rendering timed out", "polling timed out", "operation state unknown")):
        return False, status_code or "remote_state_unknown"
    if status_code in {"401", "403", "404", "408", "409", "429"}:
        return True, status_code
    if status_code and status_code.startswith("5"):
        return True, status_code
    if any(marker in normalized for marker in ("timeout", "timed out", "connection", "network", "rate limit", "temporarily unavailable")):
        return True, status_code or "transport_error"
    if any(marker in normalized for marker in ("status failed", "status cancelled", "status canceled", "status expired", "task failed")):
        return True, status_code or "remote_terminal_failure"
    return False, status_code or "provider_error"


async def run_media_subprocess(
    *,
    argv: list[str],
    cwd: str,
    env: dict[str, str],
    timeout_seconds: int,
    context: ToolExecutionContext,
    kind: str,
) -> MediaSubprocessResult:
    hook = context.metadata.get("hook")
    reservation = context.metadata.get("media_billing_reservation")
    candidate_ids = list((reservation or {}).get("gateway_candidate_ids") or []) if isinstance(reservation, dict) else []
    if hook is None or not candidate_ids or not hasattr(hook, "get_media_gateway_runtime_candidate"):
        submission = _VideoSubmissionState()
        try:
            completed = await _run_once(
                argv=argv,
                cwd=cwd,
                env=env,
                timeout_seconds=timeout_seconds,
                line_handler=_video_line_handler(kind=kind, submission=submission),
            )
            return MediaSubprocessResult(completed.returncode, completed.stdout or "", {})
        except subprocess.TimeoutExpired as exc:
            return MediaSubprocessResult(1, f"{kind} generation timed out after {timeout_seconds}s.\n{exc.stdout or ''}".strip(), {})

    last_result: MediaSubprocessResult | None = None
    attempts: list[dict[str, Any]] = []
    for sequence, candidate_id in enumerate(candidate_ids, start=1):
        candidate = hook.get_media_gateway_runtime_candidate(reservation, int(candidate_id))
        if not isinstance(candidate, dict):
            continue
        candidate_env = dict(env)
        candidate_env.update({str(key): str(value) for key, value in (candidate.get("env") or {}).items()})
        slot = None
        submission = _VideoSubmissionState()
        started = time.monotonic()
        try:
            if hasattr(hook, "validate_media_gateway_candidate"):
                await hook.validate_media_gateway_candidate(candidate)
            if hasattr(hook, "acquire_media_gateway_execution_slot"):
                slot = await hook.acquire_media_gateway_execution_slot(candidate)
            completed = await _run_once(
                argv=argv,
                cwd=cwd,
                env=candidate_env,
                timeout_seconds=timeout_seconds,
                line_handler=_video_line_handler(
                    kind=kind,
                    submission=submission,
                    hook=hook,
                    reservation=reservation,
                    candidate=candidate,
                ),
            )
            output = completed.stdout or ""
            latency_ms = int((time.monotonic() - started) * 1000)
            if completed.returncode == 0:
                if hasattr(hook, "record_media_gateway_attempt"):
                    hook.record_media_gateway_attempt(reservation, candidate, success=True, retryable=False, latency_ms=latency_ms)
                metadata = dict(candidate.get("metadata") or {})
                metadata.update({"retry_count": sequence - 1, "gateway_attempt_count": sequence})
                return MediaSubprocessResult(0, output, metadata)
            retryable, error_code = _retryable_failure(output, kind=kind)
            if submission.submitted and error_code != "remote_terminal_failure":
                retryable, error_code = False, "remote_state_unknown"
            if hasattr(hook, "record_media_gateway_attempt"):
                hook.record_media_gateway_attempt(
                    reservation,
                    candidate,
                    success=False,
                    retryable=retryable,
                    error_code=error_code,
                    summary=output,
                    latency_ms=latency_ms,
                )
            attempts.append({**dict(candidate.get("metadata") or {}), "error_code": error_code, "retryable": retryable})
            last_result = MediaSubprocessResult(
                completed.returncode,
                output,
                {"retry_count": sequence - 1, "gateway_attempt_count": sequence, "gateway_attempts": attempts},
            )
            if not retryable:
                return last_result
        except subprocess.TimeoutExpired as exc:
            output = str(exc.stdout or "")
            retryable, error_code = _retryable_failure(f"timeout {output}", kind=kind)
            if submission.submitted:
                retryable, error_code = False, "remote_state_unknown"
            latency_ms = int((time.monotonic() - started) * 1000)
            if hasattr(hook, "record_media_gateway_attempt"):
                hook.record_media_gateway_attempt(
                    reservation,
                    candidate,
                    success=False,
                    retryable=retryable,
                    error_code=error_code,
                    summary="provider subprocess timeout",
                    latency_ms=latency_ms,
                )
            attempts.append({**dict(candidate.get("metadata") or {}), "error_code": error_code, "retryable": retryable})
            last_result = MediaSubprocessResult(
                1,
                f"{kind} generation timed out after {timeout_seconds}s.",
                {"retry_count": sequence - 1, "gateway_attempt_count": sequence, "gateway_attempts": attempts},
            )
            if not retryable:
                return last_result
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            error_code = "remote_state_unknown" if submission.submitted else type(exc).__name__
            retryable = not submission.submitted
            if hasattr(hook, "record_media_gateway_attempt"):
                hook.record_media_gateway_attempt(
                    reservation,
                    candidate,
                    success=False,
                    retryable=retryable,
                    error_code=error_code,
                    summary=error_code,
                    latency_ms=latency_ms,
                )
            attempts.append({**dict(candidate.get("metadata") or {}), "error_code": error_code, "retryable": retryable})
            last_result = MediaSubprocessResult(
                1,
                "Video operation state is unknown after remote submission."
                if submission.submitted
                else f"Media gateway attempt failed: {error_code}",
                {"retry_count": sequence - 1, "gateway_attempt_count": sequence, "gateway_attempts": attempts},
            )
            if not retryable:
                return last_result
        finally:
            if slot is not None and hasattr(hook, "release_media_gateway_execution_slot"):
                await hook.release_media_gateway_execution_slot(slot)

    return last_result or MediaSubprocessResult(
        1,
        "No available media gateway remained for this model.",
        {"retry_count": len(attempts), "gateway_attempt_count": len(attempts), "gateway_attempts": attempts},
    )


def _video_line_handler(
    *,
    kind: str,
    submission: _VideoSubmissionState,
    hook: Any = None,
    reservation: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
) -> Callable[[str], str | None] | None:
    if kind != "video":
        return None

    def handle(line: str) -> str | None:
        stripped = line.strip()
        if not stripped.startswith(VIDEOGEN_EVENT_PREFIX):
            return line
        try:
            event = json.loads(stripped[len(VIDEOGEN_EVENT_PREFIX) :])
        except (TypeError, ValueError):
            return None
        if not isinstance(event, dict) or event.get("type") != "submitted":
            return None
        operation_id = str(event.get("operation_id") or "").strip()
        provider = str(event.get("provider") or "").strip()
        if not operation_id or len(operation_id) > 2048 or not provider:
            return None
        submission.submitted = True
        expected_provider = str((candidate or {}).get("provider") or provider)
        if hook is not None and hasattr(hook, "record_media_gateway_submission"):
            hook.record_media_gateway_submission(
                reservation or {},
                candidate or {},
                provider=expected_provider,
                operation_id=operation_id,
            )
        if provider != expected_provider:
            raise RuntimeError("media_gateway_submission_provider_mismatch")
        return None

    return handle


async def _run_once(
    *,
    argv: list[str],
    cwd: str,
    env: dict[str, str],
    timeout_seconds: int,
    line_handler: Callable[[str], str | None] | None = None,
) -> subprocess.CompletedProcess[str]:
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        limit=1024 * 1024,
    )
    output: list[str] = []

    async def consume() -> None:
        assert process.stdout is not None
        while True:
            raw_line = await process.stdout.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace")
            filtered = line_handler(line) if line_handler is not None else line
            if filtered is not None:
                output.append(filtered)
        await process.wait()

    try:
        await asyncio.wait_for(consume(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise subprocess.TimeoutExpired(argv, timeout_seconds, output="".join(output)) from exc
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    return subprocess.CompletedProcess(argv, int(process.returncode or 0), "".join(output))
