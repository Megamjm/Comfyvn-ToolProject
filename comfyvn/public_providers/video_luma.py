from __future__ import annotations

"""
Luma Dream Machine adapter (dry-run).

Luma currently exposes API access primarily through partner programs.  This
module documents the cost heuristics and request shape while leaving execution
stubbed until credentials become broadly available.
"""

import logging
from typing import Any, Dict, Mapping

from comfyvn.public_providers import resolve_credential

LOGGER = logging.getLogger(__name__)

PROVIDER_ID = "luma"
FEATURE_FLAG = "enable_public_video_providers"
KIND = "video"
ALIASES: tuple[str, ...] = ("luma", "luma-ai", "dream-machine")
ENV_KEYS: tuple[str, ...] = ("LUMA_API_KEY",)
DEFAULT_DURATION = 6.0
DEFAULT_RESOLUTION = "1080p"
PLAN_PRICING = [
    {"name": "Lite", "monthly_usd": 9.99, "credits": 100, "notes": "web/iOS access"},
    {"name": "Pro", "monthly_usd": 29.99, "credits": 400, "notes": "priority queue"},
]
DEFAULT_CREDITS_PER_CLIP = 10
USD_PER_CREDIT = 0.08  # derived from Lite plan heuristics


def catalog_entry() -> Dict[str, Any]:
    return {
        "id": PROVIDER_ID,
        "label": "Luma Dream Machine",
        "kind": KIND,
        "feature_flag": FEATURE_FLAG,
        "default_mode": "video",
        "modes": [
            {"id": "video", "label": "Video Generation", "default": True},
        ],
        "docs_url": "https://lumalabs.ai/dream-machine",
        "pricing_url": "https://lumalabs.ai/pricing",
        "pricing": {
            "plans": PLAN_PRICING,
            "usd_per_credit": USD_PER_CREDIT,
            "notes": "API access generally routed via partners; studio instances often purchase credits in bulk.",
        },
        "tags": ["video", "dream-machine"],
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
    duration = float(data.get("duration_seconds") or DEFAULT_DURATION)
    parameters = _require_mapping(
        data.get("parameters") or {}, "parameters must be an object"
    )
    resolution = str(parameters.get("resolution") or DEFAULT_RESOLUTION)
    style = parameters.get("style") or parameters.get("model")

    payload: Dict[str, Any] = {
        "mode": "video",
        "prompt": prompt,
        "duration_seconds": max(duration, 3.0),
        "parameters": {
            "resolution": resolution,
        },
    }
    if style:
        payload["parameters"]["style"] = style
    reference = data.get("reference")
    if reference:
        payload["reference"] = reference
    return payload


def estimate_cost(payload: Mapping[str, Any]) -> Dict[str, Any]:
    credits = DEFAULT_CREDITS_PER_CLIP
    duration = float(payload.get("duration_seconds") or DEFAULT_DURATION)
    if duration > 8:
        credits += 4
    estimated_usd = credits * USD_PER_CREDIT
    return {
        "unit": "credit",
        "credits": credits,
        "estimated_cost_usd": round(estimated_usd, 2),
        "notes": "Assumes partner API uses Dream Machine credit pricing.",
    }


def generate(request: Mapping[str, Any], *, execute: bool) -> Dict[str, Any]:
    payload = prepare_request(request)
    estimates = estimate_cost(payload)
    api_key = resolve_credential(PROVIDER_ID, env_keys=ENV_KEYS)
    execution_allowed = bool(execute and api_key)
    warnings: list[str] = []

    if not api_key:
        warnings.append("missing API key or broker credential; dry-run enforced")
    if not execute:
        warnings.append("feature flag disabled or execution not permitted")
    if execution_allowed:
        warnings.append(
            "live execution path pending implementation; returning dry-run payload"
        )

    LOGGER.info(
        "public.video.luma.dry-run",
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
]
