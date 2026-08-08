"""Shared media generation pricing helpers."""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from typing import Any, Literal


PRICING_RULES_ENV = "OPENHARNESS_MEDIA_MODEL_PRICING_RULES"
DEFAULT_CREDITS_PER_USD = 125.0
SUPPORTED_IMAGE_SCHEMES = {"image_size_tier_pricing", "image_call_pricing"}
SUPPORTED_VIDEO_SCHEMES = {"video_seconds_pricing", "video_unit_pricing", "video_call_pricing"}
SUPPORTED_AUDIO_SCHEMES = {"audio_tts_character_pricing", "audio_tts_unit_pricing"}
SUPPORTED_MUSIC_SCHEMES = {"music_duration_pricing", "music_unit_pricing"}
APIMART_PROVIDER_FAMILY = "apimart_media"
APIMART_PRICING_SOURCE_URL = "https://apimart.ai/zh/pricing"
APIMART_SUNO_UNIT_COST_BY_ACTION = {
    "default": 0.068,
    "add_instrumental": 0.05,
    "add_instrumental-v5": 0.05,
    "add_instrumental-v5.5": 0.05,
    "add_stem": 0.05,
    "add_stem-v5.5": 0.05,
    "add_vocals": 0.05,
    "add_vocals-v5": 0.05,
    "add_vocals-v5.5": 0.05,
    "adjust_speed": 0.024,
    "aligned_lyrics": 0.0008,
    "bpm": 0.0008,
    "concat": 0.004,
    "cover": 0.05,
    "cover-v3.5": 0.05,
    "cover-v4": 0.05,
    "cover-v4.5": 0.05,
    "cover-v4.5+": 0.05,
    "cover-v4.5-all": 0.05,
    "cover-v5": 0.05,
    "cover-v5.5": 0.05,
    "create_voice": 0.016,
    "crop": 0.008,
    "extend": 0.05,
    "extend-v3.5": 0.05,
    "extend-v4": 0.05,
    "extend-v4.5": 0.05,
    "extend-v4.5+": 0.05,
    "extend-v4.5-all": 0.05,
    "extend-v5": 0.05,
    "extend-v5.5": 0.05,
    "fade_in": 0.008,
    "fade_out": 0.008,
    "generate_video": 0.004,
    "inspo": 0.068,
    "inspo-v4": 0.068,
    "inspo-v4.5": 0.068,
    "inspo-v4.5+": 0.068,
    "inspo-v4.5-all": 0.068,
    "inspo-v5": 0.068,
    "inspo-v5.5": 0.068,
    "lyrics": 0.008,
    "mashup": 0.05,
    "mashup-v3.5": 0.05,
    "mashup-v4": 0.05,
    "mashup-v4.5": 0.05,
    "mashup-v4.5+": 0.05,
    "mashup-v4.5-all": 0.05,
    "mashup-v5": 0.05,
    "mashup-v5.5": 0.05,
    "midi": 0.05,
    "music": 0.05,
    "music-v3.5": 0.05,
    "music-v4": 0.05,
    "music-v4.5": 0.05,
    "music-v4.5+": 0.05,
    "music-v4.5-all": 0.05,
    "music-v5": 0.05,
    "music-v5.5": 0.05,
    "persona": 0.004,
    "remaster": 0.05,
    "remaster-v4.5+": 0.05,
    "remaster-v5": 0.05,
    "remaster-v5.5": 0.05,
    "remove_section": 0.008,
    "replace_section": 0.05,
    "replace_section-v4": 0.05,
    "replace_section-v4.5+": 0.05,
    "replace_section-v5": 0.05,
    "replace_section-v5.5": 0.05,
    "sample": 0.05,
    "sample-v3.5": 0.05,
    "sample-v4": 0.05,
    "sample-v4.5": 0.05,
    "sample-v4.5+": 0.05,
    "sample-v4.5-all": 0.05,
    "sample-v5": 0.05,
    "sample-v5.5": 0.05,
    "sounds": 0.0096,
    "sounds-v5": 0.0096,
    "sounds-v5.5": 0.0096,
    "stems": 0.1,
    "stems_all": 0.24,
    "upload": 0.004,
    "upsample_tags": 0.004,
    "vox": 0.004,
    "wav": 0.004,
}


