"""Execution routing registry for the bundled imagegen CLI.

This module selects the provider adapter and supplies lightweight execution
defaults. It is not a billing boundary and does not maintain provider-specific
dimension allowlists.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal


Provider = Literal["gpt_image", "kolors", "gemini", "doubao"]


@dataclass(frozen=True)
class ImageModelSpec:
    model_id: str
    provider: Provider
    api_model: str
    default_base_url: str
    supports_edit: bool = False
    supports_reference: bool = False
    supports_batch: bool = False
    default_resolution: str | None = None
    default_size: str = "auto"
    default_aspect_ratio: str | None = None
    default_quality: str = "medium"
    max_outputs: int = 1
    supported_output_formats: tuple[str, ...] = ()
    supported_backgrounds: tuple[str, ...] = ()
    supported_input_fidelities: tuple[str, ...] = ()


IMAGE_MODEL_REGISTRY: dict[str, ImageModelSpec] = {
    "kolors": ImageModelSpec(
        model_id="kolors",
        provider="kolors",
        api_model="Kwai-Kolors/Kolors",
        default_base_url="https://api.packyapi.com/v1",
        default_size="1024x1024",
        default_resolution="1K",
        default_aspect_ratio="1:1",
        max_outputs=4,
    ),
    "gpt-image-2": ImageModelSpec(
        model_id="gpt-image-2",
        provider="gpt_image",
        api_model="gpt-image-2",
        default_base_url="https://api.packyapi.com",
        supports_edit=True,
        supports_reference=True,
        supports_batch=True,
        default_size="auto",
        default_resolution="1K",
        default_aspect_ratio="1:1",
        default_quality="medium",
        max_outputs=10,
        supported_output_formats=("png", "jpeg", "webp"),
        supported_backgrounds=("opaque", "auto"),
        supported_input_fidelities=(),
    ),
    "nano-banana": ImageModelSpec(
        model_id="nano-banana",
        provider="gemini",
        api_model="gemini-2.5-flash-image",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_edit=True,
        supports_reference=True,
        default_resolution="1K",
        default_size="1K",
        default_aspect_ratio="1:1",
    ),
    "nano-banana-2": ImageModelSpec(
        model_id="nano-banana-2",
        provider="gemini",
        api_model="gemini-3.1-flash-image",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_edit=True,
        supports_reference=True,
        default_resolution="1K",
        default_size="1K",
        default_aspect_ratio="1:1",
    ),
    "nano-banana-pro": ImageModelSpec(
        model_id="nano-banana-pro",
        provider="gemini",
        api_model="gemini-3-pro-image",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_edit=True,
        supports_reference=True,
        default_resolution="1K",
        default_size="1K",
        default_aspect_ratio="1:1",
        default_quality="medium",
    ),
    "doubao-seedream-5-0-260128": ImageModelSpec(
        model_id="doubao-seedream-5-0-260128",
        provider="doubao",
        api_model="doubao-seedream-5-0-260128",
        default_base_url="https://api.packyapi.com",
        supports_edit=True,
        supports_reference=True,
        default_size="2048x2048",
        default_resolution="2K",
        default_aspect_ratio="1:1",
        max_outputs=4,
    ),
    "doubao-seedream-5-0-lite-260128": ImageModelSpec(
        model_id="doubao-seedream-5-0-lite-260128",
        provider="doubao",
        api_model="doubao-seedream-5-0-lite-260128",
        default_base_url="https://api.packyapi.com",
        supports_edit=True,
        supports_reference=True,
        default_size="2048x2048",
        default_resolution="2K",
        default_aspect_ratio="1:1",
        max_outputs=4,
    ),
    "doubao-seedream-4-5-251128": ImageModelSpec(
        model_id="doubao-seedream-4-5-251128",
        provider="doubao",
        api_model="doubao-seedream-4-5-251128",
        default_base_url="https://api.packyapi.com",
        supports_edit=True,
        supports_reference=True,
        default_size="2048x2048",
        default_resolution="2K",
        default_aspect_ratio="1:1",
        max_outputs=4,
    ),
    "doubao-seedream-4-0-250828": ImageModelSpec(
        model_id="doubao-seedream-4-0-250828",
        provider="doubao",
        api_model="doubao-seedream-4-0-250828",
        default_base_url="https://api.packyapi.com",
        supports_edit=True,
        supports_reference=True,
        default_size="2048x2048",
        default_resolution="2K",
        default_aspect_ratio="1:1",
        max_outputs=4,
    ),
}


def get_model_spec(model_id: str | None) -> ImageModelSpec:
    key = (model_id or "gpt-image-2").strip().lower()
    if key in {"", "auto", "default"}:
        key = "gpt-image-2"
    if key in IMAGE_MODEL_REGISTRY:
        return IMAGE_MODEL_REGISTRY[key]
    if key.startswith("gpt-image-"):
        base = IMAGE_MODEL_REGISTRY["gpt-image-2"]
        return ImageModelSpec(
            model_id=key,
            provider="gpt_image",
            api_model=key,
            default_base_url=base.default_base_url,
            supports_edit=True,
            supports_reference=True,
            supports_batch=True,
            default_resolution=base.default_resolution,
            default_size=base.default_size,
            default_aspect_ratio=base.default_aspect_ratio,
            default_quality=base.default_quality,
            max_outputs=base.max_outputs,
            supported_output_formats=base.supported_output_formats,
            supported_backgrounds=base.supported_backgrounds,
            supported_input_fidelities=base.supported_input_fidelities,
        )
    if "banana" in key or "gemini" in key:
        return IMAGE_MODEL_REGISTRY["nano-banana"]
    if "doubao" in key or "seedream" in key:
        return IMAGE_MODEL_REGISTRY["doubao-seedream-5-0-260128"]
    return IMAGE_MODEL_REGISTRY["kolors"]


def resolve_image_dimensions(
    spec: ImageModelSpec,
    *,
    resolution: str | None = None,
    size: str | None = None,
    aspect_ratio: str | None = None,
) -> tuple[str | None, str, str | None]:
    """Map user-facing dimension hints into provider payload fields.

    This function intentionally does not enforce provider-specific allowlists.
    Unsupported combinations should fail in the provider adapter or upstream API,
    after SaaS billing reservation has been safely released on failure.
    """
    raw_resolution = _normalize_resolution(resolution)
    raw_size = _normalize_size(size)
    raw_aspect = _normalize_aspect_ratio(aspect_ratio)

    if spec.provider == "gemini":
        effective_resolution = raw_resolution or _resolution_from_size(raw_size) or spec.default_resolution
        effective_aspect = raw_aspect or _aspect_from_size(raw_size) or spec.default_aspect_ratio
        return effective_resolution, str(effective_resolution or spec.default_size or "1K"), effective_aspect

    if spec.provider == "kolors":
        if raw_size:
            effective_resolution = raw_resolution or _resolution_from_size(raw_size) or spec.default_resolution
            effective_aspect = raw_aspect or _aspect_from_size(raw_size) or spec.default_aspect_ratio
            return effective_resolution, raw_size, effective_aspect
        effective_size = _kolors_size_for_aspect(raw_aspect) or spec.default_size or "1024x1024"
        effective_resolution = raw_resolution or _resolution_from_size(effective_size) or spec.default_resolution
        effective_aspect = raw_aspect or _aspect_from_size(effective_size) or spec.default_aspect_ratio
        return effective_resolution, effective_size, effective_aspect

    if raw_size:
        effective_resolution = raw_resolution or _resolution_from_size(raw_size) or spec.default_resolution
        effective_aspect = raw_aspect or _aspect_from_size(raw_size) or spec.default_aspect_ratio
        return effective_resolution, raw_size, effective_aspect

    effective_resolution = raw_resolution or spec.default_resolution
    effective_size = spec.default_size or "auto"
    effective_aspect = raw_aspect or spec.default_aspect_ratio
    return effective_resolution, effective_size, effective_aspect


def _normalize_resolution(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"auto", "adaptive", "default"}:
        return None
    aliases = {
        "0.5k": "0.5K",
        "1k": "1K",
        "2k": "2K",
        "4k": "4K",
    }
    return aliases.get(text.lower(), text)


def _normalize_size(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"auto", "adaptive", "default"}:
        return None
    if "x" in text.lower():
        return text.lower().replace(" ", "")
    return text


def _normalize_aspect_ratio(value: str | None) -> str | None:
    text = str(value or "").strip().lower().replace(" ", "")
    if not text or text in {"auto", "adaptive", "default"}:
        return None
    return text


def _kolors_size_for_aspect(aspect_ratio: str | None) -> str | None:
    return {
        "1:1": "1024x1024",
        "3:4": "960x1280",
        "1:2": "720x1440",
        "9:16": "720x1280",
    }.get(str(aspect_ratio or "").strip().lower())


def _resolution_from_size(size: str | None) -> str | None:
    upper = str(size or "").upper()
    if upper in {"0.5K", "1K", "2K", "4K"}:
        return upper
    parsed = _parse_pixel_size(size)
    if not parsed:
        return None
    longest = max(parsed)
    if longest >= 3000:
        return "4K"
    if longest >= 1500:
        return "2K"
    return "1K"


def _aspect_from_size(size: str | None) -> str | None:
    parsed = _parse_pixel_size(size)
    if not parsed:
        return None
    width, height = parsed
    divisor = math.gcd(width, height)
    if divisor <= 0:
        return None
    return f"{width // divisor}:{height // divisor}"


def _parse_pixel_size(size: str | None) -> tuple[int, int] | None:
    match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", str(size or "").lower())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))
