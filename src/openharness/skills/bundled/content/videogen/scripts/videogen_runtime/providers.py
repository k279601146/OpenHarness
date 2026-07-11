"""Provider adapters for the unified videogen CLI."""

from __future__ import annotations

import base64
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
from typing import Any

from .registry import VideoModelSpec, get_model_spec, supported_durations_for_resolution


VIDEOGEN_METADATA_PREFIX = "VIDEOGEN_METADATA:"
VIDEOGEN_EVENT_PREFIX = "VIDEOGEN_EVENT:"
CONTENT_DIR = Path(__file__).resolve().parents[3]
if str(CONTENT_DIR) not in sys.path:
    sys.path.insert(0, str(CONTENT_DIR))
from media_pricing_runtime import estimate_video_pricing  # noqa: E402
from media_safe_http import safe_download_video, validate_public_http_url  # noqa: E402


class VideogenProviderError(RuntimeError):
    pass


def emit_metadata(metadata: dict[str, Any]) -> None:
    print(f"{VIDEOGEN_METADATA_PREFIX}{json.dumps(metadata, ensure_ascii=False, sort_keys=True)}")


def _emit_submission_event(spec: VideoModelSpec, operation_id: str) -> None:
    print(
        f"{VIDEOGEN_EVENT_PREFIX}{json.dumps({'type': 'submitted', 'provider': spec.provider, 'operation_id': operation_id}, ensure_ascii=False, sort_keys=True)}",
        flush=True,
    )


def run_video(args: Any, outputs: list[Path], prompt: str) -> dict[str, Any]:
    spec = _runtime_spec(get_model_spec(getattr(args, "model", None)))
    _validate_requested_capabilities(spec, args, len(outputs))
    api_key = _credential("OPENHARNESS_MEDIA_GATEWAY_API_KEY")
    if not api_key and getattr(args, "dry_run", False):
        api_key = "dry-run"
    if not api_key:
        raise VideogenProviderError(
            f"OPENHARNESS_MEDIA_GATEWAY_API_KEY is not set. Configure the media model gateway before using {spec.model_id}."
        )
    gateway_base_url = _credential("OPENHARNESS_MEDIA_GATEWAY_BASE_URL")
    base_url = validate_public_http_url(gateway_base_url) if gateway_base_url else spec.default_base_url

    payload = _build_payload(spec, args, prompt)
    if getattr(args, "dry_run", False):
        preview = {
            "provider": spec.provider,
            "model_id": spec.model_id,
            "api_model": spec.api_model,
            "base_url": base_url,
            "payload": payload,
            "outputs": [str(path) for path in outputs],
        }
        print(json.dumps(preview, indent=2, ensure_ascii=False, sort_keys=True))
        metadata = provider_metadata(spec, args, outputs, provider_usage=None)
        metadata["dry_run"] = True
        return metadata

    if not getattr(args, "force", False):
        existing = [path for path in outputs if path.exists()]
        if existing:
            raise VideogenProviderError(f"Output already exists: {existing[0]} (use --force to overwrite)")

    if spec.provider == "seedance":
        saved, usage = _run_seedance(spec, payload, outputs, api_key, base_url)
    elif spec.provider == "veo":
        saved, usage = _run_veo(spec, payload, outputs, api_key, base_url)
    elif spec.provider == "kling":
        saved, usage = _run_kling(spec, payload, outputs, api_key, base_url)
    else:
        raise VideogenProviderError(f"Unsupported video provider: {spec.provider}")
    return provider_metadata(spec, args, saved, provider_usage=usage)


def provider_metadata(
    spec: VideoModelSpec,
    args: Any,
    outputs: list[Path],
    provider_usage: dict[str, Any] | None,
) -> dict[str, Any]:
    output_count = len(outputs)
    resolution = _resolution(args, spec)
    duration = _duration(args, spec, resolution)
    mode = _mode(args, spec)
    aspect_ratio = getattr(args, "aspect_ratio", None) or spec.default_aspect_ratio
    generate_audio = bool(getattr(args, "generate_audio", False))
    try:
        pricing = estimate_video_pricing(
            model_id=spec.model_id,
            duration_seconds=duration,
            resolution=resolution,
            mode=mode,
            generate_audio=generate_audio,
            command=getattr(args, "command", None),
            output_count=output_count,
            provider_usage=provider_usage,
        )
    except ValueError as exc:
        raise VideogenProviderError(str(exc)) from exc
    return {
        "video_model_id": spec.model_id,
        "model_id": spec.model_id,
        "provider": spec.provider,
        "api_model": spec.api_model,
        "billing_scheme": spec.billing_scheme,
        "duration_seconds": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "mode": mode,
        "generate_audio": generate_audio,
        "output_count": output_count,
        "provider_usage": provider_usage or {},
        **pricing.to_metadata(),
        "artifact_paths": [str(path) for path in outputs],
    }