DEFAULT_MEDIA_MODEL_PRICING_RULES: dict[str, Any] = {
    "currency_rates": {"USD": 1.0, "CNY": 0.14},
    "credits_per_usd": DEFAULT_CREDITS_PER_USD,
    "provider_multipliers": {"apimart_media": 1.0},
    "image": {
        "apimart-gpt-image-2": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "gpt-image-2",
            "price_model_id": "gpt-image-2",
            "allowed_upstream_model_ids": ["gpt-image-2", "gpt-image-2-ext"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "default_billing_size_tier": "1K",
            "price_unit": "usd",
            "price_by_size_tier": {"1k": 0.0085, "2k": 0.014, "4k": 0.021},
            "original_price": {"default": 0.010625, "1k": 0.010625, "2k": 0.0175, "4k": 0.02625},
            "after_discount": {"default": 0.0085, "1k": 0.0085, "2k": 0.014, "4k": 0.021},
            "active_price_basis": "after_discount",
            "tier_aliases": {
                "1:1": "1k",
                "16:9": "1k",
                "9:16": "1k",
                "4:3": "1k",
                "3:4": "1k",
                "1024x1024": "1k",
                "2048x2048": "2k",
                "3840x2160": "4k",
                "2160x3840": "4k",
            },
            "max_output_count": 2,
        },
        "apimart-grok-imagine-1.5-apimart": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "grok-imagine-1.5-ext",
            "price_model_id": "grok-imagine-1.5-apimart",
            "allowed_upstream_model_ids": ["grok-imagine-1.5-apimart", "grok-imagine-1.5-ext"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "default_billing_size_tier": "1K",
            "price_unit": "usd",
            "price_by_size_tier": {"1k": 0.015},
            "original_price": {"default": 0.01875},
            "after_discount": {"default": 0.015},
            "active_price_basis": "after_discount",
            "max_output_count": 1,
        },
        "apimart-grok-imagine-1.5-edit-apimart": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "grok-imagine-1.5-edit-ext",
            "price_model_id": "grok-imagine-1.5-edit-apimart",
            "allowed_upstream_model_ids": ["grok-imagine-1.5-edit-apimart", "grok-imagine-1.5-edit-ext"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "default_billing_size_tier": "1K",
            "price_unit": "usd",
            "price_by_size_tier": {"1k": 0.015},
            "original_price": {"default": 0.01875},
            "after_discount": {"default": 0.015},
            "active_price_basis": "after_discount",
            "max_output_count": 1,
            "supports_reference": True,
            "supports_edit": True,
        },
        "apimart-imagen-4.0-apimart": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "imagen-4.0-apimart",
            "price_model_id": "imagen-4.0-apimart",
            "allowed_upstream_model_ids": ["imagen-4.0-apimart"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "default_billing_size_tier": "1K",
            "price_unit": "usd",
            "price_by_size_tier": {"1k": 0.04},
            "original_price": {"default": 0.05},
            "after_discount": {"default": 0.04},
            "active_price_basis": "after_discount",
            "max_output_count": 1,
        },
        "apimart-qwen-image-2.0": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "qwen-image-2.0",
            "price_model_id": "qwen-image-2.0",
            "allowed_upstream_model_ids": ["qwen-image-2.0"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "default_billing_size_tier": "1K",
            "price_unit": "usd",
            "price_by_size_tier": {"1k": 0.02},
            "original_price": {"default": 0.025, "1k": 0.025},
            "after_discount": {"default": 0.02, "1k": 0.02},
            "active_price_basis": "after_discount",
            "max_output_count": 1,
        },
        "apimart-qwen-image-2.0-pro": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "qwen-image-2.0-pro",
            "price_model_id": "qwen-image-2.0-pro",
            "allowed_upstream_model_ids": ["qwen-image-2.0-pro"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "default_billing_size_tier": "1K",
            "price_unit": "usd",
            "price_by_size_tier": {"1k": 0.05},
            "original_price": {"default": 0.0625, "1k": 0.0625},
            "after_discount": {"default": 0.05, "1k": 0.05},
            "active_price_basis": "after_discount",
            "max_output_count": 1,
        },
        "apimart-qwen-image-3.0": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "qwen-image-3.0",
            "price_model_id": "qwen-image-3.0",
            "allowed_upstream_model_ids": ["qwen-image-3.0"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "default_billing_size_tier": "1K",
            "price_unit": "usd",
            "price_by_size_tier": {"1k": 0.0205712, "2k": 0.0205712},
            "original_price": {"default": 0.025714, "1k": 0.025714, "2k": 0.025714},
            "after_discount": {"default": 0.0205712, "1k": 0.0205712, "2k": 0.0205712},
            "active_price_basis": "after_discount",
            "max_output_count": 1,
        },
        "apimart-qwen-image-3.0-pro": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "qwen-image-3.0-pro",
            "price_model_id": "qwen-image-3.0-pro",
            "allowed_upstream_model_ids": ["qwen-image-3.0-pro"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "default_billing_size_tier": "1K",
            "price_unit": "usd",
            "price_by_size_tier": {"1k": 0.0285712, "2k": 0.0571432},
            "original_price": {"default": 0.035714, "1k": 0.035714, "2k": 0.071429},
            "after_discount": {"default": 0.0285712, "1k": 0.0285712, "2k": 0.0571432},
            "active_price_basis": "after_discount",
            "max_output_count": 1,
        },
        "apimart-wan2.7-image": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "wan2.7-image",
            "price_model_id": "wan2.7-image",
            "allowed_upstream_model_ids": ["wan2.7-image"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "default_billing_size_tier": "1K",
            "price_unit": "usd",
            "price_by_size_tier": {"1k": 0.0216},
            "original_price": {"default": 0.027, "1k": 0.027},
            "after_discount": {"default": 0.0216, "1k": 0.0216},
            "active_price_basis": "after_discount",
            "max_output_count": 1,
        },
        "apimart-wan2.7-image-pro": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "wan2.7-image-pro",
            "price_model_id": "wan2.7-image-pro",
            "allowed_upstream_model_ids": ["wan2.7-image-pro"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "default_billing_size_tier": "1K",
            "price_unit": "usd",
            "price_by_size_tier": {"1k": 0.0544},
            "original_price": {"default": 0.068, "1k": 0.068},
            "after_discount": {"default": 0.0544, "1k": 0.0544},
            "active_price_basis": "after_discount",
            "max_output_count": 1,
        },
        "kolors": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "kolors-provider-contract",
            "source_url": "https://huggingface.co/Kwai-Kolors/Kolors",
            "source_checked_at": "2026-07-05",
            "default_billing_size_tier": "1K",
            "price_by_size_tier": {"1k": 1.0, "2k": 3.0, "4k": 5.0},
            "tier_aliases": {"1024x1024": "1k", "1792x1024": "1k", "1024x1792": "1k"},
            "max_output_count": 4,
        },
        "gpt-image-2": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "official_model_id": "gpt-image-2",
            "allowed_upstream_model_ids": ["gpt-image-2"],
            "source_url": "https://platform.openai.com/docs/pricing",
            "source_checked_at": "2026-07-11",
            "default_billing_size_tier": "1K",
            "price_by_size_tier": {"1k": 1.0, "2k": 3.0, "4k": 5.0},
            "tier_aliases": {
                "1024x1024": "1k",
                "1536x1024": "1k",
                "1024x1536": "1k",
                "1792x1024": "1k",
                "1024x1792": "1k",
                "2048x2048": "2k",
                "2048x1152": "2k",
                "1152x2048": "2k",
                "3840x2160": "4k",
                "2160x3840": "4k",
            },
            "max_output_count": 10,
        },
        "nano-banana": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "official_model_id": "gemini-2.5-flash-image",
            "allowed_upstream_model_ids": ["gemini-2.5-flash-image", "nano-banana"],
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "source_checked_at": "2026-07-09",
            "default_billing_size_tier": "1K",
            "price_by_size_tier": {"1k": 1.0, "2k": 3.0, "4k": 5.0},
            "max_output_count": 1,
        },
        "nano-banana-2": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "official_model_id": "gemini-3.1-flash-image",
            "allowed_upstream_model_ids": ["gemini-3.1-flash-image", "gemini-3.1-flash-image-preview", "nano-banana-2"],
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "source_checked_at": "2026-07-09",
            "default_billing_size_tier": "1K",
            "price_by_size_tier": {"1k": 1.0, "2k": 3.0, "4k": 5.0},
            "tier_aliases": {"0.5k": "1k"},
            "max_output_count": 1,
        },
        "nano-banana-pro": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "official_public",
            "official_model_id": "gemini-3-pro-image",
            "allowed_upstream_model_ids": ["gemini-3-pro-image", "gemini-3.0-pro-image-preview", "nano-banana-pro"],
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "source_checked_at": "2026-07-09",
            "default_billing_size_tier": "1K",
            "price_by_size_tier": {"1k": 1.0, "2k": 3.0, "4k": 5.0},
            "max_output_count": 1,
        },
        "doubao-seedream-5-0-260128": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "volcengine-media-contract",
            "source_url": "https://www.volcengine.com/docs",
            "source_checked_at": "2026-07-05",
            "default_billing_size_tier": "2K",
            "price_by_size_tier": {"1k": 1.0, "2k": 3.0, "4k": 5.0},
            "tier_aliases": {"2048x2048": "2k", "2848x1600": "2k", "1600x2848": "2k", "2304x1728": "2k", "1728x2304": "2k"},
            "max_output_count": 4,
        },
        "doubao-seedream-5-0-lite-260128": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "volcengine-media-contract",
            "source_url": "https://www.volcengine.com/docs",
            "source_checked_at": "2026-07-05",
            "default_billing_size_tier": "2K",
            "price_by_size_tier": {"1k": 1.0, "2k": 3.0, "4k": 5.0},
            "tier_aliases": {"2048x2048": "2k", "2848x1600": "2k", "1600x2848": "2k", "2304x1728": "2k", "1728x2304": "2k"},
            "max_output_count": 4,
        },
        "doubao-seedream-4-5-251128": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "volcengine-media-contract",
            "source_url": "https://www.volcengine.com/docs",
            "source_checked_at": "2026-07-05",
            "default_billing_size_tier": "2K",
            "price_by_size_tier": {"1k": 1.0, "2k": 3.0, "4k": 5.0},
            "tier_aliases": {"2048x2048": "2k", "2848x1600": "2k", "1600x2848": "2k", "2304x1728": "2k", "1728x2304": "2k"},
            "max_output_count": 4,
        },
        "doubao-seedream-4-0-250828": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_size_tier_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "volcengine-media-contract",
            "source_url": "https://www.volcengine.com/docs",
            "source_checked_at": "2026-07-05",
            "default_billing_size_tier": "2K",
            "price_by_size_tier": {"1k": 1.0, "2k": 3.0, "4k": 5.0},
            "tier_aliases": {"2048x2048": "2k", "2848x1600": "2k", "1600x2848": "2k", "2304x1728": "2k", "1728x2304": "2k"},
            "max_output_count": 4,
        },
    },
    "video": {
        "apimart-sora-2": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "sora-2",
            "price_model_id": "sora-2",
            "allowed_upstream_model_ids": ["sora-2"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "cost_per_second_by_resolution": {"720p": 0.08},
            "original_price": {"default": 0.1, "official-720P": 0.1},
            "after_discount": {"default": 0.08, "official-720P": 0.08},
            "active_price_basis": "after_discount",
            "default_duration_seconds": 8,
            "default_resolution": "720p",
            "default_mode": "standard",
        },
        "apimart-sora-2-pro": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "sora-2-pro",
            "price_model_id": "sora-2-pro",
            "allowed_upstream_model_ids": ["sora-2-pro"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "cost_per_second_by_resolution": {"720p": 0.24, "1024p": 0.4, "1080p": 0.56},
            "original_price": {"default": 0.75, "official-720P": 0.3, "official-1024P": 0.5, "official-1080P": 0.7},
            "after_discount": {"default": 0.6, "official-720P": 0.24, "official-1024P": 0.4, "official-1080P": 0.56},
            "active_price_basis": "after_discount",
            "default_duration_seconds": 8,
            "default_resolution": "720p",
            "default_mode": "standard",
        },
        "apimart-grok-imagine-1.5-video-apimart": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "grok-imagine-1.5-video-ext",
            "price_model_id": "grok-imagine-1.5-video-apimart",
            "allowed_upstream_model_ids": ["grok-imagine-1.5-video-apimart", "grok-imagine-1.5-video-ext"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "cost_per_second_by_resolution": {"480p": 0.0068, "720p": 0.012},
            "original_price": {"480P": 0.0085, "720P": 0.015},
            "after_discount": {"480P": 0.0068, "720P": 0.012},
            "active_price_basis": "after_discount",
            "default_duration_seconds": 8,
            "default_resolution": "720p",
            "default_mode": "standard",
            "supported_resolutions": ("480p", "720p"),
            "supported_durations": (4, 8, 12, 16, 20),
        },
        "apimart-veo3.1-fast": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_call_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "veo3.1-fast",
            "price_model_id": "veo3.1-fast",
            "allowed_upstream_model_ids": ["veo3.1-fast", "veo3.1-fast-official"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "call_cost_by_resolution": {"default": 0.14, "4k": 0.64},
            "call_cost_by_command": {"extend": 0.14, "extend-4k": 0.64},
            "original_price": {"default": 0.175, "4K": 0.8, "EXTEND-4K": 0.8, "extend": 0.175},
            "after_discount": {"default": 0.14, "4K": 0.64, "EXTEND-4K": 0.64, "extend": 0.14},
            "active_price_basis": "after_discount",
            "default_duration_seconds": 8,
            "default_resolution": "720p",
            "default_mode": "standard",
        },
        "apimart-veo3.1-quality": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_call_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "veo3.1-quality",
            "price_model_id": "veo3.1-quality",
            "allowed_upstream_model_ids": ["veo3.1-quality", "veo3.1-quality-official"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "call_cost_by_resolution": {"default": 1.0, "4k": 1.5},
            "call_cost_by_command": {"extend": 1.0, "extend-4k": 1.5},
            "original_price": {"default": 1.25, "4K": 1.875, "EXTEND-4K": 1.875, "extend": 1.25},
            "after_discount": {"default": 1.0, "4K": 1.5, "EXTEND-4K": 1.5, "extend": 1.0},
            "active_price_basis": "after_discount",
            "default_duration_seconds": 8,
            "default_resolution": "720p",
            "default_mode": "standard",
        },
        "doubao-seedance-2-0-260128": {
            "enabled": True,
            "currency": "CNY",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "volcengine-media-contract",
            "source_url": "https://www.volcengine.com/docs/82379/1520757",
            "source_checked_at": "2026-07-11",
            "cost_per_second_by_resolution": {"480p": 0.32, "720p": 0.32, "1080p": 0.52, "4k": 1.28},
            "default_duration_seconds": 5,
            "default_resolution": "1080p",
            "default_mode": "standard",
        },
        "doubao-seedance-2-0-fast-260128": {
            "enabled": True,
            "currency": "CNY",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "volcengine-media-contract",
            "source_url": "https://www.volcengine.com/docs/82379/1520757",
            "source_checked_at": "2026-07-11",
            "cost_per_second_by_resolution": {"480p": 0.2, "720p": 0.2, "1080p": 0.32},
            "default_duration_seconds": 5,
            "default_resolution": "720p",
            "default_mode": "fast",
        },
        "seedance-1.5-pro": {
            "enabled": True,
            "currency": "CNY",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "volcengine-media-contract",
            "source_url": "https://www.volcengine.com/docs/82379/1520757",
            "source_checked_at": "2026-07-11",
            "cost_per_second_by_resolution": {"480p": 0.38, "720p": 0.38, "1080p": 0.6, "4k": 1.5},
            "mode_multipliers": {"pro": 1.25},
            "default_duration_seconds": 5,
            "default_resolution": "1080p",
            "default_mode": "pro",
        },
        "agnes-video-v2.0": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "official_public",
            "official_model_id": "agnes-video-v2.0",
            "allowed_upstream_model_ids": ["agnes-video-v2.0"],
            "source_url": "https://wiki.agnes-ai.com/llms.txt",
            "source_checked_at": "2026-07-31",
            "cost_per_second_by_resolution": {"480p": 0.0, "720p": 0.0, "1080p": 0.0},
            "default_duration_seconds": 5,
            "default_resolution": "720p",
            "default_mode": "standard",
        },
        "veo-3.1": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "official_public",
            "official_model_id": "veo-3.1-generate-preview",
            "allowed_upstream_model_ids": ["veo-3.1-generate-preview", "veo-3.1"],
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "source_checked_at": "2026-07-11",
            "cost_per_second_by_resolution": {"720p": 0.4, "1080p": 0.4, "4k": 0.6},
            "default_duration_seconds": 8,
            "default_resolution": "1080p",
            "default_mode": "standard",
        },
        "veo-3.1-fast": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "official_public",
            "official_model_id": "veo-3.1-fast-generate-preview",
            "allowed_upstream_model_ids": ["veo-3.1-fast-generate-preview", "veo-3.1-fast"],
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "source_checked_at": "2026-07-11",
            "cost_per_second_by_resolution": {"720p": 0.1, "1080p": 0.12, "4k": 0.3},
            "default_duration_seconds": 8,
            "default_resolution": "720p",
            "default_mode": "fast",
        },
        "veo-3.1-lite": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "official_public",
            "official_model_id": "veo-3.1-fast-generate-preview",
            "allowed_upstream_model_ids": ["veo-3.1-fast-generate-preview", "veo-3.1-lite"],
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "source_checked_at": "2026-07-11",
            "cost_per_second_by_resolution": {"720p": 0.05, "1080p": 0.08},
            "default_duration_seconds": 8,
            "default_resolution": "720p",
            "default_mode": "lite",
        },
        "kling-3.0": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "kling-media-contract",
            "source_url": "https://klingai.com/document-api/pricing/base/video",
            "source_checked_at": "2026-07-11",
            "cost_per_second_by_resolution": {"720p": 0.08, "1080p": 0.12, "4k": 0.32},
            "default_duration_seconds": 5,
            "default_resolution": "1080p",
            "default_mode": "standard",
        },
        "kling-3.0-omni": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "kling-media-contract",
            "source_url": "https://klingai.com/document-api/pricing/base/video",
            "source_checked_at": "2026-07-11",
            "cost_per_second_by_resolution": {"720p": 0.12, "1080p": 0.18, "4k": 0.42},
            "default_duration_seconds": 5,
            "default_resolution": "1080p",
            "default_mode": "omni",
        },
        "kling-2.6": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "kling-media-contract",
            "source_url": "https://klingai.com/document-api/pricing/base/video",
            "source_checked_at": "2026-07-11",
            "cost_per_second_by_resolution": {"720p": 0.07, "1080p": 0.1, "4k": 0.28},
            "default_duration_seconds": 5,
            "default_resolution": "1080p",
            "default_mode": "standard",
        },
    },
    "audio": {
        "gpt-4o-mini-tts": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "audio_tts_character_pricing",
            "pricing_basis": "official_public",
            "official_model_id": "gpt-4o-mini-tts",
            "allowed_upstream_model_ids": ["gpt-4o-mini-tts"],
            "source_url": "https://platform.openai.com/docs/pricing",
            "source_checked_at": "2026-07-27",
            "cost_per_1k_chars": 0.015,
            "default_prompt_chars": 1000,
            "max_output_count": 1,
        },
        "minimax-speech-2.8-hd": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "audio_tts_character_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "minimax-tts-provider-contract",
            "official_model_id": "minimax-speech-2.8-hd",
            "allowed_upstream_model_ids": ["minimax-speech-2.8-hd"],
            "source_url": "https://platform.minimaxi.com/document/T2A%20V2?key=673b5706a4a531a2a203d209",
            "source_checked_at": "2026-07-27",
            "cost_per_1k_chars": 0.04,
            "default_prompt_chars": 1000,
            "max_output_count": 1,
        },
        "minimax-speech-2.8-turbo": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "audio_tts_character_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "minimax-tts-provider-contract",
            "official_model_id": "minimax-speech-2.8-turbo",
            "allowed_upstream_model_ids": ["minimax-speech-2.8-turbo"],
            "source_url": "https://platform.minimaxi.com/document/T2A%20V2?key=673b5706a4a531a2a203d209",
            "source_checked_at": "2026-07-27",
            "cost_per_1k_chars": 0.02,
            "default_prompt_chars": 1000,
            "max_output_count": 1,
        },
        "eleven-v3": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "audio_tts_character_pricing",
            "pricing_basis": "official_public",
            "official_model_id": "eleven_v3",
            "allowed_upstream_model_ids": ["eleven_v3", "eleven-v3"],
            "source_url": "https://elevenlabs.io/docs/overview/pricing",
            "source_checked_at": "2026-07-27",
            "cost_per_1k_chars": 0.3,
            "default_prompt_chars": 1000,
            "max_output_count": 1,
        },
    },
    "music": {
        "apimart-flowmusic": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "music_unit_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "flowmusic",
            "price_model_id": "flowmusic",
            "allowed_upstream_model_ids": ["flowmusic"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "unit_cost_by_action": {
                "default": 0.06,
                "generate": 0.06,
                "extend": 0.06,
                "replace": 0.06,
                "cover": 0.06,
                "stems": 0.06,
                "upload_audio": 0.01,
                "lyrics": 0.02,
                "download_audio": 0.02,
                "video_clip": 0.02,
            },
            "original_price": {
                "default": 0.075,
                "generate": 0.075,
                "extend": 0.075,
                "replace": 0.075,
                "cover": 0.075,
                "stems": 0.075,
                "upload_audio": 0.0125,
                "lyrics": 0.025,
                "download_audio": 0.025,
                "video_clip": 0.025,
            },
            "after_discount": {
                "default": 0.06,
                "generate": 0.06,
                "extend": 0.06,
                "replace": 0.06,
                "cover": 0.06,
                "stems": 0.06,
                "upload_audio": 0.01,
                "lyrics": 0.02,
                "download_audio": 0.02,
                "video_clip": 0.02,
            },
            "active_price_basis": "after_discount",
            "default_pricing_action": "generate",
            "supported_pricing_actions": ("generate", "extend", "replace", "cover", "stems", "upload_audio", "lyrics", "download_audio", "video_clip"),
            "default_duration_seconds": 60,
            "max_output_count": 1,
        },
        "apimart-suno": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "music_unit_pricing",
            "pricing_basis": "official_public",
            "provider_family": APIMART_PROVIDER_FAMILY,
            "official_model_id": "suno",
            "price_model_id": "suno",
            "allowed_upstream_model_ids": ["suno"],
            "source_url": APIMART_PRICING_SOURCE_URL,
            "source_checked_at": "2026-08-07",
            "unit_cost_by_action": APIMART_SUNO_UNIT_COST_BY_ACTION,
            "original_price": {action: round(price / 0.8, 6) for action, price in APIMART_SUNO_UNIT_COST_BY_ACTION.items()},
            "after_discount": dict(APIMART_SUNO_UNIT_COST_BY_ACTION),
            "active_price_basis": "after_discount",
            "default_pricing_action": "default",
            "supported_pricing_actions": tuple(APIMART_SUNO_UNIT_COST_BY_ACTION.keys()),
            "default_duration_seconds": 60,
            "max_output_count": 2,
        },
        "suno-ai": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "music_unit_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "sunoapi-org-commercial-gateway",
            "official_model_id": "V5_5",
            "allowed_upstream_model_ids": ["V5_5", "V5", "V4_5PLUS", "V4_5ALL", "V4_5", "V4"],
            "source_url": "https://docs.sunoapi.org/cn/suno-api/generate-music",
            "source_checked_at": "2026-07-29",
            "unit_cost": 0.12,
            "max_output_count": 2,
        },
        "seed-audio-1.0": {
            "enabled": True,
            "currency": "CNY",
            "multiplier": 1.0,
            "scheme": "music_duration_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "volcengine-seed-audio-contract",
            "official_model_id": "seed-audio-1.0",
            "allowed_upstream_model_ids": ["seed-audio-1.0"],
            "source_url": "https://www.volcengine.com/docs/82379",
            "source_checked_at": "2026-07-27",
            "cost_per_second": 0.08,
            "default_duration_seconds": 60,
            "max_output_count": 1,
        },
        "eleven-music-v3": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "music_duration_pricing",
            "pricing_basis": "official_public",
            "official_model_id": "eleven_music_v3",
            "allowed_upstream_model_ids": ["eleven_music_v3", "eleven-music-v3"],
            "source_url": "https://elevenlabs.io/docs/overview/pricing",
            "source_checked_at": "2026-07-27",
            "cost_per_second": 0.01,
            "default_duration_seconds": 60,
            "max_output_count": 1,
        },
        "mureka-v8": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "music_duration_pricing",
            "pricing_basis": "manual_contract",
            "contract_reference": "mureka-music-provider-contract",
            "official_model_id": "mureka-v8",
            "allowed_upstream_model_ids": ["mureka-v8"],
            "source_url": "https://platform.mureka.ai/docs",
            "source_checked_at": "2026-07-27",
            "cost_per_second": 0.01,
            "default_duration_seconds": 60,
            "max_output_count": 1,
        },
    },
}


