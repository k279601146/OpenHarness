"""Video model registry for the bundled videogen skill.

This registry is the runtime source of truth for video model routing,
provider credentials, capability hints, and official-style billing dimensions.
Keep user-facing provider docs in sync with these entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


Provider = Literal["seedance", "veo", "kling"]


@dataclass(frozen=True)
class VideoModelSpec:
    model_id: str
    provider: Provider
    api_model: str
    billing_scheme: str
    default_base_url: str
    supports_image_to_video: bool = True
    supports_first_last_frame: bool = False
    supports_reference: bool = False
    supports_audio: bool = False
    supports_watermark: bool = False
    default_duration_seconds: int = 5
    default_aspect_ratio: str = "16:9"
    default_resolution: str = "720p"
    default_mode: str = "standard"
    supported_aspect_ratios: tuple[str, ...] = ("16:9", "9:16", "1:1")
    supported_resolutions: tuple[str, ...] = ("720p",)
    supported_durations: tuple[int, ...] = (5,)
    duration_presets_by_resolution: tuple[tuple[str, tuple[int, ...]], ...] = ()
    supported_modes: tuple[str, ...] = ("standard",)
    max_outputs: int = 4
    reference_limits: dict[str, Any] | None = None


SEEDANCE_ASPECT_RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive")
SEEDANCE_VIDEO_RESOLUTIONS = ("480p", "720p", "1080p", "4k")
SEEDANCE_FAST_VIDEO_RESOLUTIONS = ("480p", "720p", "1080p")
STANDARD_VIDEO_DURATIONS = tuple(range(2, 16))
VEO_VIDEO_DURATIONS = (4, 6, 8)
VEO_DURATION_PRESETS = (("720p", VEO_VIDEO_DURATIONS), ("1080p", (8,)), ("4k", (8,)))
VEO_LITE_DURATION_PRESETS = (("720p", VEO_VIDEO_DURATIONS), ("1080p", (8,)))
KLING_3_VIDEO_DURATIONS = tuple(range(3, 16))
KLING_VIDEO_DURATIONS = (5, 10)
SEEDANCE_REFERENCE_LIMITS = {
    "images": 9,
    "videos": 3,
    "audios": 3,
    "image_max_bytes": 30 * 1024 * 1024,
    "video_max_bytes": 50 * 1024 * 1024,
    "audio_max_bytes": 15 * 1024 * 1024,
    "video_duration_seconds": (2, 15),
    "audio_duration_seconds": (2, 15),
    "mime_types": (
        "image/jpeg",
        "image/png",
        "image/webp",
        "video/mp4",
        "video/quicktime",
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
    ),
}
VEO_REFERENCE_LIMITS = {
    "images": 3,
    "videos": 0,
    "audios": 0,
    "image_max_bytes": 20 * 1024 * 1024,
    "mime_types": ("image/jpeg", "image/png", "image/webp"),
}
KLING_REFERENCE_LIMITS = {
    "images": 7,
    "videos": 1,
    "audios": 0,
    "image_max_bytes": 10 * 1024 * 1024,
    "video_max_bytes": 200 * 1024 * 1024,
    "video_duration_seconds": (3, 15),
    "mime_types": ("image/jpeg", "image/png", "video/mp4", "video/quicktime"),
}


VIDEO_MODEL_REGISTRY: dict[str, VideoModelSpec] = {
    "doubao-seedance-2-0-260128": VideoModelSpec(
        model_id="doubao-seedance-2-0-260128",
        provider="seedance",
        api_model="doubao-seedance-2-0-260128",
        billing_scheme="seedance_official_dimensions",
        default_base_url="https://ark.cn-beijing.volces.com",
        supports_first_last_frame=True,
        supports_reference=True,
        supports_audio=True,
        default_resolution="1080p",
        supported_aspect_ratios=SEEDANCE_ASPECT_RATIOS,
        supported_resolutions=SEEDANCE_VIDEO_RESOLUTIONS,
        supported_durations=STANDARD_VIDEO_DURATIONS,
        supported_modes=("standard",),
        reference_limits=SEEDANCE_REFERENCE_LIMITS,
    ),
    "doubao-seedance-2-0-fast-260128": VideoModelSpec(
        model_id="doubao-seedance-2-0-fast-260128",
        provider="seedance",
        api_model="doubao-seedance-2-0-fast-260128",
        billing_scheme="seedance_official_dimensions",
        default_base_url="https://ark.cn-beijing.volces.com",
        supports_first_last_frame=True,
        supports_reference=True,
        supports_audio=True,
        default_resolution="720p",
        default_mode="fast",
        supported_aspect_ratios=SEEDANCE_ASPECT_RATIOS,
        supported_resolutions=SEEDANCE_FAST_VIDEO_RESOLUTIONS,
        supported_durations=STANDARD_VIDEO_DURATIONS,
        supported_modes=("fast",),
        reference_limits=SEEDANCE_REFERENCE_LIMITS,
    ),
    "seedance-1.5-pro": VideoModelSpec(
        model_id="seedance-1.5-pro",
        provider="seedance",
        api_model="doubao-seedance-1-5-pro-251215",
        billing_scheme="seedance_official_dimensions",
        default_base_url="https://ark.cn-beijing.volces.com",
        supports_first_last_frame=True,
        supports_reference=True,
        supports_audio=True,
        default_resolution="1080p",
        default_mode="pro",
        supported_aspect_ratios=SEEDANCE_ASPECT_RATIOS,
        supported_resolutions=SEEDANCE_VIDEO_RESOLUTIONS,
        supported_durations=STANDARD_VIDEO_DURATIONS,
        supported_modes=("pro",),
        reference_limits=SEEDANCE_REFERENCE_LIMITS,
    ),
    "veo-3.1": VideoModelSpec(
        model_id="veo-3.1",
        provider="veo",
        api_model="veo-3.1-generate-preview",
        billing_scheme="google_veo_model_resolution_seconds",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_audio=True,
        supports_first_last_frame=True,
        supports_reference=True,
        default_duration_seconds=8,
        default_resolution="1080p",
        supported_aspect_ratios=("16:9", "9:16"),
        supported_resolutions=("720p", "1080p", "4k"),
        supported_durations=VEO_VIDEO_DURATIONS,
        duration_presets_by_resolution=VEO_DURATION_PRESETS,
        supported_modes=("standard",),
        reference_limits=VEO_REFERENCE_LIMITS,
    ),
    "veo-3.1-fast": VideoModelSpec(
        model_id="veo-3.1-fast",
        provider="veo",
        api_model="veo-3.1-fast-generate-preview",
        billing_scheme="google_veo_model_resolution_seconds",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_audio=True,
        supports_first_last_frame=True,
        supports_reference=True,
        default_duration_seconds=8,
        default_resolution="720p",
        default_mode="fast",
        supported_aspect_ratios=("16:9", "9:16"),
        supported_resolutions=("720p", "1080p", "4k"),
        supported_durations=VEO_VIDEO_DURATIONS,
        duration_presets_by_resolution=VEO_DURATION_PRESETS,
        supported_modes=("fast",),
        reference_limits=VEO_REFERENCE_LIMITS,
    ),
    "veo-3.1-lite": VideoModelSpec(
        model_id="veo-3.1-lite",
        provider="veo",
        api_model="veo-3.1-lite-generate-preview",
        billing_scheme="google_veo_model_resolution_seconds",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_audio=True,
        supports_first_last_frame=True,
        supports_reference=True,
        default_duration_seconds=8,
        default_resolution="720p",
        default_mode="lite",
        supported_aspect_ratios=("16:9", "9:16"),
        supported_resolutions=("720p", "1080p"),
        supported_durations=VEO_VIDEO_DURATIONS,
        duration_presets_by_resolution=VEO_LITE_DURATION_PRESETS,
        supported_modes=("lite",),
        reference_limits=VEO_REFERENCE_LIMITS,
    ),
    "kling-3.0": VideoModelSpec(
        model_id="kling-3.0",
        provider="kling",
        api_model="kling-v3",
        billing_scheme="kling_resource_units",
        default_base_url="https://api.klingai.com",
        supports_first_last_frame=True,
        supports_reference=True,
        supports_audio=True,
        default_resolution="1080p",
        supported_aspect_ratios=("16:9", "9:16", "1:1"),
        supported_resolutions=("720p", "1080p", "4k"),
        supported_durations=KLING_3_VIDEO_DURATIONS,
        supported_modes=("standard",),
        reference_limits=KLING_REFERENCE_LIMITS,
    ),
    "kling-3.0-omni": VideoModelSpec(
        model_id="kling-3.0-omni",
        provider="kling",
        api_model="kling-v3-omni",
        billing_scheme="kling_resource_units",
        default_base_url="https://api.klingai.com",
        supports_first_last_frame=True,
        supports_reference=True,
        supports_audio=True,
        default_resolution="1080p",
        default_mode="omni",
        supported_aspect_ratios=("16:9", "9:16", "1:1"),
        supported_resolutions=("720p", "1080p", "4k"),
        supported_durations=KLING_3_VIDEO_DURATIONS,
        supported_modes=("omni",),
        reference_limits=KLING_REFERENCE_LIMITS,
    ),
    "kling-2.6": VideoModelSpec(
        model_id="kling-2.6",
        provider="kling",
        api_model="kling-v2-6",
        billing_scheme="kling_resource_units",
        default_base_url="https://api.klingai.com",
        supports_first_last_frame=True,
        supports_reference=True,
        supports_audio=True,
        default_resolution="1080p",
        supported_aspect_ratios=("16:9", "9:16", "1:1"),
        supported_resolutions=("720p", "1080p", "4k"),
        supported_durations=KLING_VIDEO_DURATIONS,
        supported_modes=("standard",),
        reference_limits=KLING_REFERENCE_LIMITS,
    ),
}


ALIASES: dict[str, str] = {
    "keling-3.0": "kling-3.0",
    "keling-3.0-omni": "kling-3.0-omni",
    "keling-2.6": "kling-2.6",
    "keling-o1": "kling-3.0-omni",
    "video3.1": "veo-3.1",
    "video3.1-fast": "veo-3.1-fast",
    "video3.1-lite": "veo-3.1-lite",
    "video3": "veo-3.1",
    "video3-fast": "veo-3.1-fast",
    "video3-lite": "veo-3.1-lite",
}


DEFAULT_VIDEO_MODEL = "doubao-seedance-2-0-260128"


def get_model_spec(model_id: str | None) -> VideoModelSpec:
    key = (model_id or DEFAULT_VIDEO_MODEL).strip().lower()
    if key in {"", "auto", "default"}:
        key = DEFAULT_VIDEO_MODEL
    key = ALIASES.get(key, key)
    if key in VIDEO_MODEL_REGISTRY:
        return VIDEO_MODEL_REGISTRY[key]
    if "keling" in key or "kling" in key:
        return VIDEO_MODEL_REGISTRY["kling-3.0"]
    if "video3" in key or "veo" in key:
        return VIDEO_MODEL_REGISTRY["veo-3.1"]
    if "seedance" in key or "doubao" in key:
        return VIDEO_MODEL_REGISTRY[DEFAULT_VIDEO_MODEL]
    return VIDEO_MODEL_REGISTRY[DEFAULT_VIDEO_MODEL]


def supported_durations_for_resolution(spec: VideoModelSpec, resolution: str | None) -> tuple[int, ...]:
    normalized = str(resolution or "").strip().lower()
    for preset_resolution, durations in spec.duration_presets_by_resolution:
        if str(preset_resolution).strip().lower() == normalized:
            return durations
    return spec.supported_durations
