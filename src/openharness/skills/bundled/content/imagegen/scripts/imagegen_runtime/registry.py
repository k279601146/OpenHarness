"""Execution routing registry for the bundled imagegen CLI.

This module selects the provider adapter and supplies lightweight execution
defaults. It is not a billing boundary and does not maintain provider-specific
dimension allowlists.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


Provider = Literal["gpt_image", "kolors", "gemini", "doubao"]


@dataclass(frozen=True)
class ImageModelSpec:
    model_id: str
    provider: Provider
    api_model: str
    default_base_url: str
    count_field: str | None = None
    size_field: str = "size"
    aspect_ratio_field: str | None = None
    aspect_to_size: dict[str, str] | None = None
    derive_size_from_aspect: bool = False
    safe_optional_fields: tuple[str, ...] = ()
    optional_field_aliases: dict[str, str] | None = None
    default_execution_parameters: dict[str, Any] | None = None
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


SPEC_DIR = Path(__file__).resolve().parents[2] / "references" / "providers" / "specs"


def _load_provider_specs() -> dict[str, ImageModelSpec]:
    registry: dict[str, ImageModelSpec] = {}
    for path in sorted(SPEC_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        provider = str(raw.get("provider") or "").strip()
        if provider not in {"gpt_image", "kolors", "gemini", "doubao"}:
            raise ValueError(f"Unsupported image provider in {path.name}: {provider}")
        model_ids = raw.get("model_ids")
        if not isinstance(model_ids, list) or not model_ids:
            raise ValueError(f"{path.name} must define non-empty model_ids")
        for raw_model_id in model_ids:
            model_id = str(raw_model_id or "").strip().lower()
            if not model_id:
                continue
            registry[model_id] = _spec_from_provider_doc(model_id, provider, raw, path)
    if "gpt-image-2" not in registry:
        raise ValueError("image provider specs must include gpt-image-2")
    return registry


def _spec_from_provider_doc(model_id: str, provider: str, raw: dict[str, Any], path: Path) -> ImageModelSpec:
    defaults = raw.get("defaults") if isinstance(raw.get("defaults"), dict) else {}
    supports = raw.get("supports") if isinstance(raw.get("supports"), dict) else {}
    return ImageModelSpec(
        model_id=model_id,
        provider=provider,  # type: ignore[arg-type]
        api_model=_api_model_for(model_id, raw.get("api_model_default")),
        default_base_url=str(raw.get("default_base_url") or "").strip(),
        count_field=_optional_string(raw.get("count_field")),
        size_field=str(raw.get("size_field") or "size").strip(),
        aspect_ratio_field=_optional_string(raw.get("aspect_ratio_field")),
        aspect_to_size=_string_map(raw.get("aspect_to_size")),
        derive_size_from_aspect=bool(raw.get("derive_size_from_aspect")),
        safe_optional_fields=tuple(_string_list(raw.get("safe_optional_fields"))),
        optional_field_aliases=_string_map(raw.get("optional_field_aliases")),
        default_execution_parameters=dict(raw.get("default_execution_parameters") or {}),
        supports_edit=bool(supports.get("edit")),
        supports_reference=bool(supports.get("reference")),
        supports_batch=bool(supports.get("batch")),
        default_resolution=_optional_string(defaults.get("resolution")),
        default_size=str(defaults.get("size") or "auto").strip(),
        default_aspect_ratio=_optional_string(defaults.get("aspect_ratio")),
        default_quality=str(defaults.get("quality") or "medium").strip(),
        max_outputs=max(int(raw.get("max_outputs") or 1), 1),
        supported_output_formats=tuple(_string_list(raw.get("supported_output_formats"))),
        supported_backgrounds=tuple(_string_list(raw.get("supported_backgrounds"))),
        supported_input_fidelities=tuple(_string_list(raw.get("supported_input_fidelities"))),
    )


def _api_model_for(model_id: str, raw_default: Any) -> str:
    if isinstance(raw_default, dict):
        return str(raw_default.get(model_id) or model_id).strip()
    if str(raw_default or "").strip() == "$model_id":
        return model_id
    return str(raw_default or model_id).strip()


def _optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key).strip(): str(item).strip()
        for key, item in value.items()
        if str(key or "").strip() and str(item or "").strip()
    }


IMAGE_MODEL_REGISTRY: dict[str, ImageModelSpec] = _load_provider_specs()


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
            count_field=base.count_field,
            size_field=base.size_field,
            aspect_ratio_field=base.aspect_ratio_field,
            aspect_to_size=base.aspect_to_size,
            derive_size_from_aspect=base.derive_size_from_aspect,
            safe_optional_fields=base.safe_optional_fields,
            optional_field_aliases=base.optional_field_aliases,
            default_execution_parameters=base.default_execution_parameters,
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

    if spec.derive_size_from_aspect:
        if raw_size:
            effective_resolution = raw_resolution or _resolution_from_size(raw_size) or spec.default_resolution
            effective_aspect = raw_aspect or _aspect_from_size(raw_size) or spec.default_aspect_ratio
            return effective_resolution, raw_size, effective_aspect
        effective_size = _size_for_aspect(spec, raw_aspect) or spec.default_size or "auto"
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


def _size_for_aspect(spec: ImageModelSpec, aspect_ratio: str | None) -> str | None:
    return (spec.aspect_to_size or {}).get(str(aspect_ratio or "").strip().lower())


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