def _apimart_original_price(value: float) -> float:
    return round(float(value) / 0.8, 6)


def _apimart_original_price_map(after_discount: dict[str, float], *, discounted: bool = True) -> dict[str, float]:
    if not discounted:
        return {key: float(value) for key, value in after_discount.items()}
    return {key: _apimart_original_price(value) for key, value in after_discount.items()}


def _apimart_image_size_rule(
    logical_model_id: str,
    official_model_id: str,
    after_discount: dict[str, float],
    *,
    default_billing_size_tier: str = "default",
    allowed_upstream_model_ids: list[str] | None = None,
    original_price: dict[str, float] | None = None,
    tier_aliases: dict[str, str] | None = None,
    max_output_count: int = 1,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "currency": "USD",
        "multiplier": 1.0,
        "scheme": "image_size_tier_pricing",
        "pricing_basis": "official_public",
        "provider_family": APIMART_PROVIDER_FAMILY,
        "official_model_id": official_model_id,
        "price_model_id": official_model_id,
        "allowed_upstream_model_ids": allowed_upstream_model_ids or [official_model_id],
        "source_url": APIMART_PRICING_SOURCE_URL,
        "source_checked_at": "2026-08-07",
        "default_billing_size_tier": default_billing_size_tier,
        "price_unit": "usd",
        "price_by_size_tier": after_discount,
        "original_price": original_price or _apimart_original_price_map(after_discount),
        "after_discount": after_discount,
        "active_price_basis": "after_discount",
        "tier_aliases": tier_aliases or {},
        "max_output_count": max_output_count,
    }


def _apimart_image_call_rule(
    logical_model_id: str,
    official_model_id: str,
    after_discount: dict[str, float],
    *,
    allowed_upstream_model_ids: list[str] | None = None,
    original_price: dict[str, float] | None = None,
    max_output_count: int = 1,
) -> dict[str, Any]:
    del logical_model_id
    return {
        "enabled": True,
        "currency": "USD",
        "multiplier": 1.0,
        "scheme": "image_call_pricing",
        "pricing_basis": "official_public",
        "provider_family": APIMART_PROVIDER_FAMILY,
        "official_model_id": official_model_id,
        "price_model_id": official_model_id,
        "allowed_upstream_model_ids": allowed_upstream_model_ids or [official_model_id],
        "source_url": APIMART_PRICING_SOURCE_URL,
        "source_checked_at": "2026-08-07",
        "call_cost_by_action": after_discount,
        "original_price": original_price or _apimart_original_price_map(after_discount),
        "after_discount": after_discount,
        "active_price_basis": "after_discount",
        "max_output_count": max_output_count,
    }


def _apimart_video_seconds_rule(
    logical_model_id: str,
    official_model_id: str,
    after_discount: dict[str, float],
    *,
    default_resolution: str,
    default_duration_seconds: int = 5,
    default_mode: str = "standard",
    allowed_upstream_model_ids: list[str] | None = None,
    original_price: dict[str, float] | None = None,
    token_settlement_after_discount: dict[str, float] | None = None,
    token_settlement_original_price: dict[str, float] | None = None,
) -> dict[str, Any]:
    del logical_model_id
    normalized_prices = {str(key).strip().lower(): float(value) for key, value in after_discount.items()}
    default_key = str(default_resolution).strip().lower()
    default_cost = normalized_prices.get(default_key) or next(iter(normalized_prices.values()))
    after_table = {"default": default_cost, **normalized_prices}
    original_table = original_price or _apimart_original_price_map(after_table)
    dimension_features: list[str] = []
    if any(key.endswith(("-input", "-reference", "-refvideo")) for key in normalized_prices):
        dimension_features.append("input")
    if any(key.endswith(("-audio", "-sound")) for key in normalized_prices):
        dimension_features.append("audio")
    rule = {
        "enabled": True,
        "currency": "USD",
        "multiplier": 1.0,
        "scheme": "video_seconds_pricing",
        "pricing_basis": "official_public",
        "provider_family": APIMART_PROVIDER_FAMILY,
        "official_model_id": official_model_id,
        "price_model_id": official_model_id,
        "allowed_upstream_model_ids": allowed_upstream_model_ids or [official_model_id],
        "source_url": APIMART_PRICING_SOURCE_URL,
        "source_checked_at": "2026-08-07",
        "cost_per_second_by_resolution": normalized_prices,
        "price_dimension_features": dimension_features,
        "original_price": original_table,
        "after_discount": after_table,
        "active_price_basis": "after_discount",
        "default_duration_seconds": default_duration_seconds,
        "default_resolution": default_resolution,
        "default_mode": default_mode,
    }
    if token_settlement_after_discount:
        normalized_token_prices = {
            str(key or "").strip().lower().replace("_", "-").replace(" ", "-"): float(value)
            for key, value in token_settlement_after_discount.items()
            if str(key or "").strip()
        }
        rule["settlement_pricing_scheme"] = "video_token_usage_pricing"
        rule["token_settlement_unit"] = "usd_per_million_tokens"
        rule["token_settlement_after_discount"] = normalized_token_prices
        rule["token_settlement_original_price"] = (
            {
                str(key or "").strip().lower().replace("_", "-").replace(" ", "-"): float(value)
                for key, value in token_settlement_original_price.items()
                if str(key or "").strip()
            }
            if token_settlement_original_price
            else _apimart_original_price_map(normalized_token_prices)
        )
    return rule


def _apimart_midjourney_action_prices() -> dict[str, float]:
    prices = {
        "default": 0.04504,
        "imagine": 0.04504,
        "imagine-fast": 0.05504,
        "imagine-turbo": 0.1,
        "video": 0.2,
        "video-720p": 0.4,
    }
    imagine_versions = ("niji6", "niji7", "v5.1", "v5.2", "v6.1", "v7", "v8.1", "v8.2")
    for version in imagine_versions:
        prices[f"imagine-{version}"] = 0.04504
        prices[f"imagine-{version}-fast"] = 0.05504
        prices[f"imagine-{version}-turbo"] = 0.1
    for action in (
        "blend", "describe", "edits", "high_variation", "inpaint", "low_variation", "modal",
        "pan", "remix_strong", "remix_subtle", "reroll", "shorten", "upscale", "variation", "zoom",
    ):
        prices[action] = 0.05504
        prices[f"{action}-fast"] = 0.05504
        prices[f"{action}-turbo"] = 0.1
    return prices


_APIMART_MIDJOURNEY_UNIT_COST_BY_ACTION = _apimart_midjourney_action_prices()


DEFAULT_MEDIA_MODEL_PRICING_RULES["image"].update(
    {
        "apimart-nano-banana": _apimart_image_size_rule(
            "apimart-nano-banana",
            "gemini-2.5-flash-image-preview",
            {"default": 0.0125, "1k": 0.0125},
            default_billing_size_tier="1K",
            allowed_upstream_model_ids=["gemini-2.5-flash-image-preview", "gemini-2.5-flash-image", "nano-banana"],
            original_price={"default": 0.015625, "1k": 0.015625},
        ),
        "apimart-nano-banana-2": _apimart_image_size_rule(
            "apimart-nano-banana-2",
            "gemini-3.1-flash-image-preview",
            {"default": 0.03, "0.5k": 0.015, "1k": 0.015, "2k": 0.02, "4k": 0.025},
            default_billing_size_tier="1K",
            allowed_upstream_model_ids=["gemini-3.1-flash-image-preview", "gemini-3.1-flash-image", "nano-banana-2"],
            original_price={"default": 0.0375, "0.5k": 0.01875, "1k": 0.01875, "2k": 0.025, "4k": 0.03125},
        ),
        "apimart-nano-banana-pro": _apimart_image_size_rule(
            "apimart-nano-banana-pro",
            "gemini-3-pro-image-preview",
            {"default": 0.03, "4k": 0.04},
            default_billing_size_tier="4K",
            allowed_upstream_model_ids=["gemini-3-pro-image-preview", "gemini-3-pro-image", "nano-banana-pro"],
            original_price={"default": 0.0375, "4k": 0.05},
        ),
        "apimart-doubao-seedream-5-0-pro": _apimart_image_size_rule(
            "apimart-doubao-seedream-5-0-pro",
            "doubao-seedream-5-0-pro",
            {"default": 0.036, "1k": 0.02928, "2k": 0.05856},
            default_billing_size_tier="1K",
            allowed_upstream_model_ids=["doubao-seedream-5-0-pro", "doubao-seedream-5-0-260128"],
            original_price={"default": 0.045, "1k": 0.0366, "2k": 0.0732},
            max_output_count=4,
        ),
        "apimart-doubao-seedream-5-0-lite": _apimart_image_size_rule(
            "apimart-doubao-seedream-5-0-lite",
            "doubao-seedream-5-0-lite",
            {"default": 0.0228, "1k": 0.0228},
            default_billing_size_tier="1K",
            allowed_upstream_model_ids=["doubao-seedream-5-0-lite", "doubao-seedream-5-0-lite-260128"],
            original_price={"default": 0.0285, "1k": 0.0285},
            max_output_count=4,
        ),
        "apimart-doubao-seedream-4-5": _apimart_image_size_rule(
            "apimart-doubao-seedream-4-5",
            "doubao-seedream-4-5",
            {"1k": 0.0228, "2k": 0.0228},
            default_billing_size_tier="1K",
            allowed_upstream_model_ids=["doubao-seedream-4-5", "doubao-seedream-4-5-251128"],
            original_price={"1k": 0.0285, "2k": 0.0285},
            max_output_count=4,
        ),
        "apimart-doubao-seedream-4-0": _apimart_image_size_rule(
            "apimart-doubao-seedream-4-0",
            "doubao-seedream-4-0",
            {"default": 0.0182, "1k": 0.0182, "2k": 0.0182},
            default_billing_size_tier="1K",
            allowed_upstream_model_ids=["doubao-seedream-4-0", "doubao-seedream-4-0-250828"],
            original_price={"default": 0.02275, "1k": 0.02275, "2k": 0.02275},
            max_output_count=4,
        ),
        "apimart-flux-kontext-pro": _apimart_image_size_rule(
            "apimart-flux-kontext-pro",
            "flux-kontext-pro",
            {"default": 0.032},
            default_billing_size_tier="default",
            original_price={"default": 0.04},
        ),
        "apimart-flux-kontext-max": _apimart_image_size_rule(
            "apimart-flux-kontext-max",
            "flux-kontext-max",
            {"default": 0.064},
            default_billing_size_tier="default",
            original_price={"default": 0.08},
        ),
        "apimart-flux-2-flex": _apimart_image_size_rule(
            "apimart-flux-2-flex",
            "flux-2-flex",
            {"1mp": 0.04, "2mp": 0.08, "3mp": 0.12, "4mp": 0.16},
            default_billing_size_tier="1MP",
            original_price={"1mp": 0.05, "2mp": 0.1, "3mp": 0.15, "4mp": 0.2},
        ),
        "apimart-flux-2-pro": _apimart_image_size_rule(
            "apimart-flux-2-pro",
            "flux-2-pro",
            {"1mp": 0.024, "2mp": 0.036, "3mp": 0.048, "4mp": 0.06},
            default_billing_size_tier="1MP",
            original_price={"1mp": 0.03, "2mp": 0.045, "3mp": 0.06, "4mp": 0.075},
        ),
        "apimart-flux-2-max": _apimart_image_size_rule(
            "apimart-flux-2-max",
            "flux-2-max",
            {"default": 0.08, "1mp": 0.056, "2mp": 0.08, "3mp": 0.104, "4mp": 0.128},
            default_billing_size_tier="default",
            original_price={"default": 0.1, "1mp": 0.07, "2mp": 0.1, "3mp": 0.13, "4mp": 0.16},
        ),
        "apimart-midjourney": _apimart_image_call_rule(
            "apimart-midjourney",
            "midjourney",
            _APIMART_MIDJOURNEY_UNIT_COST_BY_ACTION,
            allowed_upstream_model_ids=["midjourney", "mj"],
        ),
    }
)


