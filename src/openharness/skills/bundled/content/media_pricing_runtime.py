"""Shared media generation pricing helpers."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Literal


PRICING_RULES_ENV = "OPENHARNESS_MEDIA_MODEL_PRICING_RULES"
DEFAULT_CREDITS_PER_USD = 25.0
SUPPORTED_IMAGE_SCHEMES = {"image_token_pricing", "image_unit_pricing"}
SUPPORTED_VIDEO_SCHEMES = {"video_seconds_pricing", "video_unit_pricing"}


DEFAULT_MEDIA_MODEL_PRICING_RULES: dict[str, Any] = {
    "currency_rates": {"USD": 1.0, "CNY": 0.14},
    "credits_per_usd": DEFAULT_CREDITS_PER_USD,
    "image": {
        "kolors": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_unit_pricing",
            "source_url": "https://huggingface.co/Kwai-Kolors/Kolors",
            "source_checked_at": "2026-07-05",
            "unit_cost": 0.02,
            "default_size": "1024x1024",
            "default_quality": "medium",
        },
        "gpt-image-2": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_token_pricing",
            "source_url": "https://openai.com/api/pricing/",
            "source_checked_at": "2026-07-05",
            "input_text_per_1m": 5.0,
            "input_image_per_1m": 10.0,
            "output_image_per_1m": 40.0,
            "default_input_image_tokens": 1290,
            "default_size": "1024x1024",
            "default_quality": "medium",
            "output_tokens_by_quality_size": {
                "low": {"1024x1024": 272, "1536x1024": 408, "1024x1536": 400, "1792x1024": 488, "1024x1792": 488},
                "medium": {"1024x1024": 1056, "1536x1024": 1584, "1024x1536": 1568, "1792x1024": 1936, "1024x1792": 1936},
                "high": {"1024x1024": 4160, "1536x1024": 6240, "1024x1536": 6208, "1792x1024": 7744, "1024x1792": 7744},
            },
        },
        "nano-banana": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_unit_pricing",
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "source_checked_at": "2026-07-05",
            "unit_cost": 0.039,
            "default_size": "1024x1024",
            "default_quality": "medium",
        },
        "nano-banana-2": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_unit_pricing",
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "source_checked_at": "2026-07-05",
            "unit_cost": 0.039,
            "default_size": "1024x1024",
            "default_quality": "medium",
        },
        "nano-banana-pro": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "image_unit_pricing",
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "source_checked_at": "2026-07-05",
            "cost_by_quality_size": {
                "medium": {"1024x1024": 0.134, "2048x2048": 0.134},
                "high": {"1024x1024": 0.24, "2048x2048": 0.24},
            },
            "unit_cost": 0.134,
            "default_size": "1024x1024",
            "default_quality": "medium",
        },
        "doubao-seedream-5-0-260128": {
            "enabled": True,
            "currency": "CNY",
            "multiplier": 1.0,
            "scheme": "image_unit_pricing",
            "source_url": "https://www.volcengine.com/docs",
            "source_checked_at": "2026-07-05",
            "cost_by_size": {"2048x2048": 0.2, "2848x1600": 0.2, "1600x2848": 0.2},
            "unit_cost": 0.2,
            "default_size": "2048x2048",
            "default_quality": "medium",
        },
        "doubao-seedream-5-0-lite-260128": {
            "enabled": True,
            "currency": "CNY",
            "multiplier": 1.0,
            "scheme": "image_unit_pricing",
            "source_url": "https://www.volcengine.com/docs",
            "source_checked_at": "2026-07-05",
            "unit_cost": 0.1,
            "default_size": "2048x2048",
            "default_quality": "medium",
        },
        "doubao-seedream-4-5-251128": {
            "enabled": True,
            "currency": "CNY",
            "multiplier": 1.0,
            "scheme": "image_unit_pricing",
            "source_url": "https://www.volcengine.com/docs",
            "source_checked_at": "2026-07-05",
            "unit_cost": 0.2,
            "default_size": "2048x2048",
            "default_quality": "medium",
        },
        "doubao-seedream-4-0-250828": {
            "enabled": True,
            "currency": "CNY",
            "multiplier": 1.0,
            "scheme": "image_unit_pricing",
            "source_url": "https://www.volcengine.com/docs",
            "source_checked_at": "2026-07-05",
            "unit_cost": 0.2,
            "default_size": "2048x2048",
            "default_quality": "medium",
        },
    },
    "video": {
        "doubao-seedance-2-0-260128": {
            "enabled": True,
            "currency": "CNY",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "source_url": "https://www.volcengine.com/docs",
            "source_checked_at": "2026-07-05",
            "cost_per_second_by_resolution": {"720p": 0.32, "1080p": 0.52, "4k": 1.28},
            "default_duration_seconds": 5,
            "default_resolution": "1080p",
            "default_mode": "standard",
        },
        "doubao-seedance-2-0-fast-260128": {
            "enabled": True,
            "currency": "CNY",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "source_url": "https://www.volcengine.com/docs",
            "source_checked_at": "2026-07-05",
            "cost_per_second_by_resolution": {"720p": 0.2, "1080p": 0.32},
            "default_duration_seconds": 5,
            "default_resolution": "720p",
            "default_mode": "fast",
        },
        "seedance-1.5-pro": {
            "enabled": True,
            "currency": "CNY",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "source_url": "https://www.volcengine.com/docs",
            "source_checked_at": "2026-07-05",
            "cost_per_second_by_resolution": {"720p": 0.38, "1080p": 0.6, "4k": 1.5},
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
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "source_checked_at": "2026-07-05",
            "cost_per_second_by_resolution": {"720p": 0.4, "1080p": 0.4, "4k": 0.6},
            "default_duration_seconds": 5,
            "default_resolution": "1080p",
            "default_mode": "standard",
        },
        "veo-3.1-fast": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "source_checked_at": "2026-07-05",
            "cost_per_second_by_resolution": {"720p": 0.1, "1080p": 0.12, "4k": 0.3},
            "default_duration_seconds": 5,
            "default_resolution": "720p",
            "default_mode": "fast",
        },
        "veo-3.1-lite": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
            "source_checked_at": "2026-07-05",
            "cost_per_second_by_resolution": {"720p": 0.05, "1080p": 0.08},
            "default_duration_seconds": 5,
            "default_resolution": "720p",
            "default_mode": "lite",
        },
        "kling-3.0": {
            "enabled": True,
            "currency": "USD",
            "multiplier": 1.0,
            "scheme": "video_seconds_pricing",
            "source_url": "https://klingai.com/document-api/pricing/base/video",
            "source_checked_at": "2026-07-05",
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
            "source_url": "https://klingai.com/document-api/pricing/base/video",
            "source_checked_at": "2026-07-05",
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
            "source_url": "https://klingai.com/document-api/pricing/base/video",
            "source_checked_at": "2026-07-05",
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
    size: str | None = None,
    quality: str | None = None,
    aspect_ratio: str | None = None,
    output_count: int = 1,
    reference_count: int = 0,
    rules: dict[str, Any] | None = None,
) -> MediaPricingResult:
    loaded = load_pricing_rules(rules)
    rule = model_rule("image", model_id, loaded)
    if rule is None:
        raise ValueError(f"Image model pricing is not configured for {model_id}")

    output_count = max(int(output_count or 1), 1)
    reference_count = max(int(reference_count or 0), 0)
    resolved_quality = _normalize_key(quality or rule.get("default_quality") or "medium")
    resolved_size = _normalize_size(size, aspect_ratio, rule.get("default_size") or "1024x1024")
    scheme = str(rule["scheme"])

    if scheme == "image_token_pricing":
        text_tokens = _estimate_text_tokens(prompt)
        output_tokens = _lookup_image_output_tokens(rule, resolved_quality, resolved_size)
        input_image_tokens = reference_count * _lookup_number(
            rule.get("input_image_tokens_by_size"),
            resolved_size,
            default=float(rule.get("default_input_image_tokens", 0) or 0),
        )
        official_cost = (
            text_tokens * float(rule.get("input_text_per_1m", 0)) / 1_000_000
            + input_image_tokens * float(rule.get("input_image_per_1m", 0)) / 1_000_000
            + output_tokens * output_count * float(rule.get("output_image_per_1m", 0)) / 1_000_000
        )
        breakdown = {
            "scheme": scheme,
            "text_tokens": text_tokens,
            "input_image_tokens": input_image_tokens,
            "output_image_tokens": output_tokens,
            "output_count": output_count,
            "size": resolved_size,
            "quality": resolved_quality,
        }
    elif scheme == "image_unit_pricing":
        unit_cost = _lookup_unit_cost(rule, resolved_quality, resolved_size)
        official_cost = unit_cost * output_count
        breakdown = {
            "scheme": scheme,
            "unit_cost": unit_cost,
            "output_count": output_count,
            "size": resolved_size,
            "quality": resolved_quality,
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
    provider_usage: dict[str, Any] | None = None,
    rules: dict[str, Any] | None = None,
) -> MediaPricingResult:
    loaded = load_pricing_rules(rules)
    rule = model_rule("video", model_id, loaded)
    if rule is None:
        raise ValueError(f"Video model pricing is not configured for {model_id}")

    output_count = max(int(output_count or 1), 1)
    resolved_duration = max(float(duration_seconds or rule.get("default_duration_seconds") or 1), 1.0)
    resolved_resolution = _normalize_key(resolution or rule.get("default_resolution") or "720p")
    resolved_mode = _normalize_key(mode or rule.get("default_mode") or "standard")
    provider_cost = _provider_usage_cost(provider_usage)
    scheme = str(rule["scheme"])

    if provider_cost is not None:
        official_cost, cost_currency, usage_breakdown = provider_cost
        working_rule = {**rule, "currency": cost_currency}
        return _pricing_result(load_pricing_rules({**loaded, "video": {**loaded.get("video", {}), rule["model_id"]: working_rule}}), working_rule, official_cost, usage_breakdown)

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
    if kind == "image":
        _validate_image_scheme(model_id, rule)
    else:
        _validate_video_scheme(model_id, rule)
    return rule


def _validate_image_scheme(model_id: str, rule: dict[str, Any]) -> None:
    if rule["scheme"] == "image_token_pricing":
        for key in ("input_text_per_1m", "input_image_per_1m", "output_image_per_1m"):
            _positive_float(rule.get(key, 0), f"image.{model_id}.{key}", allow_zero=True)
        tokens = rule.get("output_tokens_by_quality_size")
        if not isinstance(tokens, dict) or not tokens:
            raise ValueError(f"image.{model_id}.output_tokens_by_quality_size must be a non-empty object")
    elif rule["scheme"] == "image_unit_pricing":
        if not any(isinstance(rule.get(key), dict) and rule[key] for key in ("cost_by_quality_size", "cost_by_size")) and "unit_cost" not in rule:
            raise ValueError(f"image.{model_id} must define unit_cost, cost_by_size, or cost_by_quality_size")


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
        billing_units=round(max(billing_units, 0.0), 2),
        pricing_scheme=str(rule.get("scheme") or ""),
        pricing_source=str(rule.get("source_url") or ""),
        source_checked_at=str(rule.get("source_checked_at") or ""),
        pricing_breakdown={**breakdown, "currency_rate_to_usd": currency_rate, "credits_per_usd": credits_per_usd},
    )


def _provider_usage_cost(provider_usage: dict[str, Any] | None) -> tuple[float, str, dict[str, Any]] | None:
    if not isinstance(provider_usage, dict):
        return None
    currency = str(provider_usage.get("currency") or provider_usage.get("official_currency") or "USD").strip().upper()
    for key in ("official_cost", "cost", "total_cost", "amount", "usd", "resource_units", "credits", "points", "usage_units", "billing_units"):
        value = provider_usage.get(key)
        if value is None:
            continue
        try:
            cost = max(float(value), 0.0)
        except (TypeError, ValueError):
            continue
        return cost, currency, {"scheme": "provider_usage", "provider_usage_key": key, "provider_usage": provider_usage}
    return None


def _estimate_text_tokens(prompt: str) -> int:
    return max(int(math.ceil(len(prompt or "") / 4)), 0)


def _lookup_image_output_tokens(rule: dict[str, Any], quality: str, size: str) -> float:
    tokens = rule.get("output_tokens_by_quality_size")
    value = _lookup_nested_number(tokens, quality, size)
    if value is not None:
        return value
    value = _lookup_number(rule.get("output_tokens_by_size"), size, default=None)
    if value is not None:
        return value
    return float(rule.get("default_output_image_tokens", 0) or 0)


def _lookup_unit_cost(rule: dict[str, Any], quality_or_mode: str, size_or_resolution: str) -> float:
    value = _lookup_nested_number(rule.get("cost_by_quality_size"), quality_or_mode, size_or_resolution)
    if value is not None:
        return value
    value = _lookup_number(rule.get("cost_by_size"), size_or_resolution, default=None)
    if value is not None:
        return value
    return float(rule.get("unit_cost", 0) or 0)


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


def _normalize_size(size: str | None, aspect_ratio: str | None, default_size: str) -> str:
    raw = str(size or "").strip().lower()
    if raw and raw != "auto":
        return raw
    aspect = str(aspect_ratio or "").strip()
    if aspect == "16:9":
        return "1792x1024"
    if aspect == "9:16":
        return "1024x1792"
    return str(default_size or "1024x1024").strip().lower()


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
