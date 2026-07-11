from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from openharness.tools.media_gateway_runtime import run_media_subprocess
from openharness.skills.bundled.content.media_safe_http import UnsafeMediaURL, safe_download_image, validate_public_http_url


class Hook:
    def __init__(self, *, kind="image", provider="gpt_image"):
        self.attempts = []
        self.submissions = []
        self.kind = kind
        self.provider = provider

    def get_media_gateway_runtime_candidate(self, reservation, candidate_id):
        return {
            "id": candidate_id,
            "kind": self.kind,
            "provider": self.provider,
            "max_concurrency": 2,
            "env": {"OPENHARNESS_MEDIA_GATEWAY_API_KEY": f"secret-{candidate_id}"},
            "metadata": {"gateway_id": candidate_id, "provider": self.provider, "model_id": "gpt-image-2"},
        }

    async def acquire_media_gateway_execution_slot(self, candidate):
        return {"gateway_id": candidate["id"]}

    async def release_media_gateway_execution_slot(self, slot):
        return None

    def record_media_gateway_attempt(self, reservation, candidate, **result):
        self.attempts.append((reservation, candidate["id"], result))

    def record_media_gateway_submission(self, reservation, candidate, *, provider, operation_id):
        self.submissions.append((reservation, candidate["id"], provider, operation_id))


@pytest.mark.asyncio
async def test_media_gateway_failover_reuses_single_reservation(monkeypatch):
    hook = Hook()
    reservation = {"resource_log_id": 7, "gateway_candidate_ids": [1, 2]}
    calls = []

    async def fake_run_once(**kwargs):
        calls.append(kwargs["env"])
        if len(calls) == 1:
            return subprocess.CompletedProcess(kwargs["argv"], 1, "provider returned 503")
        return subprocess.CompletedProcess(kwargs["argv"], 0, "ok")

    monkeypatch.setattr("openharness.tools.media_gateway_runtime._run_once", fake_run_once)
    context = SimpleNamespace(metadata={"hook": hook, "media_billing_reservation": reservation})

    result = await run_media_subprocess(
        argv=["image-gen"],
        cwd=".",
        env={},
        timeout_seconds=30,
        context=context,
        kind="image",
    )

    assert result.returncode == 0
    assert result.metadata["retry_count"] == 1
    assert [attempt[1] for attempt in hook.attempts] == [1, 2]
    assert all(attempt[0] is reservation for attempt in hook.attempts)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_media_gateway_does_not_fail_over_invalid_request(monkeypatch):
    hook = Hook()
    reservation = {"resource_log_id": 8, "gateway_candidate_ids": [1, 2]}
    calls = []

    async def fake_run_once(**kwargs):
        calls.append(kwargs["env"])
        return subprocess.CompletedProcess(kwargs["argv"], 1, "provider returned 400 invalid argument")

    monkeypatch.setattr("openharness.tools.media_gateway_runtime._run_once", fake_run_once)
    context = SimpleNamespace(metadata={"hook": hook, "media_billing_reservation": reservation})

    result = await run_media_subprocess(
        argv=["image-gen"],
        cwd=".",
        env={},
        timeout_seconds=30,
        context=context,
        kind="image",
    )

    assert result.returncode == 1
    assert len(calls) == 1
    assert hook.attempts[0][2]["retryable"] is False


@pytest.mark.asyncio
async def test_media_gateway_unsafe_url_records_reason_and_fails_over(monkeypatch):
    hook = Hook()
    reservation = {"resource_log_id": 11, "gateway_candidate_ids": [1, 2]}
    calls = []

    async def fake_validate(candidate):
        if candidate["id"] == 1:
            raise UnsafeMediaURL("Media URL host could not be resolved")

    async def fake_run_once(**kwargs):
        calls.append(kwargs["env"])
        return subprocess.CompletedProcess(kwargs["argv"], 0, "ok")

    monkeypatch.setattr(hook, "validate_media_gateway_candidate", fake_validate, raising=False)
    monkeypatch.setattr("openharness.tools.media_gateway_runtime._run_once", fake_run_once)
    context = SimpleNamespace(metadata={"hook": hook, "media_billing_reservation": reservation})

    result = await run_media_subprocess(
        argv=["image-gen"],
        cwd=".",
        env={},
        timeout_seconds=30,
        context=context,
        kind="image",
    )

    assert result.returncode == 0
    assert len(calls) == 1
    assert hook.attempts[0][1] == 1
    assert hook.attempts[0][2]["error_code"] == "unsafe_url"
    assert hook.attempts[0][2]["summary"] == "unsafe_url: Media URL host could not be resolved"
    assert hook.attempts[0][2]["retryable"] is True


