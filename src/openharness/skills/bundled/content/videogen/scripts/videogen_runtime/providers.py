"""Provider adapters for the unified videogen CLI."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from .registry import VideoModelSpec, get_model_spec


VIDEOGEN_METADATA_PREFIX = "VIDEOGEN_METADATA:"


class VideogenProviderError(RuntimeError):
    pass


def emit_metadata(metadata: dict[str, Any]) -> None:
    print(f"{VIDEOGEN_METADATA_PREFIX}{json.dumps(metadata, ensure_ascii=False, sort_keys=True)}")


def run_video(args: Any, outputs: list[Path], prompt: str) -> dict[str, Any]:
    spec = get_model_spec(getattr(args, "model", None))
    api_key = _credential(spec.api_key_env)
    if not api_key and getattr(args, "dry_run", False):
        api_key = "dry-run"
    if not api_key:
        raise VideogenProviderError(f"{spec.api_key_env} is not set. Configure it before using {spec.model_id}.")
    base_url = _credential(spec.base_url_env) or spec.default_base_url

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
    duration = _duration(args, spec)
    resolution = _resolution(args, spec)
    mode = _mode(args, spec)
    billing_units = _billing_units(spec, args, output_count, provider_usage)
    return {
        "video_model_id": spec.model_id,
        "model_id": spec.model_id,
        "provider": spec.provider,
        "api_model": spec.api_model,
        "billing_scheme": spec.billing_scheme,
        "duration_seconds": duration,
        "resolution": resolution,
        "mode": mode,
        "output_count": output_count,
        "provider_usage": provider_usage or {},
        "billing_units": billing_units,
        "artifact_paths": [str(path) for path in outputs],
    }


def _billing_units(
    spec: VideoModelSpec,
    args: Any,
    output_count: int,
    provider_usage: dict[str, Any] | None,
) -> float:
    if provider_usage:
        for key in ("billing_units", "credits", "points", "resource_units", "usage_units"):
            value = provider_usage.get(key)
            if value is not None:
                try:
                    return round(max(float(value), 0.0), 2)
                except (TypeError, ValueError):
                    pass

    duration = _duration(args, spec)
    resolution = _resolution(args, spec).lower()
    mode = _mode(args, spec).lower()
    usd_pricing = (
        spec.usd_per_second_with_audio_by_resolution
        if bool(getattr(args, "generate_audio", False)) and spec.usd_per_second_with_audio_by_resolution
        else spec.usd_per_second_by_resolution
    )
    if usd_pricing:
        usd_per_second = usd_pricing.get(resolution)
        if usd_per_second is None and resolution == "1080":
            usd_per_second = usd_pricing.get("1080p")
        if usd_per_second is None and resolution == "720":
            usd_per_second = usd_pricing.get("720p")
        if usd_per_second is not None:
            credits_per_usd = _env_float("BILLING_CREDITS_PER_USD", 25.0)
            return round(usd_per_second * duration * max(output_count, 1) * credits_per_usd, 2)
    multiplier = 1.0
    multiplier *= spec.billing_multipliers.get(resolution, 1.0)
    multiplier *= spec.billing_multipliers.get(mode, 1.0)
    command = str(getattr(args, "command", "") or "")
    if command in {"image-to-video", "first-last-frame", "reference-to-video"}:
        multiplier *= 1.15
    if bool(getattr(args, "generate_audio", False)) and spec.supports_audio:
        multiplier *= 1.1
    # Official schemes differ by provider; this fallback keeps the same dimensions
    # (model, duration, resolution, mode, references) for predictable estimates.
    duration_factor = max(duration, 1) / max(spec.default_duration_seconds, 1)
    return round(spec.base_billing_units * duration_factor * multiplier * max(output_count, 1), 2)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _credential(name: str) -> str:
    return os.getenv(name, "").strip()


def _build_payload(spec: VideoModelSpec, args: Any, prompt: str) -> dict[str, Any]:
    command = str(getattr(args, "command", "generate") or "generate")
    media = _media_inputs(args)
    duration = _duration(args, spec)
    aspect_ratio = getattr(args, "aspect_ratio", None) or spec.default_aspect_ratio
    resolution = _resolution(args, spec)
    mode = _mode(args, spec)
    generate_audio = bool(getattr(args, "generate_audio", False))

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
        for _ in range(120):
            poll = client.get(f"{endpoint.rstrip('/')}/{task_id}", headers=headers, timeout=60.0)
            poll.raise_for_status()
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
        for _ in range(90):
            time.sleep(10)
            poll = client.get(f"{clean_url.rstrip('/')}/{operation_name}", headers={"x-goog-api-key": api_key})
            poll.raise_for_status()
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
        for _ in range(120):
            time.sleep(10)
            poll = client.get(f"{clean_url}/v1/videos/generations/{task_id}", headers=headers)
            poll.raise_for_status()
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
    import httpx

    clean_urls = [url for url in urls if url and "http" in url]
    if not clean_urls:
        raise VideogenProviderError("Provider did not return a valid video URL.")
    saved: list[Path] = []
    with httpx.Client(timeout=300.0) as client:
        for url, path in zip(clean_urls, outputs):
            response = client.get(str(url))
            response.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
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


def _duration(args: Any, spec: VideoModelSpec) -> int:
    raw = getattr(args, "duration_seconds", None)
    if raw is None:
        raw = getattr(args, "duration", None)
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return spec.default_duration_seconds


def _resolution(args: Any, spec: VideoModelSpec) -> str:
    return str(getattr(args, "resolution", None) or spec.default_resolution)


def _mode(args: Any, spec: VideoModelSpec) -> str:
    return str(getattr(args, "mode", None) or getattr(args, "quality", None) or spec.default_mode)
