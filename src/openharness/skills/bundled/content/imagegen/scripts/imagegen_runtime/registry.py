"""Image model registry for the bundled imagegen skill.

This registry is the runtime source of truth for image model routing and
per-image billing units. Keep user-facing docs in sync with these entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Provider = Literal["gpt_image", "openai_compatible", "gemini", "doubao"]


@dataclass(frozen=True)
class ImageModelSpec:
    model_id: str
    provider: Provider
    api_model: str
    api_key_env: str
    base_url_env: str
    default_base_url: str
    supports_edit: bool = False
    supports_reference: bool = False
    supports_batch: bool = False
    default_size: str = "auto"
    default_quality: str = "medium"


IMAGE_MODEL_REGISTRY: dict[str, ImageModelSpec] = {
    "kolors": ImageModelSpec(
        model_id="kolors",
        provider="openai_compatible",
        api_model="Kwai-Kolors/Kolors",
        api_key_env="KOLORS_IMAGE_API_KEY",
        base_url_env="KOLORS_IMAGE_BASE_URL",
        default_base_url="https://api.packyapi.com/v1",
        default_size="1024x1024",
    ),
    "gpt-image-2": ImageModelSpec(
        model_id="gpt-image-2",
        provider="gpt_image",
        api_model="gpt-image-2",
        api_key_env="GPT_IMAGEGEN_API_KEY",
        base_url_env="GPT_IMAGEGEN_BASE_URL",
        default_base_url="https://api.packyapi.com",
        supports_edit=True,
        supports_reference=True,
        supports_batch=True,
    ),
    "nano-banana": ImageModelSpec(
        model_id="nano-banana",
        provider="gemini",
        api_model="gpt-5.4-image",
        api_key_env="NANO_BANANA_API_KEY",
        base_url_env="NANO_BANANA_BASE_URL",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_edit=True,
        supports_reference=True,
    ),
    "nano-banana-2": ImageModelSpec(
        model_id="nano-banana-2",
        provider="gemini",
        api_model="gemini-3.1-flash-image-preview",
        api_key_env="NANO_BANANA_API_KEY",
        base_url_env="NANO_BANANA_BASE_URL",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_edit=True,
        supports_reference=True,
    ),
    "nano-banana-pro": ImageModelSpec(
        model_id="nano-banana-pro",
        provider="gemini",
        api_model="gemini-3.0-pro-image-preview",
        api_key_env="NANO_BANANA_API_KEY",
        base_url_env="NANO_BANANA_BASE_URL",
        default_base_url="https://generativelanguage.googleapis.com",
        supports_edit=True,
        supports_reference=True,
    ),
    "doubao-seedream-5-0-260128": ImageModelSpec(
        model_id="doubao-seedream-5-0-260128",
        provider="doubao",
        api_model="doubao-seedream-5-0-260128",
        api_key_env="DOUBAO_IMAGE_API_KEY",
        base_url_env="DOUBAO_IMAGE_BASE_URL",
        default_base_url="https://api.packyapi.com",
        supports_edit=True,
        supports_reference=True,
        default_size="2048x2048",
    ),
    "doubao-seedream-5-0-lite-260128": ImageModelSpec(
        model_id="doubao-seedream-5-0-lite-260128",
        provider="doubao",
        api_model="doubao-seedream-5-0-lite-260128",
        api_key_env="DOUBAO_IMAGE_API_KEY",
        base_url_env="DOUBAO_IMAGE_BASE_URL",
        default_base_url="https://api.packyapi.com",
        supports_edit=True,
        supports_reference=True,
        default_size="2048x2048",
    ),
    "doubao-seedream-4-5-251128": ImageModelSpec(
        model_id="doubao-seedream-4-5-251128",
        provider="doubao",
        api_model="doubao-seedream-4-5-251128",
        api_key_env="DOUBAO_IMAGE_API_KEY",
        base_url_env="DOUBAO_IMAGE_BASE_URL",
        default_base_url="https://api.packyapi.com",
        supports_edit=True,
        supports_reference=True,
        default_size="2048x2048",
    ),
    "doubao-seedream-4-0-250828": ImageModelSpec(
        model_id="doubao-seedream-4-0-250828",
        provider="doubao",
        api_model="doubao-seedream-4-0-250828",
        api_key_env="DOUBAO_IMAGE_API_KEY",
        base_url_env="DOUBAO_IMAGE_BASE_URL",
        default_base_url="https://api.packyapi.com",
        supports_edit=True,
        supports_reference=True,
        default_size="2048x2048",
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
            api_key_env=base.api_key_env,
            base_url_env=base.base_url_env,
            default_base_url=base.default_base_url,
            supports_edit=True,
            supports_reference=True,
            supports_batch=True,
        )
    if "banana" in key or "gemini" in key:
        return IMAGE_MODEL_REGISTRY["nano-banana"]
    if "doubao" in key or "seedream" in key:
        return IMAGE_MODEL_REGISTRY["doubao-seedream-5-0-260128"]
    return IMAGE_MODEL_REGISTRY["kolors"]