@pytest.mark.asyncio
async def test_media_gateway_key_error_reports_missing_runtime_field(monkeypatch):
    hook = Hook()
    reservation = {"resource_log_id": 12, "gateway_candidate_ids": [1, 2]}

    async def fake_acquire(candidate):
        raise KeyError("media_gateway_url_validation_timeout_seconds")

    monkeypatch.setattr(hook, "acquire_media_gateway_execution_slot", fake_acquire, raising=False)
    context = SimpleNamespace(metadata={"hook": hook, "media_billing_reservation": reservation})

    result = await run_media_subprocess(
        argv=["image-gen"],
        cwd=".",
        env={},
        timeout_seconds=30,
        context=context,
        kind="image",
    )

    assert result.returncode == 1
    assert "Media gateway attempt failed: missing_runtime_field: media_gateway_url_validation_timeout_seconds" in result.output
    assert hook.attempts[0][2]["error_code"] == "missing_runtime_field"
    assert hook.attempts[0][2]["retryable"] is False


def test_media_download_url_rejects_private_address():
    with pytest.raises(UnsafeMediaURL):
        validate_public_http_url("http://127.0.0.1/internal/video.mp4")


def test_safe_download_image_accepts_octet_stream_with_image_bytes(monkeypatch):
    import openharness.skills.bundled.content.media_safe_http as media_safe_http

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/octet-stream", "content-length": str(len(png_bytes))}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            yield png_bytes

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url):
            assert method == "GET"
            assert url == "https://cdn.example.test/image.png"
            return FakeResponse()

    monkeypatch.setattr(media_safe_http.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))])
    monkeypatch.setattr(media_safe_http.httpx, "Client", FakeClient)

    assert safe_download_image("https://cdn.example.test/image.png") == png_bytes


def test_safe_download_image_rejects_octet_stream_without_image_bytes(monkeypatch):
    import openharness.skills.bundled.content.media_safe_http as media_safe_http

    payload = b"not an image"

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/octet-stream", "content-length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            yield payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url):
            return FakeResponse()

    monkeypatch.setattr(media_safe_http.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))])
    monkeypatch.setattr(media_safe_http.httpx, "Client", FakeClient)

    with pytest.raises(UnsafeMediaURL, match="supported image"):
        safe_download_image("https://cdn.example.test/image.bin")


@pytest.mark.asyncio
async def test_video_submission_is_persisted_and_unknown_state_does_not_fail_over(monkeypatch):
    hook = Hook(kind="video", provider="veo")
    reservation = {"resource_log_id": 9, "gateway_candidate_ids": [1, 2]}
    calls = []
    operation_id = "operations/private-video-id"

    async def fake_run_once(**kwargs):
        calls.append(kwargs["env"])
        event = f"VIDEOGEN_EVENT:{json.dumps({'type': 'submitted', 'provider': 'veo', 'operation_id': operation_id})}\n"
        assert kwargs["line_handler"](event) is None
        assert hook.submissions
        output = kwargs["line_handler"]("poll connection timeout\n")
        return subprocess.CompletedProcess(kwargs["argv"], 1, output)

    monkeypatch.setattr("openharness.tools.media_gateway_runtime._run_once", fake_run_once)
    context = SimpleNamespace(metadata={"hook": hook, "media_billing_reservation": reservation})

    result = await run_media_subprocess(
        argv=["video-gen"],
        cwd=".",
        env={},
        timeout_seconds=30,
        context=context,
        kind="video",
    )

    assert result.returncode == 1
    assert len(calls) == 1
    assert hook.submissions == [(reservation, 1, "veo", operation_id)]
    assert result.metadata["gateway_attempts"][0]["error_code"] == "remote_state_unknown"
    assert operation_id not in result.output
    assert "VIDEOGEN_EVENT:" not in result.output


@pytest.mark.asyncio
async def test_video_terminal_failure_after_submission_can_fail_over(monkeypatch):
    hook = Hook(kind="video", provider="veo")
    reservation = {"resource_log_id": 10, "gateway_candidate_ids": [1, 2]}
    calls = []

    async def fake_run_once(**kwargs):
        calls.append(kwargs["env"])
        if len(calls) == 1:
            event = f"VIDEOGEN_EVENT:{json.dumps({'type': 'submitted', 'provider': 'veo', 'operation_id': 'operations/failed'})}\n"
            assert kwargs["line_handler"](event) is None
            return subprocess.CompletedProcess(kwargs["argv"], 1, "task ended with status failed")
        return subprocess.CompletedProcess(kwargs["argv"], 0, "ok")

    monkeypatch.setattr("openharness.tools.media_gateway_runtime._run_once", fake_run_once)
    context = SimpleNamespace(metadata={"hook": hook, "media_billing_reservation": reservation})

    result = await run_media_subprocess(
        argv=["video-gen"],
        cwd=".",
        env={},
        timeout_seconds=30,
        context=context,
        kind="video",
    )

    assert result.returncode == 0
    assert len(calls) == 2
    assert hook.attempts[0][2]["error_code"] == "remote_terminal_failure"
