"""Shared media generation pricing helpers."""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from typing import Any, Literal


PRICING_RULES_ENV = "OPENHARNESS_MEDIA_MODEL_PRICING_RULES"
DEFAULT_CREDITS_PER_USD = 25.0
SUPPORTED_IMAGE_SCHEMES = {"image_size_tier_pricing"}
SUPPORTED_VIDEO_SCHEMES = {"video_seconds_pricing", "video_unit_pricing"}


DEFAULT_MEDIA_MODEL_PRICING_RULES: dict[str, Any] = {
    "currency_rates": {"USD": 1.0, "CNY": 0.14},
    "credits_per_usd": DEFAULT_CREDITS_PER_USD,
    "image": {
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
}


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

    def to_metadata(self) -> dict[str, Any]:
        return {
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
        "image": {},
        "video": {},
    }
    for kind, schemes in (("image", SUPPORTED_IMAGE_SCHEMES), ("video", SUPPORTED_VIDEO_SCHEMES)):
        group = rules.get(kind)
        if not isinstance(group, dict):
            raise ValueError(f"media_model_pricing_rules.{kind} must be an object")
        for model_id, rule in group.items():
            key = str(model_id or "").strip().lower()
            if not key:
                raise ValueError(f"media_model_pricing_rules.{kind} contains an empty model id")
            normalized[kind][key] = _validate_model_rule(kind, key, rule, schemes, normalized_rates)
    return normalized


def model_rule(kind: Literal["image", "video"], model_id: str | None, rules: dict[str, Any] | None = None) -> dict[str, Any] | None:
    loaded = load_pricing_rules(rules)
    group = loaded.get(kind)
    if not isinstance(group, dict):
        return None
    key = str(model_id or "").strip().lower()
    rule = group.get(key)
    if isinstance(rule, dict) and rule.get("enabled", True):
        return rule
    return None


def enabled_model_ids(kind: Literal["image", "video"], rules: dict[str, Any] | None = None) -> set[str]:
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
    output_count: int = 1,
    reference_count: int = 0,
    rules: dict[str, Any] | None = None,
) -> MediaPricingResult:
    del prompt, quality, aspect_ratio, reference_count
    loaded = load_pricing_rules(rules)
    rule = model_rule("image", model_id, loaded)
    if rule is None:
        raise ValueError(f"Image model pricing is not configured for {model_id}")

    output_count = max(int(output_count or 1), 1)
    max_output_count = int(rule.get("max_output_count", 0) or 0)
    if max_output_count > 0 and output_count > max_output_count:
        raise ValueError(f"Image output_count {output_count} exceeds max_output_count {max_output_count} for {model_id}")
    scheme = str(rule["scheme"])
    if scheme != "image_size_tier_pricing":
        raise ValueError(f"Unsupported image pricing scheme: {scheme}")
    resolved_tier = _resolve_image_billing_size_tier(
        rule,
        billing_size_tier=billing_size_tier,
        resolution=resolution,
        size=size,
    )
    unit_credits = _lookup_number(rule.get("price_by_size_tier"), resolved_tier, default=None)
    if unit_credits is None:
        raise ValueError(f"Image pricing does not include billing_size_tier {resolved_tier} for {model_id}")
    billing_units = unit_credits * output_count
    official_cost = _credits_to_official_cost(loaded, rule, billing_units)
    breakdown = {
        "scheme": scheme,
        "unit_credits": unit_credits,
        "billing_size_tier": resolved_tier.upper(),
        "output_count": output_count,
        "price_unit": "credits",
    }

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
    provider_usage: dict[str, Any] | None = None,
    rules: dict[str, Any] | None = None,
) -> MediaPricingResult:
    # Provider-reported cost is telemetry only and must not alter customer billing.
    _ = provider_usage
    loaded = load_pricing_rules(rules)
    rule = model_rule("video", model_id, loaded)
    if rule is None:
        raise ValueError(f"Video model pricing is not configured for {model_id}")

    output_count = max(int(output_count or 1), 1)
    resolved_duration = max(float(duration_seconds or rule.get("default_duration_seconds") or 1), 1.0)
    resolved_resolution = _normalize_key(resolution or rule.get("default_resolution") or "720p")
    resolved_mode = _normalize_key(mode or rule.get("default_mode") or "standard")
    scheme = str(rule["scheme"])

    if scheme == "video_seconds_pricing":
        per_second_map = (
            rule.get("cost_per_second_with_audio_by_resolution") or rule.get("usd_per_second_with_audio_by_resolution")
            if generate_audio and (isinstance(rule.get("cost_per_second_with_audio_by_resolution"), dict) or isinstance(rule.get("usd_per_second_with_audio_by_resolution"), dict))
            else rule.get("cost_per_second_by_resolution") or rule.get("usd_per_second_by_resolution")
        )
        unit_cost = _lookup_number(per_second_map, resolved_resolution, default=None)
        if unit_cost is None:
            raise ValueError(f"Video pricing does not include resolution {resolved_resolution} for {rule['model_id']}")
        mode_multiplier = _lookup_number(rule.get("mode_multipliers"), resolved_mode, default=1.0) or 1.0
        command_multiplier = _lookup_number(rule.get("command_multipliers"), _normalize_key(command or "generate"), default=1.0) or 1.0
        audio_multiplier = float(rule.get("audio_multiplier", 1.0) or 1.0) if generate_audio else 1.0
        official_cost = unit_cost * resolved_duration * output_count * mode_multiplier * command_multiplier * audio_multiplier
        breakdown = {
            "scheme": scheme,
            "cost_per_second": unit_cost,
            "duration_seconds": resolved_duration,
            "resolution": resolved_resolution,
            "mode": resolved_mode,
            "mode_multiplier": mode_multiplier,
            "command": _normalize_key(command or "generate"),
            "command_multiplier": command_multiplier,
            "audio_multiplier": audio_multiplier,
            "output_count": output_count,
        }
    elif scheme == "video_unit_pricing":
        unit_cost = _lookup_unit_cost(rule, resolved_mode, resolved_resolution)
        duration_factor = resolved_duration / max(float(rule.get("unit_duration_seconds", resolved_duration) or resolved_duration), 1.0)
        official_cost = unit_cost * duration_factor * output_count
        breakdown = {
            "scheme": scheme,
            "unit_cost": unit_cost,
            "unit_duration_seconds": float(rule.get("unit_duration_seconds", resolved_duration) or resolved_duration),
            "duration_seconds": resolved_duration,
            "resolution": resolved_resolution,
            "mode": resolved_mode,
            "output_count": output_count,
        }
    else:
        raise ValueError(f"Unsupported video pricing scheme: {scheme}")

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
    else:
        _validate_video_scheme(model_id, rule)
    return rule