DEFAULT_MEDIA_MODEL_PRICING_RULES["video"].update(
    {
        "apimart-doubao-seedance-2.0": _apimart_video_seconds_rule(
            "apimart-doubao-seedance-2.0",
            "doubao-seedance-2.0",
            {
                "480p": 0.066,
                "480p-input": 0.04,
                "720p": 0.142,
                "720p-input": 0.08584,
                "1080p": 0.3544,
                "1080p-input": 0.21568,
                "4k": 0.722,
                "4k-input": 0.44432,
            },
            default_resolution="1080p",
            default_duration_seconds=5,
            default_mode="standard",
        ),
        "apimart-doubao-seedance-2.0-face": _apimart_video_seconds_rule(
            "apimart-doubao-seedance-2.0-face",
            "doubao-seedance-2.0-face",
            {
                "480p": 0.0992,
                "480p-input": 0.06,
                "720p": 0.2136,
                "720p-input": 0.1288,
                "1080p": 0.5,
                "1080p-input": 0.3,
            },
            default_resolution="720p",
            default_duration_seconds=5,
            default_mode="standard",
        ),
        "apimart-doubao-seedance-2.0-fast": _apimart_video_seconds_rule(
            "apimart-doubao-seedance-2.0-fast",
            "doubao-seedance-2.0-fast",
            {
                "480p": 0.05312,
                "480p-input": 0.0316,
                "720p": 0.11416,
                "720p-input": 0.0684,
            },
            default_resolution="720p",
            default_duration_seconds=5,
            default_mode="fast",
        ),
        "apimart-doubao-seedance-2.0-fast-face": _apimart_video_seconds_rule(
            "apimart-doubao-seedance-2.0-fast-face",
            "doubao-seedance-2.0-fast-face",
            {
                "480p": 0.08,
                "480p-input": 0.048,
                "720p": 0.172,
                "720p-input": 0.1032,
            },
            default_resolution="720p",
            default_duration_seconds=5,
            default_mode="fast",
        ),
        "apimart-doubao-seedance-2.0-mini": _apimart_video_seconds_rule(
            "apimart-doubao-seedance-2.0-mini",
            "doubao-seedance-2.0-mini",
            {
                "480p": 0.02632,
                "480p-input": 0.01608,
                "720p": 0.05712,
                "720p-input": 0.03456,
            },
            default_resolution="720p",
            default_duration_seconds=5,
            default_mode="fast",
        ),
        "apimart-doubao-seedance-2.5": _apimart_video_seconds_rule(
            "apimart-doubao-seedance-2.5",
            "doubao-seedance-2.5",
            {
                "default": 0.216,
                "480p": 0.09608,
                "480p-input": 0.0576,
                "720p": 0.216,
                "720p-input": 0.1296,
            },
            default_resolution="720p",
            default_duration_seconds=5,
            default_mode="standard",
            token_settlement_after_discount={"token": 10.0, "token-input": 6.0},
            token_settlement_original_price={"token": 12.5, "token-input": 7.5},
        ),
        "apimart-happyhorse-1.0": _apimart_video_seconds_rule(
            "apimart-happyhorse-1.0",
            "happyhorse-1.0",
            {
                "default": 0.23,
                "720p": 0.13,
                "1080p": 0.23,
                "edit-720p": 0.13,
                "edit-1080p": 0.23,
            },
            default_resolution="720p",
            default_duration_seconds=5,
        ),
        "apimart-minimax-h3": _apimart_video_seconds_rule(
            "apimart-minimax-h3",
            "MiniMax-H3",
            {"default": 0.09144, "2k": 0.09144, "768p": 0.05712},
            default_resolution="2k",
            default_duration_seconds=5,
        ),
        "apimart-minimax-h3-regeneration": _apimart_video_seconds_rule(
            "apimart-minimax-h3-regeneration",
            "MiniMax-H3-Regeneration",
            {"2k": 0.03432},
            default_resolution="2k",
            default_duration_seconds=15,
        ),
        "apimart-minimax-hailuo-02": _apimart_video_seconds_rule(
            "apimart-minimax-hailuo-02",
            "MiniMax-Hailuo-02",
            {"512p": 0.0104, "768p": 0.04, "1080p": 0.08},
            default_resolution="768p",
            default_duration_seconds=5,
        ),
        "apimart-minimax-hailuo-2.3": _apimart_video_seconds_rule(
            "apimart-minimax-hailuo-2.3",
            "MiniMax-Hailuo-2.3",
            {"default": 0.0488, "1080p": 0.072},
            default_resolution="1080p",
            default_duration_seconds=5,
            default_mode="standard",
        ),
        "apimart-kling-3.0-turbo": _apimart_video_seconds_rule(
            "apimart-kling-3.0-turbo",
            "kling-3.0-turbo",
            {"720p": 0.1144, "1080p": 0.1432},
            default_resolution="1080p",
            default_duration_seconds=5,
            default_mode="turbo",
        ),
        "apimart-kling-v2-6": _apimart_video_seconds_rule(
            "apimart-kling-v2-6",
            "kling-v2-6",
            {
                "default": 0.0368,
                "pro": 0.0625,
                "pro-sound": 0.125,
                "pro-sound-voice": 0.15,
            },
            default_resolution="1080p",
            default_duration_seconds=5,
        ),
        "apimart-kling-v2-6-motion-control": _apimart_video_seconds_rule(
            "apimart-kling-v2-6-motion-control",
            "kling-v2-6-motion-control",
            {"default": 0.05712, "pro": 0.09144},
            default_resolution="1080p",
            default_duration_seconds=5,
            default_mode="standard",
        ),
        "apimart-kling-v3-motion-control": _apimart_video_seconds_rule(
            "apimart-kling-v3-motion-control",
            "kling-v3-motion-control",
            {"default": 0.10288, "pro": 0.13712},
            default_resolution="1080p",
            default_duration_seconds=5,
            default_mode="standard",
        ),
        "apimart-kling-v3-omni": _apimart_video_seconds_rule(
            "apimart-kling-v3-omni",
            "kling-v3-omni",
            {
                "default": 0.0672,
                "4k": 0.42856,
                "4k-sound": 0.42856,
                "pro": 0.0896,
                "pro-sound": 0.112,
                "pro-video": 0.1344,
                "sound": 0.0896,
                "video": 0.1008,
            },
            default_resolution="1080p",
            default_duration_seconds=5,
            default_mode="omni",
        ),
        "apimart-kling-video-o1": _apimart_video_seconds_rule(
            "apimart-kling-video-o1",
            "kling-video-o1",
            {
                "default": 0.0672,
                "pro": 0.0896,
                "pro-video": 0.1344,
                "video": 0.1008,
            },
            default_resolution="1080p",
            default_duration_seconds=5,
        ),
        "apimart-wan2.7": _apimart_video_seconds_rule(
            "apimart-wan2.7",
            "wan2.7",
            {"default": 0.0664, "1080p": 0.1096},
            default_resolution="1080p",
            default_duration_seconds=5,
        ),
        "apimart-wan2.7-r2v": _apimart_video_seconds_rule(
            "apimart-wan2.7-r2v",
            "wan2.7-r2v",
            {"default": 0.0664, "1080p": 0.1096},
            default_resolution="1080p",
            default_duration_seconds=5,
        ),
        "apimart-wan2.7-videoedit": _apimart_video_seconds_rule(
            "apimart-wan2.7-videoedit",
            "wan2.7-videoedit",
            {"default": 0.0664, "1080p": 0.1096},
            default_resolution="1080p",
            default_duration_seconds=5,
        ),
        "apimart-gemini-omni-flash-preview": _apimart_video_seconds_rule(
            "apimart-gemini-omni-flash-preview",
            "gemini-omni-flash-preview",
            {"720p": 0.088},
            default_resolution="720p",
            default_duration_seconds=8,
        ),
    }
)


@dataclass(frozen=True)
class MediaPricingResult:
    official_cost: float
    official_currency: str
    pricing_multiplier: float
    billing_units: float
    pricing_scheme: str
    pricing_basis: str
    pricing_source: str
    source_checked_at: str
    pricing_breakdown: dict[str, Any]
    provider_multiplier: float = 1.0
    price_model_id: str | None = None
    active_price_basis: str | None = None
    original_price: Any = None
    after_discount: Any = None

    def to_metadata(self) -> dict[str, Any]:
        metadata = {
            "official_cost": self.official_cost,
            "official_currency": self.official_currency,
            "pricing_multiplier": self.pricing_multiplier,
            "billing_units": self.billing_units,
            "pricing_scheme": self.pricing_scheme,
            "pricing_basis": self.pricing_basis,
            "pricing_source": self.pricing_source,
            "source_checked_at": self.source_checked_at,
            "pricing_breakdown": self.pricing_breakdown,
        }
        if self.provider_multiplier != 1.0:
            metadata["provider_multiplier"] = self.provider_multiplier
        if self.price_model_id:
            metadata["price_model_id"] = self.price_model_id
        if self.active_price_basis:
            metadata["active_price_basis"] = self.active_price_basis
        if self.original_price is not None:
            metadata["original_price"] = self.original_price
        if self.after_discount is not None:
            metadata["after_discount"] = self.after_discount
        return metadata


def load_pricing_rules(raw: Any | None = None) -> dict[str, Any]:
    if raw is None:
        raw = os.getenv(PRICING_RULES_ENV, "").strip()
    if not raw:
        raw = DEFAULT_MEDIA_MODEL_PRICING_RULES
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return validate_pricing_rules(raw)


