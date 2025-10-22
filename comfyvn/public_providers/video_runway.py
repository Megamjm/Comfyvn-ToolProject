from __future__ import annotations

"""
Runway API adapter (dry-run).

Provides catalog metadata, cost estimation heuristics, and payload coercion so
Studio tooling can inspect request shapes.  Live execution remains TODO until
API access is approved.
"""

import logging
from typing import Any, Dict, Mapping

from comfyvn.public_providers import resolve_credential

LOGGER = logging.getLogger(__name__)

PROVIDER_ID = "runway"
FEATURE_FLAG = "enable_public_video_providers"
KIND = "video"
ALIASES: tuple[str, ...] = ("runway", "runwayml")
ENV_KEYS: tuple[str, ...] = ("RUNWAY_API_KEY", "RUNWAY_TOKEN")
DEFAULT_DURATION = 8.0
DEFAULT_RESOLUTION = "720p"
USD_PER_CREDIT = 0.01
CREDITS_PER_SECOND: Dict[str, float] = {
    "720p": 12.0,
    "1080p": 18.0,
}


def price_info() -> Dict[str, object]:
    info = catalog_entry()
    pricing = dict(info.get("pricing") or {})
    pricing.update({"last_checked": "2025-11", "dry_run": True})
    return pricing


def catalog_entry() -> Dict[str, Any]:
    return {
        "id": PROVIDER_ID,
        "label": "Runway Gen-3",
        "kind": KIND,
        "feature_flag": FEATURE_FLAG,
        "default_mode": "video",
        "modes": [
            {"id": "video", "label": "Video Generation", "default": True},
        ],
        "docs_url": "https://docs.runwayml.com/reference/api-overview",
        "pricing_url": "https://runwayml.com/pricing",
        "pricing": {
            "usd_per_credit": USD_PER_CREDIT,
            "credits_per_second": CREDITS_PER_SECOND,
            "notes": "Credits burn faster with higher resolutions and quality settings.",
        },
        "tags": ["gen-3", "video"],
    }


def credentials_present() -> bool:
    return bool(resolve_credential(PROVIDER_ID, env_keys=ENV_KEYS))


def _require_mapping(payload: Any, detail: str) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    raise ValueError(detail)


def prepare_request(request: Mapping[str, Any]) -> Dict[str, Any]:
    data = _require_mapping(request, "request payload must be an object")
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    duration = float(
        data.get("duration_seconds") or data.get("duration") or DEFAULT_DURATION
    )
    aspect = str(data.get("aspect_ratio") or "16:9")
    parameters = _require_mapping(
        data.get("parameters") or {}, "parameters must be an object"
    )
    resolution = str(parameters.get("resolution") or DEFAULT_RESOLUTION).lower()
    if resolution not in CREDITS_PER_SECOND:
        resolution = DEFAULT_RESOLUTION
    storyboard = data.get("storyboard") or data.get("reference_frames")

    payload: Dict[str, Any] = {
        "mode": "video",
        "prompt": prompt,
        "duration_seconds": max(duration, 1.0),
        "aspect_ratio": aspect,
        "parameters": {"resolution": resolution},
    }
    if storyboard:
        payload["storyboard"] = storyboard
    quality = parameters.get("quality")
    if quality:
        payload["parameters"]["quality"] = quality
    return payload


def estimate_cost(payload: Mapping[str, Any]) -> Dict[str, Any]:
    duration = float(payload.get("duration_seconds") or DEFAULT_DURATION)
    resolution = str(
        payload.get("parameters", {}).get("resolution") or DEFAULT_RESOLUTION
    )
    credits_per_second = CREDITS_PER_SECOND.get(
        resolution, CREDITS_PER_SECOND[DEFAULT_RESOLUTION]
    )
    credits = duration * credits_per_second
    cost_usd = credits * USD_PER_CREDIT
    return {
        "unit": "second",
        "duration_seconds": round(duration, 2),
        "credits": round(credits, 2),
        "credits_per_second": credits_per_second,
        "estimated_cost_usd": round(cost_usd, 2),
    }


def generate(request: Mapping[str, Any], *, execute: bool) -> Dict[str, Any]:
    payload = prepare_request(request)
    estimates = estimate_cost(payload)
    api_key = resolve_credential(PROVIDER_ID, env_keys=ENV_KEYS)
    execution_allowed = bool(execute and api_key)
    warnings: list[str] = []

    if not api_key:
        warnings.append("missing API key; forcing dry-run")
    if not execute:
        warnings.append("feature flag disabled or execution not permitted")
    if execution_allowed:
        warnings.append(
            "live execution path pending implementation; returning dry-run payload"
        )

    LOGGER.info(
        "public.video.runway.dry-run",
        extra={
            "duration": payload["duration_seconds"],
            "resolution": payload["parameters"]["resolution"],
            "estimates": estimates,
            "has_key": bool(api_key),
        },
    )

    return {
        "provider": PROVIDER_ID,
        "kind": KIND,
        "mode": payload["mode"],
        "dry_run": True,
        "payload": payload,
        "estimates": estimates,
        "execution_allowed": execution_allowed,
        "warnings": warnings,
    }


__all__ = [
    "ALIASES",
    "FEATURE_FLAG",
    "KIND",
    "catalog_entry",
    "credentials_present",
    "estimate_cost",
    "generate",
    "prepare_request",
    "price_info",
]