def _validate_image_scheme(model_id: str, rule: dict[str, Any]) -> None:
    prices = rule.get("price_by_size_tier")
    if not isinstance(prices, dict) or not prices:
        raise ValueError(f"image.{model_id}.price_by_size_tier must be a non-empty object")
    normalized_prices: dict[str, float] = {}
    for tier, price in prices.items():
        normalized_tier = _normalize_billing_size_tier(tier)
        if normalized_tier not in {"1k", "2k", "4k"}:
            raise ValueError(f"image.{model_id}.price_by_size_tier contains unsupported tier {tier}")
        normalized_prices[normalized_tier] = _positive_float(price, f"image.{model_id}.price_by_size_tier.{normalized_tier}", allow_zero=False)
    rule["price_by_size_tier"] = normalized_prices
    default_tier = _resolve_configured_billing_size_tier(rule.get("default_billing_size_tier"))
    if default_tier not in normalized_prices:
        raise ValueError(f"image.{model_id}.default_billing_size_tier must exist in price_by_size_tier")
    rule["default_billing_size_tier"] = default_tier.upper()
    rule["max_output_count"] = int(_positive_float(rule.get("max_output_count", 1), f"image.{model_id}.max_output_count", allow_zero=False))
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
    elif rule["scheme"] == "video_unit_pricing":
        if not any(isinstance(rule.get(key), dict) and rule[key] for key in ("cost_by_quality_size", "cost_by_size")) and "unit_cost" not in rule:
            raise ValueError(f"video.{model_id} must define unit_cost, cost_by_size, or cost_by_quality_size")


def _pricing_result(loaded: dict[str, Any], rule: dict[str, Any], official_cost: float, breakdown: dict[str, Any]) -> MediaPricingResult:
    official_cost = round(max(float(official_cost or 0), 0.0), 8)
    currency = str(rule.get("currency") or "USD").upper()
    currency_rate = float(loaded.get("currency_rates", {}).get(currency, 0) or 0)
    credits_per_usd = float(loaded.get("credits_per_usd") or os.getenv("BILLING_CREDITS_PER_USD", DEFAULT_CREDITS_PER_USD) or DEFAULT_CREDITS_PER_USD)
    multiplier = float(rule.get("multiplier", 1) or 1)
    billing_units = official_cost * currency_rate * credits_per_usd * multiplier
    return MediaPricingResult(
        official_cost=official_cost,
        official_currency=currency,
        pricing_multiplier=multiplier,
        billing_units=float(Decimal(str(max(billing_units, 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        pricing_scheme=str(rule.get("scheme") or ""),
        pricing_basis=str(rule.get("pricing_basis") or "official_public"),
        pricing_source=str(rule.get("source_url") or ""),
        source_checked_at=str(rule.get("source_checked_at") or ""),
        pricing_breakdown={**breakdown, "currency_rate_to_usd": currency_rate, "credits_per_usd": credits_per_usd},
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
    return {"1k": 1, "2k": 2, "4k": 4}.get(_normalize_billing_size_tier(tier), 0)


def _billing_size_tier_from_value(rule: dict[str, Any], value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"auto", "adaptive", "default"}:
        return None
    alias_key = _normalize_alias_key(text)
    aliases = rule.get("tier_aliases")
    if isinstance(aliases, dict) and alias_key in aliases:
        return _normalize_billing_size_tier(aliases[alias_key])
    direct = _normalize_billing_size_tier(text)
    if direct in {"1k", "2k", "4k"}:
        return direct
    parsed = _parse_pixel_size(alias_key)
    if parsed:
        longest = max(parsed)
        if longest >= 3000:
            return "4k"
        if longest >= 2000:
            return "2k"
        return "1k"
    raise ValueError(f"Cannot determine image billing_size_tier from {value!r} for {rule['model_id']}")


def _resolve_configured_billing_size_tier(value: Any) -> str:
    tier = _normalize_billing_size_tier(value)
    if tier not in {"1k", "2k", "4k"}:
        raise ValueError(f"billing_size_tier must be one of 1K, 2K, or 4K")
    return tier


def _normalize_billing_size_tier(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "")
    if text in {"1", "1k"}:
        return "1k"
    if text in {"2", "2k"}:
        return "2k"
    if text in {"4", "4k"}:
        return "4k"
    return text


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
    value = mapping.get(normalized)
    if value is None:
        value = mapping.get(key)
    if value is None and normalized.endswith("p"):
        value = mapping.get(normalized[:-1])
    if value is None and not normalized.endswith("p") and normalized.isdigit():
        value = mapping.get(f"{normalized}p")
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