def _credential(name: str) -> str:
    return os.getenv(name, "").strip()


def _runtime_spec(spec: VideoModelSpec) -> VideoModelSpec:
    upstream_model_id = _credential("OPENHARNESS_MEDIA_GATEWAY_MODEL_ID")
    return replace(spec, api_model=upstream_model_id) if upstream_model_id else spec


def _build_payload(spec: VideoModelSpec, args: Any, prompt: str) -> dict[str, Any]:
    command = str(getattr(args, "command", "generate") or "generate")
    media = _media_inputs(args)
    aspect_ratio = getattr(args, "aspect_ratio", None) or spec.default_aspect_ratio
    resolution = _resolution(args, spec)
    duration = _duration(args, spec, resolution)
    mode = _mode(args, spec)
    generate_audio = bool(getattr(args, "generate_audio", False))
    watermark = bool(getattr(args, "watermark", False))

    if spec.provider == "veo":
        instance: dict[str, Any] = {"prompt": prompt}
        if media.get("first_frame"):
            instance["image"] = _load_image(media["first_frame"], "gemini")
        parameters = {
            "aspectRatio": aspect_ratio,
            "durationSeconds": str(duration),
            "resolution": resolution,
        }
        if mode:
            parameters["mode"] = mode
        if generate_audio:
            parameters["generateAudio"] = True
        if watermark:
            parameters["watermark"] = True
        return {
            "model": spec.api_model,
            "instances": [instance],
            "parameters": parameters,
            "command": command,
        }

    if spec.provider == "seedance":
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if media.get("first_frame"):
            content.append(_seedance_image_content(media["first_frame"], "first_frame"))
        if media.get("last_frame"):
            content.append(_seedance_image_content(media["last_frame"], "last_frame"))
        for path in media.get("references", []):
            content.append(_seedance_image_content(path, "reference_image"))
        return {
            "model": spec.api_model,
            "content": content,
            "ratio": aspect_ratio,
            "duration": duration,
            "resolution": resolution,
            "mode": mode,
            "generate_audio": generate_audio,
            **({"watermark": True} if watermark else {}),
            "command": command,
        }

    payload: dict[str, Any] = {
        "model": spec.api_model,
        "prompt": prompt,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "mode": mode,
        "generate_audio": generate_audio,
        **({"watermark": True} if watermark else {}),
        "command": command,
    }
    if media.get("first_frame"):
        payload["image"] = _load_image(media["first_frame"], "data_url")
    if media.get("last_frame"):
        payload["last_frame"] = _load_image(media["last_frame"], "data_url")
    if media.get("references"):
        payload["reference_files"] = [_load_image(path, "data_url") for path in media["references"]]
    return payload


def _run_seedance(
    spec: VideoModelSpec,
    payload: dict[str, Any],
    outputs: list[Path],
    api_key: str,
    base_url: str,
) -> tuple[list[Path], dict[str, Any]]:
    import httpx

    base_domain = _strip_version(base_url)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60.0) as client:
        endpoint = f"{base_domain}/v1/contents/generations/tasks"
        response = client.post(endpoint, json={k: v for k, v in payload.items() if k != "command"}, headers=headers)
        if response.status_code == 404:
            endpoint = f"{base_domain}/api/v3/contents/generations/tasks"
            response = client.post(endpoint, json={k: v for k, v in payload.items() if k != "command"}, headers=headers)
        response.raise_for_status()
        data = response.json()
        task_id = data.get("id") or data.get("task_id")
        if not task_id:
            raise VideogenProviderError("Seedance API did not return a task id.")
        _emit_submission_event(spec, str(task_id))
        for _ in range(120):
            try:
                poll = client.get(f"{endpoint.rstrip('/')}/{task_id}", headers=headers, timeout=60.0)
                poll.raise_for_status()
            except httpx.HTTPError as exc:
                raise VideogenProviderError("Seedance operation state unknown after task submission; do not resubmit.") from exc
            status_data = poll.json()
            status = status_data.get("status")
            if status == "succeeded":
                video_url = status_data.get("content", {}).get("video_url") or status_data.get("video_url")
                return _download_videos([video_url], outputs), _usage_from_response(status_data)
            if status in {"failed", "cancelled", "expired"}:
                raise VideogenProviderError(f"Seedance task ended with status {status}: {status_data.get('error')}")
    raise VideogenProviderError("Seedance rendering timed out.")


