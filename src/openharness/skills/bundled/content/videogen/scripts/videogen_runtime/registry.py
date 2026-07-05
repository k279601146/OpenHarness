"""Video model registry for the bundled videogen skill.

This registry is the runtime source of truth for video model routing,
provider credentials, capability hints, and official-style billing dimensions.
Keep user-facing provider docs in sync with these entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Provider = Literal["seedance", "veo", "kling"]


@dataclass(frozen=True)
class VideoModelSpec:
    model_id: str
    provider: Provider
    api_model: str
    billing_scheme: str
    api_key_env: str
    base_url_env: str
    default_base_url: str
    supports_image_to_video: bool = True
    supports_first_last_frame: bool = False
    supports_reference: bool = False
    supports_audio: bool = False
    default_duration_seconds: int = 5
    default_aspect_ratio: str = "16:9"
    default_resolution: str = "720p"
    default_mode: str = "standard"


VIDEO_MODEL_REGISTRY: dict[str, VideoModelSpec] = {
    "doubao-seedance-2-0-260128": VideoModelSpec(
        model_id="doubao-seedance-2-0-260128",
        provider="seedance",
        api_model="doubao-seedance-2-0-260128",
        billing_scheme="seedance_official_dimensions",
        api_key_env="SEEDANCE_VIDEO_API_KEY",
        base_url_env="SEEDANCE_VIDEO_BASE_URL",
        default_base_url="https://ark.cn-beijing.volces.com",
        supports_first_last_frame=True,
        supports_reference=True,
        supports_audio=True,
        default_resolution="1080p",
    ),
    "doubao-seedance-2-0-fast-260128": VideoModelSpec(
        model_id="doubao-seedance-2-0-fast-260128",
        provider="seedance",
        api_model="doubao-seedance-2-0-fast-260128",
        billing_scheme="seedance_official_dimensions",
        api_key_env="SEEDANCE_VIDEO_API_KEY",
        base_url_env="SEEDANCE_VIDEO_BASE_URL",
        default_base_url="https://ark.cn-beijing.volces.com",
        supports_first_last_frame=True,
        supports_reference=True,
        supports_audio=True,
        default_resolution="720p",
        default_mode="fast",
    ),
    "seedance-1.5-pro": VideoModelSpec(
        model_id="seedance-1.5-pro",
        provider="seedance",
        api_model="doubao-seedance-1-5-pro-251215",
        billing_scheme="seedance_official_dimensions",
        api_key_env="SEEDANCE_VIDEO_API_KEY",
        base_url_env="SEEDANCE_VIDEO_BASE_URL",
        default_base_url="https://ark.cn-beijing.volces.com",
        supports_first_last_frame=True,
        supports_reference=True,
        supports_audio=True,
        default_resolution="1080p",
        default_mode="pro",
    ),
    "veo-3.1": VideoModelSpec(
        model_id="veo-3.1",
        provider="veo",
        api_model="veo-3.1-generate-preview",
        billing_scheme="google_veo_model_resolution_seconds",
        api_key_env="VEO_VIDEO_API_KEY",
        base_url_env="VEO_VIDEO_BASE_URL",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_audio=True,
        supports_first_last_frame=True,
        supports_reference=True,
        default_resolution="1080p",
    ),
    "veo-3.1-fast": VideoModelSpec(
        model_id="veo-3.1-fast",
        provider="veo",
        api_model="veo-3.1-fast-generate-preview",
        billing_scheme="google_veo_model_resolution_seconds",
        api_key_env="VEO_VIDEO_API_KEY",
        base_url_env="VEO_VIDEO_BASE_URL",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_audio=True,
        supports_first_last_frame=True,
        supports_reference=True,
        default_resolution="720p",
        default_mode="fast",
    ),
    "veo-3.1-lite": VideoModelSpec(
        model_id="veo-3.1-lite",
        provider="veo",
        api_model="veo-3.1-lite-generate-preview",
        billing_scheme="google_veo_model_resolution_seconds",
        api_key_env="VEO_VIDEO_API_KEY",
        base_url_env="VEO_VIDEO_BASE_URL",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_audio=True,
        supports_first_last_frame=True,
        supports_reference=True,
        default_resolution="720p",
        default_mode="lite",
    ),
    "kling-3.0": VideoModelSpec(
        model_id="kling-3.0",
        provider="kling",
        api_model="kling-v3",
        billing_scheme="kling_resource_units",
        api_key_env="KLING_VIDEO_API_KEY",
        base_url_env="KLING_VIDEO_BASE_URL",
        default_base_url="https://api.klingai.com",
        supports_first_last_frame=True,
        supports_reference=True,
        supports_audio=True,
        default_resolution="1080p",
    ),
    "kling-3.0-omni": VideoModelSpec(
        model_id="kling-3.0-omni",
        provider="kling",
        api_model="kling-v3-omni",
        billing_scheme="kling_resource_units",
        api_key_env="KLING_VIDEO_API_KEY",
        base_url_env="KLING_VIDEO_BASE_URL",
        default_base_url="https://api.klingai.com",
        supports_first_last_frame=True,
        supports_reference=True,
        supports_audio=True,
        default_resolution="1080p",
        default_mode="omni",
    ),
    "kling-2.6": VideoModelSpec(
        model_id="kling-2.6",
        provider="kling",
        api_model="kling-v2-6",
        billing_scheme="kling_resource_units",
        api_key_env="KLING_VIDEO_API_KEY",
        base_url_env="KLING_VIDEO_BASE_URL",
        default_base_url="https://api.klingai.com",
        supports_first_last_frame=True,
        supports_reference=True,
        supports_audio=True,
        default_resolution="1080p",
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
