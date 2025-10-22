from __future__ import annotations

"""
Pika Labs API adapter (dry-run).

Focuses on per-second billing heuristics so Studio tooling can preview cost
without invoking the real API.  Execution paths remain TODO.
"""

import logging
from typing import Any, Dict, Mapping

from comfyvn.public_providers import resolve_credential

LOGGER = logging.getLogger(__name__)

PROVIDER_ID = "pika"
FEATURE_FLAG = "enable_public_video_providers"
KIND = "video"
ALIASES: tuple[str, ...] = ("pika", "pika-labs")
ENV_KEYS: tuple[str, ...] = ("PIKA_API_KEY",)
DEFAULT_DURATION = 6.0
DEFAULT_RESOLUTION = "720p"
RATE_USD_PER_SECOND = {
    "720p": 0.05,
    "1080p": 0.07,
}
MAX_DURATION_SECONDS = 16.0


def catalog_entry() -> Dict[str, Any]:
    return {
        "id": PROVIDER_ID,
        "label": "Pika Labs",
        "kind": KIND,
        "feature_flag": FEATURE_FLAG,
        "default_mode": "video",
        "modes": [
            {"id": "video", "label": "Video Generation", "default": True},
        ],
        "docs_url": "https://docs.pika.art/",
        "pricing_url": "https://pika.art/pricing",
        "pricing": {
            "usd_per_second": RATE_USD_PER_SECOND,
            "notes": "Usage-based billing; subscription tiers provide monthly credit buckets.",
        },
        "tags": ["video", "pika"],
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
    duration = min(max(duration, 1.0), MAX_DURATION_SECONDS)
    parameters = _require_mapping(
        data.get("parameters") or {}, "parameters must be an object"
    )
    resolution = str(parameters.get("resolution") or DEFAULT_RESOLUTION).lower()
    if resolution not in RATE_USD_PER_SECOND:
        resolution = DEFAULT_RESOLUTION
    fps = int(parameters.get("fps") or 24)

    payload: Dict[str, Any] = {
        "mode": "video",
        "prompt": prompt,
        "duration_seconds": duration,
        "parameters": {
            "resolution": resolution,
            "fps": fps,
        },
    }
    style = parameters.get("style")
    if isinstance(style, str) and style.strip():
        payload["parameters"]["style"] = style.strip()
    return payload


def estimate_cost(payload: Mapping[str, Any]) -> Dict[str, Any]:
    duration = float(payload.get("duration_seconds") or DEFAULT_DURATION)
    resolution = str(
        payload.get("parameters", {}).get("resolution") or DEFAULT_RESOLUTION
    )
    rate = RATE_USD_PER_SECOND.get(resolution, RATE_USD_PER_SECOND[DEFAULT_RESOLUTION])
    cost = duration * rate
    return {
        "unit": "second",
        "duration_seconds": round(duration, 2),
        "rate_usd_per_second": rate,
        "estimated_cost_usd": round(cost, 2),
    }


def generate(request: Mapping[str, Any], *, execute: bool) -> Dict[str, Any]:
    payload = prepare_request(request)
    estimates = estimate_cost(payload)
    api_key = resolve_credential(PROVIDER_ID, env_keys=ENV_KEYS)
    execution_allowed = bool(execute and api_key)
    warnings: list[str] = []

    if not api_key:
        warnings.append("missing API key; dry-run enforced")
    if not execute:
        warnings.append("feature flag disabled or execution not permitted")
    if execution_allowed:
        warnings.append(
            "live execution path pending implementation; returning dry-run payload"
        )

    LOGGER.info(
        "public.video.pika.dry-run",
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