def validate_pricing_rules(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("media_model_pricing_rules expects a JSON object")

    rules = dict(raw)
    currency_rates = rules.get("currency_rates")
    if not isinstance(currency_rates, dict) or not currency_rates:
        raise ValueError("media_model_pricing_rules.currency_rates must be a non-empty object")
    normalized_rates: dict[str, float] = {}
    for currency, rate in currency_rates.items():
        key = str(currency or "").strip().upper()
        numeric = _positive_float(rate, f"currency_rates.{key}", allow_zero=False)
        normalized_rates[key] = numeric
    if "USD" not in normalized_rates:
        raise ValueError("media_model_pricing_rules.currency_rates must include USD")

    credits_per_usd = _positive_float(rules.get("credits_per_usd", DEFAULT_CREDITS_PER_USD), "credits_per_usd", allow_zero=False)
    normalized = {
        "currency_rates": normalized_rates,
        "credits_per_usd": credits_per_usd,
        "provider_multipliers": {},
        "image": {},
        "video": {},
        "audio": {},
        "music": {},
    }
    provider_multipliers = rules.get("provider_multipliers")
    if isinstance(provider_multipliers, dict):
        normalized["provider_multipliers"] = {
            str(provider or "").strip().lower(): _positive_float(multiplier, f"provider_multipliers.{str(provider or '').strip().lower()}", allow_zero=False)
            for provider, multiplier in provider_multipliers.items()
            if str(provider or "").strip()
        }
    for kind, schemes in (
        ("image", SUPPORTED_IMAGE_SCHEMES),
        ("video", SUPPORTED_VIDEO_SCHEMES),
        ("audio", SUPPORTED_AUDIO_SCHEMES),
        ("music", SUPPORTED_MUSIC_SCHEMES),
    ):
        group = rules.get(kind)
        if group is None and kind in {"audio", "music"}:
            group = {}
        if not isinstance(group, dict):
            raise ValueError(f"media_model_pricing_rules.{kind} must be an object")
        for model_id, rule in group.items():
            key = str(model_id or "").strip().lower()
            if not key:
                raise ValueError(f"media_model_pricing_rules.{kind} contains an empty model id")
            if isinstance(rule, dict) and rule.get("enabled") is False:
                normalized[kind][key] = {"model_id": key, "enabled": False}
                continue
            normalized[kind][key] = _validate_model_rule(kind, key, rule, schemes, normalized_rates)
    return normalized


def model_rule(kind: Literal["image", "video", "audio", "music"], model_id: str | None, rules: dict[str, Any] | None = None) -> dict[str, Any] | None:
    loaded = load_pricing_rules(rules)
    group = loaded.get(kind)
    if not isinstance(group, dict):
        return None
    key = str(model_id or "").strip().lower()
    rule = group.get(key)
    if isinstance(rule, dict) and rule.get("enabled", True):
        return rule
    return None


def enabled_model_ids(kind: Literal["image", "video", "audio", "music"], rules: dict[str, Any] | None = None) -> set[str]:
    loaded = load_pricing_rules(rules)
    group = loaded.get(kind)
    if not isinstance(group, dict):
        return set()
    return {model_id for model_id, rule in group.items() if isinstance(rule, dict) and rule.get("enabled", True)}


def estimate_image_pricing(
    *,
    model_id: str,
    prompt: str = "",
    billing_size_tier: str | None = None,
    resolution: str | None = None,
    size: str | None = None,
    quality: str | None = None,
    aspect_ratio: str | None = None,
    pricing_action: str | None = None,
    output_count: int = 1,
    reference_count: int = 0,
    rules: dict[str, Any] | None = None,
) -> MediaPricingResult:
    del prompt, quality, aspect_ratio
    loaded = load_pricing_rules(rules)
    rule = model_rule("image", model_id, loaded)
    if rule is None:
        raise ValueError(f"Image model pricing is not configured for {model_id}")

    output_count = max(int(output_count or 1), 1)
    resolved_reference_count = _reference_count(reference_count)
    max_output_count = int(rule.get("max_output_count", 0) or 0)
    if max_output_count > 0 and output_count > max_output_count:
        raise ValueError(f"Image output_count {output_count} exceeds max_output_count {max_output_count} for {model_id}")
    scheme = str(rule["scheme"])
    if scheme == "image_size_tier_pricing":
        resolved_tier = _resolve_image_billing_size_tier(
            rule,
            billing_size_tier=billing_size_tier,
            resolution=resolution,
            size=size,
        )
        price_unit = str(rule.get("price_unit") or "credits").strip().lower()
        unit_price = _lookup_active_price(rule, resolved_tier, fallback_mapping=rule.get("price_by_size_tier"), field=f"image.{model_id}.price_by_size_tier.{resolved_tier}")
        if unit_price is None:
            raise ValueError(f"Image pricing does not include billing_size_tier {resolved_tier} for {model_id}")
        reference_unit_credits = _reference_unit_credits(rule)
        if price_unit == "usd":
            reference_cost = _reference_unit_cost(rule, "image") * resolved_reference_count
            official_cost = unit_price * output_count + reference_cost
            reference_charge = reference_cost
            price_unit_label = "usd"
        else:
            reference_credits = reference_unit_credits * resolved_reference_count
            billing_units = unit_price * output_count + reference_credits
            official_cost = _credits_to_official_cost(loaded, rule, billing_units)
            reference_charge = reference_credits
            price_unit_label = "credits"
        breakdown = {
            "scheme": scheme,
            "unit_credits": unit_price if price_unit == "credits" else None,
            "unit_cost": unit_price if price_unit == "usd" else None,
            "billing_size_tier": _display_billing_size_tier(resolved_tier),
            "output_count": output_count,
            "reference_count": resolved_reference_count,
            "reference_unit_credits": reference_unit_credits,
            "reference_credits": reference_charge if price_unit == "credits" else 0.0,
            "reference_cost": reference_charge if price_unit == "usd" else 0.0,
            "price_unit": price_unit_label,
        }
    elif scheme == "image_call_pricing":
        resolved_action = _normalize_key(pricing_action) or "default"
        unit_cost = _lookup_exact_active_price(
            rule,
            resolved_action,
            fallback_mapping=rule.get("call_cost_by_action"),
            field=f"image.{model_id}.call_cost_by_action.{resolved_action}",
        )
        if unit_cost is None:
            raise ValueError(f"Image pricing does not include pricing_action {resolved_action} for {model_id}")
        reference_cost = _reference_unit_cost(rule, "image") * resolved_reference_count
        official_cost = unit_cost * output_count + reference_cost
        breakdown = {
            "scheme": scheme,
            "unit_cost": unit_cost,
            "pricing_action": resolved_action,
            "output_count": output_count,
            "reference_count": resolved_reference_count,
            "reference_unit_cost": _reference_unit_cost(rule, "image"),
            "reference_cost": reference_cost,
            "price_unit": "usd",
        }
    else:
        raise ValueError(f"Unsupported image pricing scheme: {scheme}")

    return _pricing_result(loaded, rule, official_cost, breakdown)


def estimate_video_pricing(
    *,
    model_id: str,
    duration_seconds: int | float | None = None,
    resolution: str | None = None,
    mode: str | None = None,
    generate_audio: bool = False,
    command: str | None = None,
    output_count: int = 1,
    reference_count: int = 0,
    provider_usage: dict[str, Any] | None = None,
    rules: dict[str, Any] | None = None,
) -> MediaPricingResult:
    loaded = load_pricing_rules(rules)
    rule = model_rule("video", model_id, loaded)
    if rule is None:
        raise ValueError(f"Video model pricing is not configured for {model_id}")

    output_count = max(int(output_count or 1), 1)
    resolved_reference_count = _reference_count(reference_count)
    resolved_duration = max(float(duration_seconds or rule.get("default_duration_seconds") or 1), 1.0)
    resolved_resolution = _normalize_key(resolution or rule.get("default_resolution") or "720p")
    resolved_mode = _normalize_key(mode or rule.get("default_mode") or "standard")
    scheme = str(rule["scheme"])
    reference_unit_cost = _reference_unit_cost(rule)
    reference_cost = reference_unit_cost * resolved_reference_count

    if scheme == "video_seconds_pricing":
        per_second_map = rule.get("cost_per_second_by_resolution") or rule.get("usd_per_second_by_resolution")
        with_audio_map = rule.get("cost_per_second_with_audio_by_resolution") or rule.get("usd_per_second_with_audio_by_resolution")
        price_key, dimension_candidates = _video_seconds_dimension_price_key(
            rule,
            resolved_resolution,
            resolved_mode,
            command=command,
            generate_audio=generate_audio,
            reference_count=resolved_reference_count,
            base_mapping=per_second_map,
            with_audio_mapping=with_audio_map,
        )
        token_settlement_usage = _video_token_settlement_usage(rule, provider_usage)
        if token_settlement_usage is not None:
            unit_prices = token_settlement_usage["unit_prices"]
            input_tokens = float(token_settlement_usage["input_tokens"])
            output_tokens = float(token_settlement_usage["output_tokens"])
            token_input_cost = (input_tokens / 1_000_000.0) * float(unit_prices.get("token-input", 0.0))
            token_cost = (output_tokens / 1_000_000.0) * float(unit_prices.get("token", 0.0))
            official_cost = token_input_cost + token_cost
            breakdown = {
                "scheme": scheme,
                "settlement_pricing_scheme": "video_token_usage_pricing",
                "settlement_source": "provider_usage",
                "token_settlement_unit": str(rule.get("token_settlement_unit") or "usd_per_million_tokens"),
                "token_input_cost_per_million": float(unit_prices.get("token-input", 0.0)),
                "token_cost_per_million": float(unit_prices.get("token", 0.0)),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "token_input_cost": token_input_cost,
                "token_cost": token_cost,
                "price_dimension_key": price_key,
                "price_dimension_candidates": dimension_candidates,
                "duration_seconds": resolved_duration,
                "resolution": resolved_resolution,
                "mode": resolved_mode,
                "command": _normalize_key(command or "generate"),
                "output_count": output_count,
                "reference_count": resolved_reference_count,
                "reference_unit_cost": reference_unit_cost,
                "reference_cost": 0.0,
            }
            return _pricing_result(loaded, rule, official_cost, breakdown)
        actual_provider_cost = _video_actual_cost_settlement_cost(rule, provider_usage)
        if actual_provider_cost is not None:
            official_cost = actual_provider_cost["official_cost"]
            breakdown = {
                "scheme": scheme,
                "settlement_pricing_scheme": "video_token_usage_pricing",
                "settlement_source": "provider_task_cost",
                "provider_task_cost": official_cost,
                "provider_credits_cost": actual_provider_cost.get("credits_cost"),
                "price_dimension_key": price_key,
                "price_dimension_candidates": dimension_candidates,
                "duration_seconds": resolved_duration,
                "resolution": resolved_resolution,
                "mode": resolved_mode,
                "command": _normalize_key(command or "generate"),
                "output_count": output_count,
                "reference_count": resolved_reference_count,
                "reference_unit_cost": reference_unit_cost,
                "reference_cost": 0.0,
            }
            return _pricing_result(loaded, rule, official_cost, breakdown)
        if provider_usage is not None and str(rule.get("settlement_pricing_scheme") or "") == "video_token_usage_pricing":
            raise ValueError(f"Video token settlement usage is missing for {rule['model_id']}")
        exact_dimension = price_key != resolved_resolution
        if exact_dimension:
            lookup_map = with_audio_map if price_key.endswith("-audio") and isinstance(with_audio_map, dict) else per_second_map
            unit_cost = _lookup_exact_active_price(
                rule,
                price_key,
                fallback_mapping=lookup_map,
                field=f"video.{rule['model_id']}.cost_per_second_by_resolution.{price_key}",
            )
        elif generate_audio and isinstance(with_audio_map, dict):
            raw_audio_cost = _lookup_number(with_audio_map, resolved_resolution, default=None)
            unit_cost = (
                _positive_float(raw_audio_cost, f"video.{rule['model_id']}.cost_per_second_with_audio_by_resolution.{resolved_resolution}", allow_zero=False)
                if raw_audio_cost is not None
                else _lookup_active_price(
                    rule,
                    resolved_resolution,
                    fallback_mapping=with_audio_map,
                    field=f"video.{rule['model_id']}.cost_per_second_with_audio_by_resolution.{resolved_resolution}",
                )
            )
        else:
            unit_cost = _lookup_active_price(
                rule,
                resolved_resolution,
                fallback_mapping=per_second_map,
                field=f"video.{rule['model_id']}.cost_per_second_by_resolution.{resolved_resolution}",
            )
        if unit_cost is None:
            raise ValueError(f"Video pricing does not include resolution dimension {price_key} for {rule['model_id']}")
        mode_multiplier = _lookup_number(rule.get("mode_multipliers"), resolved_mode, default=1.0) or 1.0
        command_multiplier = _lookup_number(rule.get("command_multipliers"), _normalize_key(command or "generate"), default=1.0) or 1.0
        audio_multiplier = 1.0 if exact_dimension and _video_price_key_covers_feature(price_key, "audio") else float(rule.get("audio_multiplier", 1.0) or 1.0) if generate_audio else 1.0
        official_cost = unit_cost * resolved_duration * output_count * mode_multiplier * command_multiplier * audio_multiplier + reference_cost
        breakdown = {
            "scheme": scheme,
            "cost_per_second": unit_cost,
            "price_dimension_key": price_key,
            "price_dimension_candidates": dimension_candidates,
            "duration_seconds": resolved_duration,
            "resolution": resolved_resolution,
            "mode": resolved_mode,
            "mode_multiplier": mode_multiplier,
            "command": _normalize_key(command or "generate"),
            "command_multiplier": command_multiplier,
            "audio_multiplier": audio_multiplier,
            "output_count": output_count,
            "reference_count": resolved_reference_count,
            "reference_unit_cost": reference_unit_cost,
            "reference_cost": reference_cost,
        }
        if str(rule.get("settlement_pricing_scheme") or "") == "video_token_usage_pricing":
            breakdown["settlement_pricing_scheme"] = "video_token_usage_pricing"
            breakdown["settlement_source"] = "provider_usage"
            breakdown["token_settlement_unit"] = str(rule.get("token_settlement_unit") or "usd_per_million_tokens")
            breakdown["token_settlement_after_discount"] = dict(rule.get("token_settlement_after_discount") or {})
            breakdown["token_settlement_original_price"] = dict(rule.get("token_settlement_original_price") or {})
    elif scheme == "video_unit_pricing":
        unit_cost = _lookup_unit_cost(rule, resolved_mode, resolved_resolution)
        duration_factor = resolved_duration / max(float(rule.get("unit_duration_seconds", resolved_duration) or resolved_duration), 1.0)
        official_cost = unit_cost * duration_factor * output_count + reference_cost
        breakdown = {
            "scheme": scheme,
            "unit_cost": unit_cost,
            "unit_duration_seconds": float(rule.get("unit_duration_seconds", resolved_duration) or resolved_duration),
            "duration_seconds": resolved_duration,
            "resolution": resolved_resolution,
            "mode": resolved_mode,
            "output_count": output_count,
            "reference_count": resolved_reference_count,
            "reference_unit_cost": reference_unit_cost,
            "reference_cost": reference_cost,
        }
    elif scheme == "video_call_pricing":
        resolved_command = _normalize_key(command or "generate")
        call_mapping: dict[str, Any] = {}
        for mapping in (rule.get("call_cost_by_resolution"), rule.get("call_cost_by_command")):
            if isinstance(mapping, dict):
                call_mapping.update(mapping)
        unit_cost = None
        price_key = ""
        for candidate in _video_price_candidate_basis(resolved_resolution, resolved_mode, resolved_command):
            unit_cost = _lookup_exact_active_price(
                rule,
                candidate,
                fallback_mapping=call_mapping,
                field=f"video.{rule['model_id']}.video_call_pricing.{candidate}",
            )
            if unit_cost is not None:
                price_key = candidate
                break
        if unit_cost is None:
            raise ValueError(f"Video pricing does not include a call cost for {rule['model_id']}")
        official_cost = unit_cost * output_count + reference_cost
        breakdown = {
            "scheme": scheme,
            "unit_cost": unit_cost,
            "price_dimension_key": price_key,
            "duration_seconds": resolved_duration,
            "resolution": resolved_resolution,
            "mode": resolved_mode,
            "command": resolved_command,
            "output_count": output_count,
            "reference_count": resolved_reference_count,
            "reference_unit_cost": reference_unit_cost,
            "reference_cost": reference_cost,
        }
    else:
        raise ValueError(f"Unsupported video pricing scheme: {scheme}")

    return _pricing_result(loaded, rule, official_cost, breakdown)


def estimate_audio_pricing(
    *,
    model_id: str,
    prompt_chars: int | None = None,
    output_count: int = 1,
    reference_count: int = 0,
    rules: dict[str, Any] | None = None,
) -> MediaPricingResult:
    loaded = load_pricing_rules(rules)
    rule = model_rule("audio", model_id, loaded)
    if rule is None:
        raise ValueError(f"Audio model pricing is not configured for {model_id}")

    output_count = max(int(output_count or 1), 1)
    _assert_output_count(rule, output_count, "Audio")
    resolved_reference_count = _reference_count(reference_count)
    reference_unit_cost = _reference_unit_cost(rule, "audio")
    reference_cost = reference_unit_cost * resolved_reference_count
    resolved_chars = max(int(prompt_chars or rule.get("default_prompt_chars") or 1), 1)
    scheme = str(rule["scheme"])
    if scheme == "audio_tts_character_pricing":
        cost_per_1k_chars = _lookup_active_price(rule, "default", fallback_value=rule.get("cost_per_1k_chars"), field=f"audio.{model_id}.cost_per_1k_chars")
        if cost_per_1k_chars is None:
            raise ValueError(f"Audio pricing does not include cost_per_1k_chars for {model_id}")
        official_cost = cost_per_1k_chars * (resolved_chars / 1000.0) * output_count + reference_cost
        breakdown = {
            "scheme": scheme,
            "cost_per_1k_chars": cost_per_1k_chars,
            "prompt_chars": resolved_chars,
            "output_count": output_count,
            "reference_count": resolved_reference_count,
            "reference_unit_cost": reference_unit_cost,
            "reference_cost": reference_cost,
        }
    elif scheme == "audio_tts_unit_pricing":
        unit_cost = _lookup_active_price(rule, "default", fallback_value=rule.get("unit_cost"), field=f"audio.{model_id}.unit_cost", allow_zero=not rule.get("enabled", True))
        if unit_cost is None:
            raise ValueError(f"Audio pricing does not include unit_cost for {model_id}")
        official_cost = unit_cost * output_count + reference_cost
        breakdown = {
            "scheme": scheme,
            "unit_cost": unit_cost,
            "output_count": output_count,
            "reference_count": resolved_reference_count,
            "reference_unit_cost": reference_unit_cost,
            "reference_cost": reference_cost,
        }
    else:
        raise ValueError(f"Unsupported audio pricing scheme: {scheme}")

    return _pricing_result(loaded, rule, official_cost, breakdown)


def estimate_music_pricing(
    *,
    model_id: str,
    duration_seconds: int | float | None = None,
    output_count: int = 1,
    prompt_chars: int | None = None,
    pricing_action: str | None = None,
    reference_count: int = 0,
    rules: dict[str, Any] | None = None,
) -> MediaPricingResult:
    del prompt_chars
    loaded = load_pricing_rules(rules)
    rule = model_rule("music", model_id, loaded)
    if rule is None:
        raise ValueError(f"Music model pricing is not configured for {model_id}")

    output_count = max(int(output_count or 1), 1)
    _assert_output_count(rule, output_count, "Music")
    resolved_reference_count = _reference_count(reference_count)
    reference_unit_cost = _reference_unit_cost(rule, "music")
    reference_cost = reference_unit_cost * resolved_reference_count
    resolved_duration = max(float(duration_seconds or rule.get("default_duration_seconds") or 1), 1.0)
    resolved_action = _resolve_music_pricing_action(rule, pricing_action)
    scheme = str(rule["scheme"])
    if scheme == "music_duration_pricing":
        cost_per_second = _lookup_active_price(rule, "default", fallback_value=rule.get("cost_per_second"), field=f"music.{model_id}.cost_per_second")
        if cost_per_second is None:
            raise ValueError(f"Music pricing does not include cost_per_second for {model_id}")
        official_cost = cost_per_second * resolved_duration * output_count + reference_cost
        breakdown = {
            "scheme": scheme,
            "cost_per_second": cost_per_second,
            "duration_seconds": resolved_duration,
            "output_count": output_count,
            "reference_count": resolved_reference_count,
            "reference_unit_cost": reference_unit_cost,
            "reference_cost": reference_cost,
        }
    elif scheme == "music_unit_pricing":
        unit_cost = _resolve_music_unit_cost(rule, resolved_action)
        official_cost = unit_cost * output_count + reference_cost
        breakdown = {
            "scheme": scheme,
            "unit_cost": unit_cost,
            "pricing_action": resolved_action,
            "duration_seconds": resolved_duration,
            "output_count": output_count,
            "reference_count": resolved_reference_count,
            "reference_unit_cost": reference_unit_cost,
            "reference_cost": reference_cost,
        }
    else:
        raise ValueError(f"Unsupported music pricing scheme: {scheme}")

    return _pricing_result(loaded, rule, official_cost, breakdown)


def _validate_model_rule(kind: str, model_id: str, raw: Any, schemes: set[str], currency_rates: dict[str, float]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{kind}.{model_id} must be an object")
    rule = dict(raw)
    rule["model_id"] = model_id
    rule["enabled"] = bool(rule.get("enabled", True))
    scheme = str(rule.get("scheme") or "").strip()
    if scheme not in schemes:
        raise ValueError(f"{kind}.{model_id}.scheme must be one of: {', '.join(sorted(schemes))}")
    currency = str(rule.get("currency") or "").strip().upper()
    if currency not in currency_rates:
        raise ValueError(f"{kind}.{model_id}.currency must exist in currency_rates")
    multiplier = _positive_float(rule.get("multiplier", 1), f"{kind}.{model_id}.multiplier", allow_zero=True)
    source_url = str(rule.get("source_url") or "").strip()
    if not source_url.startswith(("http://", "https://")):
        raise ValueError(f"{kind}.{model_id}.source_url must be an HTTP URL")
    source_checked_at = str(rule.get("source_checked_at") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", source_checked_at):
        raise ValueError(f"{kind}.{model_id}.source_checked_at must use YYYY-MM-DD")

    rule["currency"] = currency
    rule["multiplier"] = multiplier
    rule["source_url"] = source_url
    rule["source_checked_at"] = source_checked_at
    pricing_basis = str(rule.get("pricing_basis") or "official_public").strip().lower()
    if pricing_basis not in {"official_public", "manual_contract"}:
        raise ValueError(f"{kind}.{model_id}.pricing_basis must be official_public or manual_contract")
    if pricing_basis == "official_public" and not str(rule.get("official_model_id") or model_id).strip():
        raise ValueError(f"{kind}.{model_id}.official_model_id is required")
    rule["official_model_id"] = str(rule.get("official_model_id") or model_id).strip()
    rule["price_model_id"] = str(rule.get("price_model_id") or rule["official_model_id"] or model_id).strip()
    active_price_basis = str(rule.get("active_price_basis") or "after_discount").strip().lower()
    if active_price_basis not in {"original_price", "after_discount"}:
        raise ValueError(f"{kind}.{model_id}.active_price_basis must be original_price or after_discount")
    rule["active_price_basis"] = active_price_basis
    provider_family = str(rule.get("provider_family") or "").strip().lower()
    if provider_family:
        rule["provider_family"] = provider_family
    allowed_upstream_model_ids = rule.get("allowed_upstream_model_ids")
    if allowed_upstream_model_ids is not None and (
        not isinstance(allowed_upstream_model_ids, list)
        or not allowed_upstream_model_ids
        or not all(str(item or "").strip() for item in allowed_upstream_model_ids)
    ):
        raise ValueError(f"{kind}.{model_id}.allowed_upstream_model_ids must be a non-empty string list")
    if pricing_basis == "manual_contract" and not str(rule.get("contract_reference") or "").strip():
        raise ValueError(f"{kind}.{model_id}.contract_reference is required")
    rule["pricing_basis"] = pricing_basis
    if kind == "image":
        _validate_image_scheme(model_id, rule)
    elif kind == "video":
        _validate_video_scheme(model_id, rule)
    elif kind == "audio":
        _validate_audio_scheme(model_id, rule)
    else:
        _validate_music_scheme(model_id, rule)
    return rule


def _validate_image_scheme(model_id: str, rule: dict[str, Any]) -> None:
    if rule["scheme"] == "image_call_pricing":
        action_costs = rule.get("call_cost_by_action")
        if not isinstance(action_costs, dict) or not action_costs:
            raise ValueError(f"image.{model_id}.call_cost_by_action must be a non-empty object")
        normalized_costs: dict[str, float] = {}
        for action, cost in action_costs.items():
            normalized_action = _normalize_key(action)
            if not normalized_action:
                raise ValueError(f"image.{model_id}.call_cost_by_action contains an empty action")
            normalized_costs[normalized_action] = _positive_float(cost, f"image.{model_id}.call_cost_by_action.{normalized_action}", allow_zero=False)
        if "default" not in normalized_costs:
            raise ValueError(f"image.{model_id}.call_cost_by_action.default is required")
        rule["call_cost_by_action"] = normalized_costs
        rule["max_output_count"] = int(_positive_float(rule.get("max_output_count", 1), f"image.{model_id}.max_output_count", allow_zero=False))
        if any(key in rule and rule.get(key) is not None for key in ("reference_unit_cost", "cost_per_reference", "reference_cost")):
            rule["reference_unit_cost"] = _reference_unit_cost(rule, "image")
        return
    price_unit = str(rule.get("price_unit") or "credits").strip().lower()
    if price_unit not in {"credits", "usd"}:
        raise ValueError(f"image.{model_id}.price_unit must be credits or usd")
    rule["price_unit"] = price_unit
    prices = rule.get("price_by_size_tier")
    if not isinstance(prices, dict) or not prices:
        raise ValueError(f"image.{model_id}.price_by_size_tier must be a non-empty object")
    normalized_prices: dict[str, float] = {}
    for tier, price in prices.items():
        normalized_tier = _normalize_billing_size_tier(tier)
        if not _valid_billing_size_tier(normalized_tier):
            raise ValueError(f"image.{model_id}.price_by_size_tier contains unsupported tier {tier}")
        normalized_prices[normalized_tier] = _positive_float(price, f"image.{model_id}.price_by_size_tier.{normalized_tier}", allow_zero=False)
    rule["price_by_size_tier"] = normalized_prices
    default_tier = _resolve_configured_billing_size_tier(rule.get("default_billing_size_tier"))
    if default_tier not in normalized_prices:
        raise ValueError(f"image.{model_id}.default_billing_size_tier must exist in price_by_size_tier")
    rule["default_billing_size_tier"] = default_tier.upper()
    rule["max_output_count"] = int(_positive_float(rule.get("max_output_count", 1), f"image.{model_id}.max_output_count", allow_zero=False))
    if any(key in rule and rule.get(key) is not None for key in ("reference_unit_credits", "credits_per_reference", "reference_credits")):
        rule["reference_unit_credits"] = _reference_unit_credits(rule)
    aliases = rule.get("tier_aliases")
    if aliases is not None:
        if not isinstance(aliases, dict):
            raise ValueError(f"image.{model_id}.tier_aliases must be an object")
        rule["tier_aliases"] = {
            _normalize_alias_key(alias): _resolve_configured_billing_size_tier(tier)
            for alias, tier in aliases.items()
        }


def _validate_video_scheme(model_id: str, rule: dict[str, Any]) -> None:
    if rule["scheme"] == "video_seconds_pricing":
        costs = rule.get("cost_per_second_by_resolution") or rule.get("usd_per_second_by_resolution")
        if not isinstance(costs, dict) or not costs:
            raise ValueError(f"video.{model_id}.cost_per_second_by_resolution must be a non-empty object")
        if "cost_per_second_by_resolution" not in rule:
            rule["cost_per_second_by_resolution"] = costs
        dimension_features = rule.get("price_dimension_features")
        if dimension_features is not None:
            if not isinstance(dimension_features, list) or not all(str(item or "").strip() for item in dimension_features):
                raise ValueError(f"video.{model_id}.price_dimension_features must be a string list")
            rule["price_dimension_features"] = sorted({_normalize_key(item) for item in dimension_features})
        if str(rule.get("settlement_pricing_scheme") or "") == "video_token_usage_pricing":
            token_prices = rule.get("token_settlement_after_discount")
            if not isinstance(token_prices, dict):
                raise ValueError(f"video.{model_id}.token_settlement_after_discount must be an object")
            normalized_token_prices = {
                _normalize_key(key): _positive_float(value, f"video.{model_id}.token_settlement_after_discount.{_normalize_key(key)}", allow_zero=False)
                for key, value in token_prices.items()
                if _normalize_key(key)
            }
            if "token" not in normalized_token_prices or "token-input" not in normalized_token_prices:
                raise ValueError(f"video.{model_id}.token_settlement_after_discount must include token and token-input")
            rule["token_settlement_after_discount"] = normalized_token_prices
            original_token_prices = rule.get("token_settlement_original_price")
            if isinstance(original_token_prices, dict):
                rule["token_settlement_original_price"] = {
                    _normalize_key(key): _positive_float(value, f"video.{model_id}.token_settlement_original_price.{_normalize_key(key)}", allow_zero=False)
                    for key, value in original_token_prices.items()
                    if _normalize_key(key)
                }
            rule["token_settlement_unit"] = str(rule.get("token_settlement_unit") or "usd_per_million_tokens")
    elif rule["scheme"] == "video_unit_pricing":
        if not any(isinstance(rule.get(key), dict) and rule[key] for key in ("cost_by_quality_size", "cost_by_size")) and "unit_cost" not in rule:
            raise ValueError(f"video.{model_id} must define unit_cost, cost_by_size, or cost_by_quality_size")
    elif rule["scheme"] == "video_call_pricing":
        if not any(isinstance(rule.get(key), dict) and rule[key] for key in ("call_cost_by_resolution", "call_cost_by_command")):
            raise ValueError(f"video.{model_id} must define call_cost_by_resolution or call_cost_by_command")
    if any(key in rule and rule.get(key) is not None for key in ("reference_unit_cost", "cost_per_reference", "reference_cost")):
        rule["reference_unit_cost"] = _reference_unit_cost(rule)


def _validate_audio_scheme(model_id: str, rule: dict[str, Any]) -> None:
    if rule["scheme"] == "audio_tts_character_pricing":
        rule["cost_per_1k_chars"] = _positive_float(rule.get("cost_per_1k_chars"), f"audio.{model_id}.cost_per_1k_chars", allow_zero=False)
        rule["default_prompt_chars"] = int(_positive_float(rule.get("default_prompt_chars", 1000), f"audio.{model_id}.default_prompt_chars", allow_zero=False))
    elif rule["scheme"] == "audio_tts_unit_pricing":
        rule["unit_cost"] = _positive_float(rule.get("unit_cost"), f"audio.{model_id}.unit_cost", allow_zero=not rule.get("enabled", True))
    if any(key in rule and rule.get(key) is not None for key in ("reference_unit_cost", "cost_per_reference", "reference_cost")):
        rule["reference_unit_cost"] = _reference_unit_cost(rule, "audio")
    rule["max_output_count"] = int(_positive_float(rule.get("max_output_count", 1), f"audio.{model_id}.max_output_count", allow_zero=False))


def _validate_music_scheme(model_id: str, rule: dict[str, Any]) -> None:
    if rule["scheme"] == "music_duration_pricing":
        rule["cost_per_second"] = _positive_float(rule.get("cost_per_second"), f"music.{model_id}.cost_per_second", allow_zero=False)
        rule["default_duration_seconds"] = int(_positive_float(rule.get("default_duration_seconds", 60), f"music.{model_id}.default_duration_seconds", allow_zero=False))
    elif rule["scheme"] == "music_unit_pricing":
        _validate_music_action_pricing(rule, model_id)
        if not isinstance(rule.get("unit_cost_by_action"), dict) or not rule.get("unit_cost_by_action"):
            rule["unit_cost"] = _positive_float(rule.get("unit_cost"), f"music.{model_id}.unit_cost", allow_zero=not rule.get("enabled", True))
    if any(key in rule and rule.get(key) is not None for key in ("reference_unit_cost", "cost_per_reference", "reference_cost")):
        rule["reference_unit_cost"] = _reference_unit_cost(rule, "music")
    rule["max_output_count"] = int(_positive_float(rule.get("max_output_count", 1), f"music.{model_id}.max_output_count", allow_zero=False))


def _assert_output_count(rule: dict[str, Any], output_count: int, label: str) -> None:
    max_output_count = int(rule.get("max_output_count", 0) or 0)
    if max_output_count > 0 and output_count > max_output_count:
        raise ValueError(f"{label} output_count {output_count} exceeds max_output_count {max_output_count} for {rule['model_id']}")


def _reference_count(value: Any) -> int:
    try:
        return max(int(float(value or 0)), 0)
    except (TypeError, ValueError):
        return 0


def _optional_positive_float(rule: dict[str, Any], keys: tuple[str, ...], field: str) -> float:
    for key in keys:
        if key in rule and rule.get(key) is not None:
            return _positive_float(rule.get(key), field, allow_zero=True)
    return 0.0


def _reference_unit_credits(rule: dict[str, Any]) -> float:
    return _optional_positive_float(
        rule,
        ("reference_unit_credits", "credits_per_reference", "reference_credits"),
        f"image.{rule['model_id']}.reference_unit_credits",
    )


def _reference_unit_cost(rule: dict[str, Any], kind: str = "video") -> float:
    return _optional_positive_float(
        rule,
        ("reference_unit_cost", "cost_per_reference", "reference_cost"),
        f"{kind}.{rule['model_id']}.reference_unit_cost",
    )


def _normalize_music_pricing_action(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _validate_music_action_pricing(rule: dict[str, Any], model_id: str) -> None:
    action_costs = rule.get("unit_cost_by_action")
    if action_costs is not None:
        if not isinstance(action_costs, dict) or not action_costs:
            raise ValueError(f"music.{model_id}.unit_cost_by_action must be a non-empty object")
        normalized_costs: dict[str, float] = {}
        for action, cost in action_costs.items():
            normalized_action = _normalize_music_pricing_action(action)
            if not normalized_action:
                raise ValueError(f"music.{model_id}.unit_cost_by_action contains an empty action")
            normalized_costs[normalized_action] = _positive_float(cost, f"music.{model_id}.unit_cost_by_action.{normalized_action}", allow_zero=False)
        rule["unit_cost_by_action"] = normalized_costs
    supported_actions = rule.get("supported_pricing_actions")
    if supported_actions is not None:
        if not isinstance(supported_actions, (list, tuple)) or not supported_actions:
            raise ValueError(f"music.{model_id}.supported_pricing_actions must be a non-empty string list")
        normalized_actions = []
        for action in supported_actions:
            normalized_action = _normalize_music_pricing_action(action)
            if not normalized_action:
                raise ValueError(f"music.{model_id}.supported_pricing_actions contains an empty action")
            normalized_actions.append(normalized_action)
        rule["supported_pricing_actions"] = sorted(set(normalized_actions))
    default_action = _normalize_music_pricing_action(rule.get("default_pricing_action") or "generate")
    if not default_action:
        default_action = "generate"
    if isinstance(rule.get("supported_pricing_actions"), list) and default_action not in set(rule["supported_pricing_actions"]):
        raise ValueError(f"music.{model_id}.default_pricing_action must exist in supported_pricing_actions")
    rule["default_pricing_action"] = default_action


def _resolve_music_pricing_action(rule: dict[str, Any], pricing_action: str | None) -> str:
    supported_actions = set(str(item).strip().lower() for item in (rule.get("supported_pricing_actions") or []) if str(item or "").strip())
    default_action = _normalize_music_pricing_action(rule.get("default_pricing_action") or "generate") or "generate"
    resolved_action = _normalize_music_pricing_action(pricing_action) or default_action
    if supported_actions and resolved_action not in supported_actions:
        raise ValueError(f"Music pricing action {resolved_action} is not configured for {rule['model_id']}")
    return resolved_action


def _resolve_music_unit_cost(rule: dict[str, Any], pricing_action: str) -> float:
    for action_costs in (_active_price_table(rule), rule.get("unit_cost_by_action")):
        if isinstance(action_costs, dict) and action_costs:
            unit_cost = _lookup_number(action_costs, pricing_action, default=None)
            if unit_cost is None and pricing_action != "default":
                unit_cost = _lookup_number(action_costs, "default", default=None)
            if unit_cost is not None:
                return _positive_float(unit_cost, f"music.{rule['model_id']}.unit_cost_by_action.{pricing_action}", allow_zero=False)
    return _positive_float(rule.get("unit_cost"), f"music.{rule['model_id']}.unit_cost", allow_zero=not rule.get("enabled", True))


def _pricing_result(loaded: dict[str, Any], rule: dict[str, Any], official_cost: float, breakdown: dict[str, Any]) -> MediaPricingResult:
    official_cost = round(max(float(official_cost or 0), 0.0), 8)
    currency = str(rule.get("currency") or "USD").upper()
    currency_rate = float(loaded.get("currency_rates", {}).get(currency, 0) or 0)
    credits_per_usd = float(loaded.get("credits_per_usd") or os.getenv("BILLING_CREDITS_PER_USD", DEFAULT_CREDITS_PER_USD) or DEFAULT_CREDITS_PER_USD)
    multiplier = float(rule.get("multiplier", 1) or 1)
    provider_multiplier = 1.0
    provider_family = str(rule.get("provider_family") or "").strip().lower()
    provider_multipliers = loaded.get("provider_multipliers")
    if provider_family and isinstance(provider_multipliers, dict):
        provider_multiplier = float(provider_multipliers.get(provider_family, 1.0) or 1.0)
    billing_units = official_cost * currency_rate * credits_per_usd * multiplier * provider_multiplier
    pricing_breakdown = {
        **breakdown,
        "currency_rate_to_usd": currency_rate,
        "credits_per_usd": credits_per_usd,
        "provider_multiplier": provider_multiplier,
    }
    for key in ("price_model_id", "active_price_basis", "original_price", "after_discount", "provider_family"):
        if key in rule:
            pricing_breakdown[key] = rule.get(key)
    return MediaPricingResult(
        official_cost=official_cost,
        official_currency=currency,
        pricing_multiplier=multiplier,
        billing_units=float(Decimal(str(max(billing_units, 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        pricing_scheme=str(rule.get("scheme") or ""),
        pricing_basis=str(rule.get("pricing_basis") or "official_public"),
        pricing_source=str(rule.get("source_url") or ""),
        source_checked_at=str(rule.get("source_checked_at") or ""),
        pricing_breakdown=pricing_breakdown,
        provider_multiplier=provider_multiplier,
        price_model_id=str(rule.get("price_model_id") or rule.get("official_model_id") or rule.get("model_id") or "").strip() or None,
        active_price_basis=str(rule.get("active_price_basis") or "").strip() or None,
        original_price=rule.get("original_price"),
        after_discount=rule.get("after_discount"),
    )


def _resolve_image_billing_size_tier(
    rule: dict[str, Any],
    *,
    billing_size_tier: str | None,
    resolution: str | None,
    size: str | None,
) -> str:
    configured_tiers = {_normalize_billing_size_tier(tier) for tier in (rule.get("price_by_size_tier") or {})}
    explicit_tier = _billing_size_tier_from_value(rule, billing_size_tier)
    if explicit_tier:
        if explicit_tier not in configured_tiers:
            raise ValueError(f"Image pricing tier {explicit_tier} is not configured for {rule['model_id']}")
        return explicit_tier
    inferred_tiers = [
        tier
        for tier in (
            _billing_size_tier_from_value(rule, resolution),
            _billing_size_tier_from_value(rule, size),
        )
        if tier
    ]
    if inferred_tiers:
        resolved = max(inferred_tiers, key=_billing_size_tier_rank)
        if resolved not in configured_tiers:
            raise ValueError(f"Image pricing tier {resolved} is not configured for {rule['model_id']}")
        return resolved
    default_tier = _resolve_configured_billing_size_tier(rule.get("default_billing_size_tier"))
    if default_tier not in configured_tiers:
        raise ValueError(f"Image default billing_size_tier {default_tier} is not configured for {rule['model_id']}")
    return default_tier


def _billing_size_tier_rank(tier: str) -> int:
    normalized = _normalize_billing_size_tier(tier)
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(k|mp)", normalized)
    if match:
        scale = 1_000 if match.group(2) == "k" else 1_000_000
        return int(float(match.group(1)) * scale)
    return 0


def _billing_size_tier_from_value(rule: dict[str, Any], value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"auto", "adaptive", "default"}:
        return None
    if re.fullmatch(r"\d{1,2}\s*:\s*\d{1,2}", text):
        return None
    alias_key = _normalize_alias_key(text)
    aliases = rule.get("tier_aliases")
    if isinstance(aliases, dict) and alias_key in aliases:
        return _normalize_billing_size_tier(aliases[alias_key])
    direct = _normalize_billing_size_tier(text)
    if _valid_billing_size_tier(direct):
        return direct
    parsed = _parse_pixel_size(alias_key)
    if parsed:
        width, height = parsed
        configured_tiers = {_normalize_billing_size_tier(tier) for tier in (rule.get("price_by_size_tier") or {})}
        if any(tier.endswith("mp") for tier in configured_tiers):
            megapixels = max(width * height / 1_000_000.0, 0.0)
            mp_candidates = [
                tier
                for tier in configured_tiers
                if re.fullmatch(r"\d+(?:\.\d+)?mp", tier)
            ]
            if mp_candidates:
                ranked = sorted(
                    (
                        abs(float(re.fullmatch(r"(\d+(?:\.\d+)?)mp", tier).group(1)) - megapixels),
                        -_billing_size_tier_rank(tier),
                        tier,
                    )
                    for tier in mp_candidates
                )
                return ranked[0][2]
        longest = max(parsed)
        if longest >= 3000:
            return "4k"
        if longest >= 2000:
            return "2k"
        return "1k"
    raise ValueError(f"Cannot determine image billing_size_tier from {value!r} for {rule['model_id']}")


def _resolve_configured_billing_size_tier(value: Any) -> str:
    tier = _normalize_billing_size_tier(value)
    if not _valid_billing_size_tier(tier):
        raise ValueError(f"billing_size_tier is not supported")
    return tier


def _normalize_billing_size_tier(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "")
    if text in {"default", "auto"}:
        return "default"
    if text in {"1", "1k"}:
        return "1k"
    if text in {"2", "2k"}:
        return "2k"
    if text in {"4", "4k"}:
        return "4k"
    return text


def _valid_billing_size_tier(value: str) -> bool:
    text = str(value or "").strip().lower()
    return bool(text == "default" or re.fullmatch(r"\d+(?:\.\d+)?(?:k|mp)", text) or re.fullmatch(r"[a-z][a-z0-9_.:+-]{0,63}", text))


def _display_billing_size_tier(value: str) -> str:
    text = _normalize_billing_size_tier(value)
    if text == "default":
        return "DEFAULT"
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(k|mp)", text)
    if match:
        return f"{match.group(1)}{match.group(2).upper()}"
    return text.upper()


def _normalize_alias_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def _credits_to_official_cost(loaded: dict[str, Any], rule: dict[str, Any], billing_units: float) -> float:
    currency = str(rule.get("currency") or "USD").upper()
    currency_rate = float(loaded.get("currency_rates", {}).get(currency, 0) or 0)
    credits_per_usd = float(loaded.get("credits_per_usd") or DEFAULT_CREDITS_PER_USD)
    multiplier = float(rule.get("multiplier", 1) or 1)
    divisor = currency_rate * credits_per_usd * multiplier
    if divisor <= 0:
        raise ValueError(f"Invalid credit conversion for {rule['model_id']}")
    return float(billing_units) / divisor


def _parse_pixel_size(size: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"([1-9][0-9]{2,4})x([1-9][0-9]{2,4})", str(size or "").lower())
    return (int(match.group(1)), int(match.group(2))) if match else None


def _lookup_unit_cost(rule: dict[str, Any], quality_or_mode: str, size_or_resolution: str) -> float:
    value = _lookup_nested_number(rule.get("cost_by_quality_size"), quality_or_mode, size_or_resolution)
    if value is not None:
        return value
    value = _lookup_number(rule.get("cost_by_size"), size_or_resolution, default=None)
    if value is not None:
        return value
    if rule.get("covers_all_supported_parameters") is True and "unit_cost" in rule:
        return float(rule.get("unit_cost", 0) or 0)
    raise ValueError(f"Pricing does not include {quality_or_mode}/{size_or_resolution} for {rule['model_id']}")


def _lookup_nested_number(mapping: Any, first: str, second: str) -> float | None:
    if not isinstance(mapping, dict):
        return None
    first_key = _normalize_key(first)
    second_key = _normalize_key(second)
    first_level = mapping.get(first_key) or mapping.get(first)
    if isinstance(first_level, dict):
        value = _lookup_number(first_level, second_key, default=None)
        if value is not None:
            return value
    value = mapping.get(f"{first_key}:{second_key}") or mapping.get(f"{first_key}_{second_key}") or mapping.get(f"{first_key}-{second_key}")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _lookup_number(mapping: Any, key: str, default: float | None) -> float | None:
    if not isinstance(mapping, dict):
        return default
    normalized = _normalize_key(key)
    normalized_mapping = {
        _normalize_key(raw_key): raw_value
        for raw_key, raw_value in mapping.items()
        if str(raw_key or "").strip()
    }
    value = normalized_mapping.get(normalized)
    if value is None:
        value = mapping.get(key)
    if value is None and normalized.endswith("p"):
        value = normalized_mapping.get(normalized[:-1]) or mapping.get(normalized[:-1]) or mapping.get(normalized[:-1].upper())
    if value is None and not normalized.endswith("p") and normalized.isdigit():
        value = normalized_mapping.get(f"{normalized}p") or mapping.get(f"{normalized}p") or mapping.get(f"{normalized}P")
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _active_price_table(rule: dict[str, Any]) -> dict[str, Any] | None:
    basis = str(rule.get("active_price_basis") or "after_discount").strip().lower()
    if basis not in {"original_price", "after_discount"}:
        return None
    table = rule.get(basis)
    return table if isinstance(table, dict) else None


def _lookup_active_price(
    rule: dict[str, Any],
    key: str,
    *,
    fallback_mapping: Any = None,
    fallback_value: Any = None,
    field: str,
    allow_zero: bool = False,
) -> float | None:
    normalized_key = _normalize_key(key)
    lookup_keys = [key]
    if normalized_key and not normalized_key.startswith("official-"):
        lookup_keys.append(f"official-{normalized_key}")
    if key != "default":
        lookup_keys.append("default")
    for mapping in (_active_price_table(rule), fallback_mapping):
        if not isinstance(mapping, dict):
            continue
        for lookup_key in lookup_keys:
            value = _lookup_number(mapping, lookup_key, default=None)
            if value is not None:
                return _positive_float(value, field, allow_zero=allow_zero)
    if fallback_value is not None:
        return _positive_float(fallback_value, field, allow_zero=allow_zero)
    return None


def _lookup_exact_active_price(
    rule: dict[str, Any],
    key: str,
    *,
    fallback_mapping: Any = None,
    field: str,
    allow_zero: bool = False,
) -> float | None:
    normalized_key = _normalize_key(key)
    lookup_keys = [key]
    if normalized_key and not normalized_key.startswith("official-"):
        lookup_keys.append(f"official-{normalized_key}")
    for mapping in (_active_price_table(rule), fallback_mapping):
        if not isinstance(mapping, dict):
            continue
        for lookup_key in lookup_keys:
            value = _lookup_number(mapping, lookup_key, default=None)
            if value is not None:
                return _positive_float(value, field, allow_zero=allow_zero)
    return None


def _mapping_has_normalized_key(mapping: Any, key: str) -> bool:
    if not isinstance(mapping, dict):
        return False
    normalized = _normalize_key(key)
    return any(_normalize_key(raw_key) == normalized for raw_key in mapping)


def _video_dimension_suffix_candidates(feature: str) -> tuple[str, ...]:
    normalized = _normalize_key(feature)
    if normalized in {"input", "reference"}:
        return ("input", "reference", "refvideo")
    if normalized in {"audio", "sound"}:
        return ("audio", "sound")
    return (normalized,)


def _video_match_dimension_suffix(rule: dict[str, Any], feature: str, *mappings: Any) -> str | None:
    for suffix in _video_dimension_suffix_candidates(feature):
        normalized_suffix = f"-{suffix}"
        for mapping in (_active_price_table(rule), *mappings):
            if not isinstance(mapping, dict):
                continue
            if any(_normalize_key(key).endswith(normalized_suffix) for key in mapping):
                return suffix
    return None


def _video_price_key_covers_feature(price_key: str, feature: str) -> bool:
    normalized = _normalize_key(price_key)
    return any(
        normalized == suffix or normalized.endswith(f"-{suffix}")
        for suffix in _video_dimension_suffix_candidates(feature)
    )


def _video_price_key_exists(rule: dict[str, Any], key: str, *mappings: Any) -> bool:
    return (
        _mapping_has_normalized_key(_active_price_table(rule), key)
        or any(_mapping_has_normalized_key(mapping, key) for mapping in mappings)
    )


def _video_token_settlement_usage(rule: dict[str, Any], provider_usage: dict[str, Any] | None) -> dict[str, Any] | None:
    if str(rule.get("settlement_pricing_scheme") or "") != "video_token_usage_pricing":
        return None
    if not isinstance(provider_usage, dict):
        return None
    unit_prices = rule.get("token_settlement_after_discount")
    if not isinstance(unit_prices, dict) or "token" not in unit_prices or "token-input" not in unit_prices:
        raise ValueError(f"Video token settlement prices are incomplete for {rule['model_id']}")
    usage = _find_token_usage_dict(provider_usage)
    if not isinstance(usage, dict):
        return None
    input_tokens = _usage_number(
        usage,
        "token-input",
        "token_input",
        "input_token",
        "input_tokens",
        "prompt_tokens",
        "prompt_token_count",
    )
    output_tokens = _usage_number(
        usage,
        "token",
        "tokens",
        "output_token",
        "output_tokens",
        "completion_tokens",
        "generated_tokens",
        "billable_tokens",
    )
    total_tokens = _usage_number(usage, "total_token", "total_tokens", "total")
    if output_tokens is None and total_tokens is not None:
        output_tokens = max(total_tokens - float(input_tokens or 0.0), 0.0)
    input_tokens = float(input_tokens or 0.0)
    output_tokens = float(output_tokens or 0.0)
    if input_tokens <= 0 and output_tokens <= 0:
        return None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "unit_prices": {
            "token": float(unit_prices["token"]),
            "token-input": float(unit_prices["token-input"]),
        },
    }


def _video_actual_cost_settlement_cost(rule: dict[str, Any], provider_usage: dict[str, Any] | None) -> dict[str, float] | None:
    if str(rule.get("settlement_pricing_scheme") or "") != "video_token_usage_pricing":
        return None
    if not isinstance(provider_usage, dict):
        return None
    raw_cost = _usage_number(
        provider_usage,
        "cost",
        "usd_cost",
        "provider_cost",
        "official_cost",
        "actual_cost",
        "task_cost",
    )
    if raw_cost is None:
        usage = _find_token_usage_dict(provider_usage)
        if isinstance(usage, dict):
            raw_cost = _usage_number(usage, "cost", "usd_cost", "provider_cost", "official_cost", "actual_cost", "task_cost")
    if raw_cost is None or raw_cost <= 0:
        return None
    credits_cost = _usage_number(provider_usage, "credits_cost", "credits")
    return {
        "official_cost": float(raw_cost),
        "credits_cost": float(credits_cost) if credits_cost is not None else 0.0,
    }


def _find_token_usage_dict(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    candidate_keys = {"usage", "token_usage", "billing_usage", "billing", "tokens", "usage_tokens"}
    if _usage_dict_has_token_keys(value):
        return value
    for key, item in value.items():
        if _normalize_key(str(key)) in candidate_keys and isinstance(item, dict) and _usage_dict_has_token_keys(item):
            return item
    for key in ("data", "result", "metadata", "meta", "response"):
        item = value.get(key)
        if isinstance(item, dict):
            nested = _find_token_usage_dict(item)
            if nested is not None:
                return nested
    return None


def _usage_dict_has_token_keys(value: dict[str, Any]) -> bool:
    token_keys = {
        "token",
        "tokens",
        "token-input",
        "token_input",
        "input_tokens",
        "prompt_tokens",
        "output_tokens",
        "completion_tokens",
        "generated_tokens",
        "billable_tokens",
        "total_tokens",
    }
    return any(_normalize_key(str(key)) in token_keys for key in value)


def _usage_number(value: dict[str, Any], *keys: str) -> float | None:
    wanted = {_normalize_key(key) for key in keys}
    for key, item in value.items():
        if _normalize_key(str(key)) not in wanted:
            continue
        if isinstance(item, bool):
            continue
        try:
            numeric = float(item)
        except (TypeError, ValueError):
            continue
        if numeric >= 0 and numeric == numeric:
            return numeric
    return None


def _video_price_candidate_basis(resolution: str, mode: str, command: str | None = None) -> list[str]:
    normalized_resolution = _normalize_key(resolution)
    normalized_command = _normalize_key(command)
    candidates: list[str] = []
    if normalized_command and normalized_command not in {"standard", "default", "generate"}:
        if normalized_resolution:
            candidates.append(f"{normalized_command}-{normalized_resolution}")
            candidates.append(f"{normalized_resolution}-{normalized_command}")
    normalized_mode = _normalize_key(mode)
    if normalized_mode and normalized_mode not in {"standard", "default", "generate"}:
        if normalized_resolution:
            candidates.append(f"{normalized_mode}-{normalized_resolution}")
            candidates.append(f"{normalized_resolution}-{normalized_mode}")
    candidates.append(normalized_resolution)
    if normalized_command and normalized_command not in {"standard", "default", "generate"}:
        candidates.append(normalized_command)
    if normalized_mode and normalized_mode not in {"standard", "default", "generate"}:
        candidates.append(normalized_mode)
    candidates.append("default")
    result: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in result:
            result.append(candidate)
    return result


def _video_feature_price_candidates(resolution: str, mode: str, command: str | None, suffixes: list[str]) -> list[str]:
    basis = _video_price_candidate_basis(resolution, mode, command)
    candidates: list[str] = []
    if len(suffixes) > 1:
        for base in basis:
            candidates.append(f"{base}-{'-'.join(suffixes)}")
            candidates.append(f"{base}-{'-'.join(reversed(suffixes))}")
    for base in basis:
        for suffix in suffixes:
            candidates.append(f"{base}-{suffix}")
    if len(suffixes) > 1:
        candidates.append("-".join(suffixes))
        candidates.append("-".join(reversed(suffixes)))
    candidates.extend(suffixes)
    result: list[str] = []
    for candidate in candidates:
        normalized = _normalize_key(candidate)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _video_combined_feature_price_candidates(resolution: str, mode: str, command: str | None, suffixes: list[str]) -> list[str]:
    if len(suffixes) < 2:
        return []
    candidates: list[str] = []
    for base in _video_price_candidate_basis(resolution, mode, command):
        candidates.append(f"{base}-{'-'.join(suffixes)}")
        candidates.append(f"{base}-{'-'.join(reversed(suffixes))}")
    candidates.append("-".join(suffixes))
    candidates.append("-".join(reversed(suffixes)))
    result: list[str] = []
    for candidate in candidates:
        normalized = _normalize_key(candidate)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _video_seconds_dimension_price_key(
    rule: dict[str, Any],
    resolution: str,
    mode: str,
    *,
    command: str | None,
    generate_audio: bool,
    reference_count: int,
    base_mapping: Any,
    with_audio_mapping: Any,
) -> tuple[str, list[str]]:
    normalized_resolution = _normalize_key(resolution)
    required_suffixes: list[str] = []
    input_suffix = _video_match_dimension_suffix(rule, "input", base_mapping)
    audio_suffix = _video_match_dimension_suffix(rule, "audio", base_mapping, with_audio_mapping)
    dimension_features = {_normalize_key(item) for item in (rule.get("price_dimension_features") or []) if str(item or "").strip()}
    if reference_count > 0:
        if input_suffix:
            required_suffixes.append(input_suffix)
        elif "input" in dimension_features:
            expected = ", ".join(f"{normalized_resolution}-{suffix}" for suffix in _video_dimension_suffix_candidates("input"))
            raise ValueError(f"Video pricing does not include required APIMart input dimension ({expected}) for {rule['model_id']}")
    if generate_audio:
        if audio_suffix:
            required_suffixes.append(audio_suffix)
        elif "audio" in dimension_features:
            expected = ", ".join(f"{normalized_resolution}-{suffix}" for suffix in _video_dimension_suffix_candidates("audio"))
            raise ValueError(f"Video pricing does not include required APIMart audio dimension ({expected}) for {rule['model_id']}")
    if not required_suffixes:
        for candidate in _video_price_candidate_basis(normalized_resolution, mode, command):
            if _video_price_key_exists(rule, candidate, base_mapping, with_audio_mapping):
                return candidate, []
        return normalized_resolution, []

    exact_candidates = _video_feature_price_candidates(normalized_resolution, mode, command, required_suffixes)
    if len(required_suffixes) > 1:
        combined_candidates = _video_combined_feature_price_candidates(normalized_resolution, mode, command, required_suffixes)
        for candidate in combined_candidates:
            if _video_price_key_exists(rule, candidate, base_mapping, with_audio_mapping):
                return candidate, combined_candidates
        raise ValueError(f"Video pricing does not include required APIMart dimension {', '.join(combined_candidates)} for {rule['model_id']}")

    for candidate in exact_candidates:
        if not _video_price_key_exists(rule, candidate, base_mapping, with_audio_mapping):
            continue
        price = _lookup_exact_active_price(
            rule,
            candidate,
            fallback_mapping=with_audio_mapping if _video_price_key_covers_feature(candidate, "audio") and isinstance(with_audio_mapping, dict) else base_mapping,
            field=f"video.{rule['model_id']}.cost_per_second_by_resolution.{candidate}",
        )
        if price is None:
            raise ValueError(f"Video pricing does not include required APIMart dimension {candidate} for {rule['model_id']}")
        return candidate, exact_candidates
    raise ValueError(f"Video pricing does not include required APIMart dimension {', '.join(exact_candidates)} for {rule['model_id']}")


def _normalize_key(value: str | None) -> str:
    return str(value or "").strip().lower()


def _positive_float(value: Any, field: str, *, allow_zero: bool) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} expects a number") from exc
    if numeric < 0 or (numeric == 0 and not allow_zero):
        op = "greater than 0" if not allow_zero else "greater than or equal to 0"
        raise ValueError(f"{field} must be {op}")
    return numeric
