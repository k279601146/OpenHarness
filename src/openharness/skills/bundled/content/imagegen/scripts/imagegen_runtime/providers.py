"""Provider adapters for non-GPT image models used by the imagegen CLI."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import sys
from typing import Any

from .registry import ImageModelSpec, get_model_spec


IMAGEGEN_METADATA_PREFIX = "IMAGEGEN_METADATA:"
CONTENT_DIR = Path(__file__).resolve().parents[3]
if str(CONTENT_DIR) not in sys.path:
    sys.path.insert(0, str(CONTENT_DIR))
from media_pricing_runtime import estimate_image_pricing

ASPECT_TO_OPENAI_SIZE = {"1:1": "1024x1024", "16:9": "1792x1024", "9:16": "1024x1792"}
ASPECT_TO_DOUBAO_SIZE = {
    "1:1": "2048x2048",
    "4:3": "2304x1728",
    "3:4": "1728x2304",
    "16:9": "2848x1600",
    "9:16": "1600x2848",
}
VALID_GEMINI_ASPECTS = {"1:1", "16:9", "9:16", "4:3", "3:4"}


class ImagegenProviderError(RuntimeError):
    pass


def emit_metadata(metadata: dict[str, Any]) -> None:
    print(f"{IMAGEGEN_METADATA_PREFIX}{json.dumps(metadata, ensure_ascii=False, sort_keys=True)}")


def provider_metadata(spec: ImageModelSpec, outputs: list[Path], args: Any | None = None, prompt: str = "") -> dict[str, Any]:
    count = len(outputs)
    reference_count = len(list(getattr(args, "image", []) or [])) if args is not None else 0
    try:
        pricing = estimate_image_pricing(
            model_id=spec.model_id,
            prompt=prompt,
            size=getattr(args, "size", None) if args is not None else spec.default_size,
            quality=getattr(args, "quality", None) if args is not None else spec.default_quality,
            aspect_ratio=getattr(args, "aspect_ratio", None) if args is not None else None,
            output_count=count,
            reference_count=reference_count,
        )
    except ValueError as exc:
        raise ImagegenProviderError(str(exc)) from exc
    return {
        "model_id": spec.model_id,
        "provider": spec.provider,
        "api_model": spec.api_model,
        "output_count": count,
        **pricing.to_metadata(),
        "artifact_paths": [str(path) for path in outputs],
    }


def run_non_gpt_image(args: Any, outputs: list[Path], prompt: str) -> dict[str, Any]:
    spec = get_model_spec(getattr(args, "model", None))
    if spec.provider == "gpt_image":
        raise ImagegenProviderError("run_non_gpt_image cannot execute GPT Image models")
    if getattr(args, "command", "") == "generate-batch":
        raise ImagegenProviderError(f"{spec.model_id} does not support generate-batch in the unified imagegen CLI yet.")

    api_key = _credential(spec.api_key_env)
    if not api_key and getattr(args, "dry_run", False):
        api_key = "dry-run"
    if not api_key:
        raise ImagegenProviderError(f"{spec.api_key_env} is not set. Configure it before using {spec.model_id}.")
    base_url = _credential(spec.base_url_env) or spec.default_base_url

    if getattr(args, "dry_run", False):
        preview = _build_payload(spec, args, prompt)
        preview["outputs"] = [str(path) for path in outputs]
        print(json.dumps(preview, indent=2, ensure_ascii=False, sort_keys=True))
        metadata = provider_metadata(spec, outputs, args, prompt)
        metadata["dry_run"] = True
        return metadata

    if not getattr(args, "force", False):
        existing = [path for path in outputs if path.exists()]
        if existing:
            raise ImagegenProviderError(f"Output already exists: {existing[0]} (use --force to overwrite)")

    if spec.provider == "gemini":
        saved = _run_gemini(spec, args, prompt, outputs, api_key, base_url)
    elif spec.provider == "doubao":
        saved = _run_doubao(spec, args, prompt, outputs, api_key, base_url)
    elif spec.provider == "openai_compatible":
        saved = _run_openai_compatible(spec, args, prompt, outputs, api_key, base_url)
    else:
        raise ImagegenProviderError(f"Unsupported image provider: {spec.provider}")
    return provider_metadata(spec, saved, args, prompt)


def _credential(name: str) -> str:
    return os.getenv(name, "").strip()


def _build_payload(spec: ImageModelSpec, args: Any, prompt: str) -> dict[str, Any]:
    images = list(getattr(args, "image", []) or [])
    aspect_ratio = getattr(args, "aspect_ratio", None) or _aspect_from_size(getattr(args, "size", None))
    n = int(getattr(args, "n", 1) or 1)
    if spec.provider == "gemini":
        parts: list[dict[str, Any]] = [{"text": prompt}]
        parts.extend(_load_image(path, "gemini") for path in images)
        return {
            "provider": spec.provider,
            "model": spec.api_model,
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "aspectRatio": aspect_ratio if aspect_ratio in VALID_GEMINI_ASPECTS else "1:1",
                    "imageSize": "2K",
                },
            },
        }
    if spec.provider == "doubao":
        payload = {
            "provider": spec.provider,
            "model": spec.api_model,
            "prompt": prompt,
            "size": _doubao_size(getattr(args, "size", None), aspect_ratio),
            "stream": True,
            "response_format": "b64_json",
            "sequential_image_generation": "auto" if n > 1 else "disabled",
            "sequential_image_generation_options": {"max_images": n},
        }
        if images:
            payload["image"] = [_load_image(path, "doubao") for path in images]
        return payload
    return {
        "provider": spec.provider,
        "model": spec.api_model,
        "prompt": prompt,
        "size": _openai_compatible_size(getattr(args, "size", None), aspect_ratio),
        "n": n,
        "response_format": "b64_json",
    }


def _run_gemini(spec: ImageModelSpec, args: Any, prompt: str, outputs: list[Path], api_key: str, base_url: str) -> list[Path]:
    import httpx

    payload = _build_payload(spec, args, prompt)
    clean_url = base_url.rstrip("/")
    if "/v1" not in clean_url:
        clean_url = f"{clean_url}/v1beta"
    response = httpx.post(
        f"{clean_url}/models/{spec.api_model}:generateContent",
        json={key: value for key, value in payload.items() if key != "provider" and key != "model"},
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        timeout=180.0,
    )
    response.raise_for_status()
    parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    images = [item.get("inlineData", {}).get("data") for item in parts if item.get("inlineData", {}).get("data")]
    if not images:
        raise ImagegenProviderError("Gemini image API did not return image data.")
    return _write_b64_images(images[: len(outputs)], outputs)


def _run_doubao(spec: ImageModelSpec, args: Any, prompt: str, outputs: list[Path], api_key: str, base_url: str) -> list[Path]:
    import httpx

    payload = _build_payload(spec, args, prompt)
    base_domain = _strip_version(base_url)
    saved: list[Path] = []
    with httpx.stream(
        "POST",
        f"{base_domain}/v1/images/generations",
        json={key: value for key, value in payload.items() if key != "provider"},
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=240.0,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "image_generation.partial_succeeded":
                continue
            b64 = event.get("b64_json")
            if not b64:
                continue
            index = len(saved)
            if index >= len(outputs):
                break
            _write_b64(outputs[index], b64)
            saved.append(outputs[index])
    if not saved:
        raise ImagegenProviderError("Doubao image API did not return image data.")
    return saved


def _run_openai_compatible(
    spec: ImageModelSpec,
    args: Any,
    prompt: str,
    outputs: list[Path],
    api_key: str,
    base_url: str,
) -> list[Path]:
    import httpx

    payload = _build_payload(spec, args, prompt)
    clean_url = base_url.rstrip("/")
    if "/v1" not in clean_url:
        clean_url = f"{clean_url}/v1"
    response = httpx.post(
        f"{clean_url}/images/generations",
        json={key: value for key, value in payload.items() if key != "provider"},
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=180.0,
    )
    response.raise_for_status()
    data = response.json().get("data", [])
    saved: list[Path] = []
    with httpx.Client(timeout=180.0) as client:
        for index, item in enumerate(data):
            if index >= len(outputs):
                break
            b64 = item.get("b64_json")
            url = item.get("url")
            if b64:
                _write_b64(outputs[index], b64)
            elif url:
                image_response = client.get(url)
                image_response.raise_for_status()
                _write_bytes(outputs[index], image_response.content)
            else:
                continue
            saved.append(outputs[index])
    if not saved:
        raise ImagegenProviderError("OpenAI-compatible image API did not return image data.")
    return saved


def _load_image(file_path: str, api_format: str) -> str | dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        raise ImagegenProviderError(f"Image file not found: {file_path}")
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "bmp": "bmp"}.get(
        path.suffix.lower().lstrip("."),
        "png",
    )
    if api_format == "doubao":
        return f"data:image/{mime};base64,{encoded}"
    return {"inlineData": {"mimeType": f"image/{mime}", "data": encoded}}


def _write_b64_images(images: list[str], outputs: list[Path]) -> list[Path]:
    saved: list[Path] = []
    for b64, path in zip(images, outputs):
        _write_b64(path, b64)
        saved.append(path)
    return saved


def _write_b64(path: Path, image_b64: str) -> None:
    _write_bytes(path, base64.b64decode(image_b64))


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    print(f"Wrote {path}")


def _strip_version(base_url: str) -> str:
    base = base_url.rstrip("/")
    for marker in ("/v1beta", "/v1"):
        if marker in base:
            return base.split(marker)[0]
    return base


def _aspect_from_size(size: str | None) -> str | None:
    if not size or "x" not in size:
        return None
    try:
        width_raw, height_raw = size.lower().split("x", 1)
        width = int(width_raw)
        height = int(height_raw)
    except ValueError:
        return None
    if width == height:
        return "1:1"
    ratio = width / height
    if ratio > 1.6:
        return "16:9"
    if ratio < 0.7:
        return "9:16"
    if ratio > 1:
        return "4:3"
    return "3:4"


def _doubao_size(size: str | None, aspect_ratio: str | None) -> str:
    if size and size != "auto":
        return size
    return ASPECT_TO_DOUBAO_SIZE.get(aspect_ratio or "", "2048x2048")


def _openai_compatible_size(size: str | None, aspect_ratio: str | None) -> str:
    if size and size != "auto":
        return size
    return ASPECT_TO_OPENAI_SIZE.get(aspect_ratio or "", "1024x1024")