def _run_veo(
    spec: VideoModelSpec,
    payload: dict[str, Any],
    outputs: list[Path],
    api_key: str,
    base_url: str,
) -> tuple[list[Path], dict[str, Any]]:
    import time
    import httpx

    clean_url = base_url.rstrip("/")
    if "/v1" not in clean_url:
        clean_url = f"{clean_url}/v1beta"
    body = {key: value for key, value in payload.items() if key not in {"model", "command"}}
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            f"{clean_url}/models/{spec.api_model}:predictLongRunning",
            json=body,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        )
        response.raise_for_status()
        operation_name = response.json().get("name")
        if not operation_name:
            raise VideogenProviderError("Veo API did not return an operation name.")
        _emit_submission_event(spec, str(operation_name))
        for _ in range(90):
            time.sleep(10)
            try:
                poll = client.get(f"{clean_url.rstrip('/')}/{operation_name}", headers={"x-goog-api-key": api_key})
                poll.raise_for_status()
            except httpx.HTTPError as exc:
                raise VideogenProviderError("Veo operation state unknown after task submission; do not resubmit.") from exc
            data = poll.json()
            if data.get("done"):
                if "error" in data:
                    raise VideogenProviderError(f"Veo task failed: {data['error']}")
                samples = data.get("response", {}).get("generateVideoResponse", {}).get("generatedSamples", [])
                urls = [item.get("video", {}).get("uri") for item in samples]
                return _download_videos(urls, outputs), _usage_from_response(data)
    raise VideogenProviderError("Veo rendering timed out.")


def _run_kling(
    spec: VideoModelSpec,
    payload: dict[str, Any],
    outputs: list[Path],
    api_key: str,
    base_url: str,
) -> tuple[list[Path], dict[str, Any]]:
    import time
    import httpx

    clean_url = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60.0) as client:
        response = client.post(f"{clean_url}/v1/videos/generations", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        task_id = data.get("id") or data.get("task_id") or data.get("data", {}).get("task_id")
        if not task_id:
            raise VideogenProviderError("Kling API did not return a task id.")
        _emit_submission_event(spec, str(task_id))
        for _ in range(120):
            time.sleep(10)
            try:
                poll = client.get(f"{clean_url}/v1/videos/generations/{task_id}", headers=headers)
                poll.raise_for_status()
            except httpx.HTTPError as exc:
                raise VideogenProviderError("Kling operation state unknown after task submission; do not resubmit.") from exc
            status_data = poll.json()
            status = status_data.get("status") or status_data.get("data", {}).get("status")
            if status in {"succeeded", "completed", "success"}:
                urls = _extract_video_urls(status_data)
                return _download_videos(urls, outputs), _usage_from_response(status_data)
            if status in {"failed", "cancelled", "canceled", "expired"}:
                raise VideogenProviderError(f"Kling task ended with status {status}: {status_data}")
    raise VideogenProviderError("Kling rendering timed out.")


def _media_inputs(args: Any) -> dict[str, Any]:
    images = list(getattr(args, "image", []) or [])
    images.extend(list(getattr(args, "images", []) or []))
    references = list(getattr(args, "reference_files", []) or [])
    first_frame = getattr(args, "first_frame", None) or (images[0] if images else None)
    last_frame = getattr(args, "last_frame", None)
    if not references and len(images) > 1:
        references = images[1:]
    return {
        "first_frame": first_frame,
        "last_frame": last_frame,
        "references": references,
    }


def _seedance_image_content(path: str, role: str) -> dict[str, Any]:
    return {
        "type": "image_url",
        "image_url": {"url": _load_image(path, "data_url")},
        "role": role,
    }


def _load_image(file_path: str, api_format: str) -> str | dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        raise VideogenProviderError(f"Image file not found: {file_path}")
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "bmp": "bmp"}.get(
        path.suffix.lower().lstrip("."),
        "png",
    )
    if api_format == "gemini":
        return {"inlineData": {"mimeType": f"image/{mime}", "data": encoded}}
    return f"data:image/{mime};base64,{encoded}"


