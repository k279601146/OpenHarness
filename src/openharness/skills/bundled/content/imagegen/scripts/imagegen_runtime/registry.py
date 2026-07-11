"""Image model registry for the bundled imagegen skill.

This registry is the runtime source of truth for image model routing and
per-image billing units. Keep user-facing docs in sync with these entries.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal


Provider = Literal["gpt_image", "openai_compatible", "gemini", "doubao"]


@dataclass(frozen=True)
class ImageModelSpec:
    model_id: str
    provider: Provider
    api_model: str
    default_base_url: str
    supports_edit: bool = False
    supports_reference: bool = False
    supports_batch: bool = False
    dimension_mode: Literal["exact_size", "resolution_aspect"] = "exact_size"
    default_resolution: str | None = None
    default_size: str = "auto"
    default_aspect_ratio: str | None = None
    default_quality: str = "medium"
    supported_sizes: tuple[str, ...] = ("auto",)
    supported_resolutions: tuple[str, ...] = ()
    supported_aspect_ratios: tuple[str, ...] = ()
    size_presets: tuple[tuple[str, str, str], ...] = ()
    supported_qualities: tuple[str, ...] = ("medium",)
    max_outputs: int = 1
    supports_flexible_size: bool = False
    supported_output_formats: tuple[str, ...] = ()
    supported_backgrounds: tuple[str, ...] = ()
    supported_input_fidelities: tuple[str, ...] = ()


GPT_IMAGE_2_SIZES = (
    "1024x1024",
    "1536x1024",
    "1024x1536",
    "1792x1024",
    "1024x1792",
    "2048x2048",
    "2048x1152",
    "1152x2048",
    "3840x2160",
    "2160x3840",
)
GPT_IMAGE_2_QUALITIES = ("auto", "low", "medium", "high")
GPT_IMAGE_2_ASPECT_RATIOS = ("1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "16:9", "9:16", "2:1", "1:2", "21:9", "9:21")
DOUBAO_IMAGE_SIZES = ("2048x2048", "2848x1600", "1600x2848", "2304x1728", "1728x2304")
DOUBAO_IMAGE_ASPECT_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4")
KOLORS_IMAGE_SIZES = ("1024x1024", "1792x1024", "1024x1792")
KOLORS_IMAGE_ASPECT_RATIOS = ("1:1", "16:9", "9:16")
GPT_IMAGE_2_MIN_PIXELS = 655_360
GPT_IMAGE_2_MAX_PIXELS = 8_294_400
GPT_IMAGE_2_MAX_EDGE = 3840
GPT_IMAGE_2_MAX_RATIO = 3.0
GPT_IMAGE_2_SIZE_MULTIPLE = 16
GEMINI_IMAGE_ASPECT_RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")
GEMINI_3_1_IMAGE_ASPECT_RATIOS = GEMINI_IMAGE_ASPECT_RATIOS + ("1:4", "4:1", "1:8", "8:1")

GPT_IMAGE_2_PRESETS = (
    ("1K", "1:1", "1024x1024"),
    ("1K", "3:2", "1536x1024"),
    ("1K", "2:3", "1024x1536"),
    ("1K", "16:9", "1792x1024"),
    ("1K", "9:16", "1024x1792"),
    ("2K", "1:1", "2048x2048"),
    ("2K", "16:9", "2048x1152"),
    ("2K", "9:16", "1152x2048"),
    ("4K", "16:9", "3840x2160"),
    ("4K", "9:16", "2160x3840"),
)
DOUBAO_IMAGE_PRESETS = (
    ("2K", "1:1", "2048x2048"),
    ("2K", "16:9", "2848x1600"),
    ("2K", "9:16", "1600x2848"),
    ("2K", "4:3", "2304x1728"),
    ("2K", "3:4", "1728x2304"),
)
KOLORS_IMAGE_PRESETS = (
    ("1K", "1:1", "1024x1024"),
    ("1K", "16:9", "1792x1024"),
    ("1K", "9:16", "1024x1792"),
)


IMAGE_MODEL_REGISTRY: dict[str, ImageModelSpec] = {
    "kolors": ImageModelSpec(
        model_id="kolors",
        provider="openai_compatible",
        api_model="Kwai-Kolors/Kolors",
        default_base_url="https://api.packyapi.com/v1",
        default_size="1024x1024",
        default_resolution="1K",
        default_aspect_ratio="1:1",
        supported_sizes=KOLORS_IMAGE_SIZES,
        supported_resolutions=("1K",),
        supported_aspect_ratios=KOLORS_IMAGE_ASPECT_RATIOS,
        size_presets=KOLORS_IMAGE_PRESETS,
        supported_qualities=("medium",),
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
        default_size="1024x1024",
        default_resolution="1K",
        default_aspect_ratio="1:1",
        supported_sizes=GPT_IMAGE_2_SIZES,
        supported_resolutions=("1K", "2K", "4K"),
        supported_aspect_ratios=GPT_IMAGE_2_ASPECT_RATIOS,
        size_presets=GPT_IMAGE_2_PRESETS,
        supported_qualities=GPT_IMAGE_2_QUALITIES,
        max_outputs=10,
        supports_flexible_size=True,
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
        dimension_mode="resolution_aspect",
        default_resolution="1K",
        default_size="1K",
        default_aspect_ratio="1:1",
        supported_sizes=("1K",),
        supported_resolutions=("1K",),
        supported_aspect_ratios=GEMINI_IMAGE_ASPECT_RATIOS,
        supported_qualities=("medium",),
    ),
    "nano-banana-2": ImageModelSpec(
        model_id="nano-banana-2",
        provider="gemini",
        api_model="gemini-3.1-flash-image",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_edit=True,
        supports_reference=True,
        dimension_mode="resolution_aspect",
        default_resolution="1K",
        default_size="1K",
        default_aspect_ratio="1:1",
        supported_sizes=("0.5K", "1K", "2K", "4K"),
        supported_resolutions=("0.5K", "1K", "2K", "4K"),
        supported_aspect_ratios=GEMINI_3_1_IMAGE_ASPECT_RATIOS,
        supported_qualities=("medium",),
    ),
    "nano-banana-pro": ImageModelSpec(
        model_id="nano-banana-pro",
        provider="gemini",
        api_model="gemini-3-pro-image",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_edit=True,
        supports_reference=True,
        dimension_mode="resolution_aspect",
        default_resolution="1K",
        default_size="1K",
        default_aspect_ratio="1:1",
        supported_sizes=("1K", "2K", "4K"),
        supported_resolutions=("1K", "2K", "4K"),
        supported_aspect_ratios=GEMINI_IMAGE_ASPECT_RATIOS,
        supported_qualities=("medium", "high"),
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
        supported_sizes=DOUBAO_IMAGE_SIZES,
        supported_resolutions=("2K",),
        supported_aspect_ratios=DOUBAO_IMAGE_ASPECT_RATIOS,
        size_presets=DOUBAO_IMAGE_PRESETS,
        supported_qualities=("medium",),
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
        supported_sizes=DOUBAO_IMAGE_SIZES,
        supported_resolutions=("2K",),
        supported_aspect_ratios=DOUBAO_IMAGE_ASPECT_RATIOS,
        size_presets=DOUBAO_IMAGE_PRESETS,
        supported_qualities=("medium",),
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
        supported_sizes=DOUBAO_IMAGE_SIZES,
        supported_resolutions=("2K",),
        supported_aspect_ratios=DOUBAO_IMAGE_ASPECT_RATIOS,
        size_presets=DOUBAO_IMAGE_PRESETS,
        supported_qualities=("medium",),
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
        supported_sizes=DOUBAO_IMAGE_SIZES,
        supported_resolutions=("2K",),
        supported_aspect_ratios=DOUBAO_IMAGE_ASPECT_RATIOS,
        size_presets=DOUBAO_IMAGE_PRESETS,
        supported_qualities=("medium",),
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
            dimension_mode=base.dimension_mode,
            default_resolution=base.default_resolution,
            default_size=base.default_size,
            default_aspect_ratio=base.default_aspect_ratio,
            default_quality=base.default_quality,
            supported_sizes=base.supported_sizes,
            supported_resolutions=base.supported_resolutions,
            supported_aspect_ratios=base.supported_aspect_ratios,
            size_presets=base.size_presets,
            supported_qualities=base.supported_qualities,
            max_outputs=base.max_outputs,
            supports_flexible_size=base.supports_flexible_size,
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
    """Resolve user-facing dimensions into one provider-safe effective combination."""
    raw_resolution = str(resolution or "").strip().upper() or None
    raw_size = str(size or "").strip()
    raw_aspect = str(aspect_ratio or "").strip().lower() or None
    if raw_size.lower() == "auto":
        raw_size = ""
    if raw_aspect in {"auto", "adaptive"}:
        raw_aspect = None
    if raw_aspect and raw_size.lower() == str(spec.default_size).lower():
        raw_size = ""

    preset_by_size = next((item for item in spec.size_presets if item[2].lower() == raw_size.lower()), None)
    if preset_by_size:
        if raw_resolution and raw_resolution != preset_by_size[0].upper():
            raise ValueError("Image size conflicts with resolution")
        if raw_aspect and raw_aspect != preset_by_size[1].lower():
            raise ValueError("Image size conflicts with aspect_ratio")
        raw_resolution = preset_by_size[0].upper()
        raw_aspect = preset_by_size[1].lower()

    if raw_size and not preset_by_size and spec.supports_flexible_size and _is_valid_flexible_image_size(raw_size):
        effective_resolution = raw_resolution or _resolution_from_size(raw_size) or spec.default_resolution
        size_aspect = _aspect_from_size(raw_size)
        if raw_aspect and size_aspect and not _same_aspect_ratio(raw_aspect, size_aspect):
            raise ValueError("Image size conflicts with aspect_ratio")
        effective_aspect = raw_aspect or size_aspect
        return effective_resolution, raw_size, effective_aspect

    if spec.dimension_mode == "resolution_aspect":
        effective_resolution = raw_resolution or _resolution_from_size(raw_size) or spec.default_resolution
        effective_aspect = raw_aspect or _aspect_from_size(raw_size) or spec.default_aspect_ratio
        _ensure_member("resolution", effective_resolution, spec.supported_resolutions)
        _ensure_member("aspect_ratio", effective_aspect, spec.supported_aspect_ratios)
        return effective_resolution, str(effective_resolution), effective_aspect

    if raw_size:
        if raw_aspect and not spec.supports_flexible_size:
            _ensure_member("aspect_ratio", raw_aspect, spec.supported_aspect_ratios)
        _ensure_member("size", raw_size, spec.supported_sizes)
        return raw_resolution or spec.default_resolution, raw_size, raw_aspect or _aspect_from_size(raw_size)

    effective_resolution = raw_resolution or spec.default_resolution
    effective_aspect = raw_aspect or spec.default_aspect_ratio
    preset = next(
        (
            item
            for item in spec.size_presets
            if (not effective_resolution or item[0].upper() == str(effective_resolution).upper())
            and (not effective_aspect or item[1].lower() == str(effective_aspect).lower())
        ),
        None,
    )
    if preset:
        return preset[0].upper(), preset[2], preset[1].lower()
    if spec.supports_flexible_size and effective_aspect:
        flexible_size = _flexible_size_from_aspect(effective_aspect, effective_resolution)
        if flexible_size:
            size_aspect = _aspect_from_size(flexible_size)
            returned_aspect = effective_aspect if size_aspect and _same_aspect_ratio(effective_aspect, size_aspect) else size_aspect or effective_aspect
            return effective_resolution or _resolution_from_size(flexible_size) or spec.default_resolution, flexible_size, returned_aspect
        if raw_aspect:
            raise ValueError(f"Unsupported image aspect_ratio: {raw_aspect}")
    if effective_aspect and not spec.supports_flexible_size:
        _ensure_member("aspect_ratio", effective_aspect, spec.supported_aspect_ratios)
    effective_size = spec.default_size
    _ensure_member("size", effective_size, spec.supported_sizes)
    return effective_resolution, effective_size, effective_aspect or _aspect_from_size(effective_size)


def _ensure_member(parameter: str, value: str | None, supported: tuple[str, ...]) -> None:
    if value is None or not supported:
        return
    if not any(str(item).lower() == str(value).lower() for item in supported):
        raise ValueError(f"Unsupported image {parameter}: {value}")


def _resolution_from_size(size: str) -> str | None:
    upper = size.upper()
    if upper in {"0.5K", "1K", "2K", "4K"}:
        return upper
    if "x" not in size.lower():
        return None
    try:
        width, height = (int(part) for part in size.lower().split("x", 1))
    except ValueError:
        return None
    longest = max(width, height)
    if longest >= 3000:
        return "4K"
    if longest >= 1500:
        return "2K"
    return "1K"


def _aspect_from_size(size: str) -> str | None:
    preset = next((item for item in (*GPT_IMAGE_2_PRESETS, *DOUBAO_IMAGE_PRESETS, *KOLORS_IMAGE_PRESETS) if item[2].lower() == size.lower()), None)
    if preset:
        return preset[1].lower()
    parsed = _parse_pixel_size(size)
    if not parsed:
        return None
    width, height = parsed
    divisor = math.gcd(width, height)
    if divisor <= 0:
        return None
    return f"{width // divisor}:{height // divisor}"


def _parse_pixel_size(size: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", str(size or "").lower())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _parse_aspect_ratio(aspect_ratio: str | None) -> tuple[int, int] | None:
    match = re.fullmatch(r"([1-9][0-9]?):([1-9][0-9]?)", str(aspect_ratio or "").strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _same_aspect_ratio(left: str | None, right: str | None) -> bool:
    parsed_left = _parse_aspect_ratio(left)
    parsed_right = _parse_aspect_ratio(right)
    if not parsed_left or not parsed_right:
        return False
    return parsed_left[0] * parsed_right[1] == parsed_right[0] * parsed_left[1]


def _is_valid_flexible_image_size(size: str) -> bool:
    parsed = _parse_pixel_size(size)
    if parsed is None:
        return False
    width, height = parsed
    max_edge = max(width, height)
    min_edge = min(width, height)
    total_pixels = width * height
    if max_edge > GPT_IMAGE_2_MAX_EDGE:
        return False
    if width % GPT_IMAGE_2_SIZE_MULTIPLE != 0 or height % GPT_IMAGE_2_SIZE_MULTIPLE != 0:
        return False
    if max_edge / min_edge > GPT_IMAGE_2_MAX_RATIO:
        return False
    return GPT_IMAGE_2_MIN_PIXELS <= total_pixels <= GPT_IMAGE_2_MAX_PIXELS


def _flexible_size_from_aspect(aspect_ratio: str | None, resolution: str | None) -> str | None:
    match = re.fullmatch(r"([1-9][0-9]?):([1-9][0-9]?)", str(aspect_ratio or "").strip())
    if not match:
        return None
    ratio_width, ratio_height = int(match.group(1)), int(match.group(2))
    if ratio_width == ratio_height:
        square = 2880 if str(resolution or "").upper() == "4K" else 2048 if str(resolution or "").upper() == "2K" else 1024
        size = f"{square}x{square}"
        return size if _is_valid_flexible_image_size(size) else None

    base_short_edge = 2160 if str(resolution or "").upper() == "4K" else 1536 if str(resolution or "").upper() == "2K" else 1024
    unit = (base_short_edge // min(ratio_width, ratio_height) // GPT_IMAGE_2_SIZE_MULTIPLE) * GPT_IMAGE_2_SIZE_MULTIPLE
    while unit >= GPT_IMAGE_2_SIZE_MULTIPLE:
        size = f"{ratio_width * unit}x{ratio_height * unit}"
        if _is_valid_flexible_image_size(size):
            return size
        unit -= GPT_IMAGE_2_SIZE_MULTIPLE
    return None