def _download_videos(urls: list[str | None], outputs: list[Path]) -> list[Path]:
    clean_urls = [url for url in urls if url and "http" in url]
    if not clean_urls:
        raise VideogenProviderError("Provider did not return a valid video URL.")
    saved: list[Path] = []
    for url, path in zip(clean_urls, outputs):
        safe_download_video(str(url), path)
        print(f"Wrote {path}")
        saved.append(path)
    if not saved:
        raise VideogenProviderError("No videos were saved.")
    return saved


def _extract_video_urls(data: dict[str, Any]) -> list[str]:
    candidates = [
        data.get("video_url"),
        data.get("url"),
        data.get("data", {}).get("video_url") if isinstance(data.get("data"), dict) else None,
        data.get("data", {}).get("url") if isinstance(data.get("data"), dict) else None,
    ]
    videos = data.get("data", {}).get("videos") if isinstance(data.get("data"), dict) else None
    if isinstance(videos, list):
        candidates.extend(item.get("url") or item.get("video_url") for item in videos if isinstance(item, dict))
    return [str(item) for item in candidates if item]


def _usage_from_response(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("usage", "billing", "credits", "points", "resource_units"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
        if value is not None:
            return {key: value}
    return {}


def _strip_version(base_url: str) -> str:
    base = base_url.rstrip("/")
    for marker in ("/v1beta", "/v1", "/api/v3"):
        if marker in base:
            return base.split(marker)[0]
    return base


def _duration(args: Any, spec: VideoModelSpec, resolution: str | None = None) -> int:
    raw = getattr(args, "duration_seconds", None)
    if raw is None:
        raw = getattr(args, "duration", None)
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        supported = supported_durations_for_resolution(spec, resolution or _resolution(args, spec))
        if spec.default_duration_seconds in supported:
            return spec.default_duration_seconds
        return supported[0] if supported else spec.default_duration_seconds


def _resolution(args: Any, spec: VideoModelSpec) -> str:
    raw = getattr(args, "resolution", None)
    value = str(raw if raw is not None else spec.default_resolution).strip().lower()
    aliases = {
        "480": "480p",
        "480p": "480p",
        "720": "720p",
        "720p": "720p",
        "1080": "1080p",
        "1080p": "1080p",
        "2k": "2k",
        "4k": "4k",
    }
    return aliases.get(value, value)


def _mode(args: Any, spec: VideoModelSpec) -> str:
    mode = str(getattr(args, "mode", None) or "").strip().lower()
    if mode:
        return mode
    legacy_quality = str(getattr(args, "quality", None) or "").strip().lower()
    if legacy_quality in {"fast", "standard", "pro", "lite", "omni"}:
        return legacy_quality
    return spec.default_mode


def _validate_requested_capabilities(spec: VideoModelSpec, args: Any, output_count: int) -> None:
    command = str(getattr(args, "command", "generate") or "generate")
    if command == "image-to-video" and not spec.supports_image_to_video:
        raise VideogenProviderError(f"{spec.model_id} does not support image-to-video.")
    if command == "first-last-frame" and not spec.supports_first_last_frame:
        raise VideogenProviderError(f"{spec.model_id} does not support first-last-frame generation.")
    if command == "reference-to-video" and not spec.supports_reference:
        raise VideogenProviderError(f"{spec.model_id} does not support reference-to-video generation.")

    resolution = _resolution(args, spec)
    duration = _duration(args, spec, resolution)
    checks = (
        ("resolution", resolution, spec.supported_resolutions),
        ("duration_seconds", duration, supported_durations_for_resolution(spec, resolution)),
        ("aspect_ratio", str(getattr(args, "aspect_ratio", None) or spec.default_aspect_ratio), spec.supported_aspect_ratios),
        ("mode", _mode(args, spec), spec.supported_modes),
    )
    for parameter, value, supported in checks:
        if value not in supported:
            raise VideogenProviderError(
                f"Unsupported {parameter}={value!r} for {spec.model_id}. Supported values: {', '.join(map(str, supported))}"
            )
    if bool(getattr(args, "generate_audio", False)) and not spec.supports_audio:
        raise VideogenProviderError(f"{spec.model_id} does not support audio generation.")
    if bool(getattr(args, "watermark", False)) and not spec.supports_watermark:
        raise VideogenProviderError(f"{spec.model_id} does not support watermark generation.")
    if output_count > max(int(spec.max_outputs or 1), 1):
        raise VideogenProviderError(f"{spec.model_id} supports at most {spec.max_outputs} outputs.")
