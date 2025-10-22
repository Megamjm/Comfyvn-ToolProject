from __future__ import annotations

"""
fal.ai public image adapter (Flux & SDXL catalog + dry-run estimators).

fal.ai exposes multiple latency tiers; here we model heuristic costs so Studio
can present rough estimates without requiring live credentials.  Execution is
stubbed until feature flags and API keys are supplied.
"""

import logging
from typing import Any, Dict, Mapping

from comfyvn.public_providers import resolve_credential

LOGGER = logging.getLogger(__name__)

PROVIDER_ID = "fal.ai"
FEATURE_FLAG = "enable_public_image_providers"
KIND = "image"
ALIASES: tuple[str, ...] = (
    "fal",
    "fal.ai",
    "flux",
    "sdxl-fal",
)
ENV_KEYS: tuple[str, ...] = ("FAL_KEY", "FAL_API_KEY")
DEFAULT_MODE = "flux"
SUPPORTED_MODES: Dict[str, str] = {
    "flux": "Flux Schnell / Flux Pro (txt2img)",
    "sdxl": "Stable Diffusion XL (txt2img)",
}
GPU_PRICING_USD_PER_HOUR: Dict[str, float] = {
    "A100": 1.09,
    "H100": 1.89,
}
DEFAULT_GPU = "H100"


def catalog_entry() -> Dict[str, Any]:
    return {
        "id": PROVIDER_ID,
        "label": "fal.ai",
        "kind": KIND,
        "feature_flag": FEATURE_FLAG,
        "default_mode": DEFAULT_MODE,
        "modes": [
            {"id": key, "label": label, "default": key == DEFAULT_MODE}
            for key, label in SUPPORTED_MODES.items()
        ],
        "docs_url": "https://docs.fal.ai/",
        "pricing_url": "https://fal.ai/pricing",
        "pricing": {
            "gpu_hourly_usd": GPU_PRICING_USD_PER_HOUR,
            "notes": "Latency tiers depend on GPU allocation; Flux Schnell typically runs on H100.",
        },
        "tags": ["flux", "sdxl", "gpu"],
    }


def credentials_present() -> bool:
    return bool(
        resolve_credential("fal", env_keys=ENV_KEYS, secret_keys=("api_key", "key"))
    )


def _require_mapping(payload: Any, detail: str) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    raise ValueError(detail)


def prepare_request(request: Mapping[str, Any]) -> Dict[str, Any]:
    data = _require_mapping(request, "request payload must be an object")
    mode = str(data.get("mode") or DEFAULT_MODE).lower()
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"unsupported mode '{mode}'")
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    parameters = _require_mapping(
        data.get("parameters") or {},
        "parameters must be an object",
    )
    cfg_scale = float(
        parameters.get("guidance_scale") or parameters.get("cfg_scale") or 7.5
    )
    steps = int(parameters.get("steps") or parameters.get("num_inference_steps") or 30)
    resolution = str(parameters.get("resolution") or "1024x1024")

    payload: Dict[str, Any] = {
        "mode": mode,
        "prompt": prompt,
        "parameters": {
            "guidance_scale": cfg_scale,
            "steps": max(steps, 1),
            "resolution": resolution,
        },
    }

    seed = parameters.get("seed")
    if isinstance(seed, int):
        payload["parameters"]["seed"] = seed

    return payload


def _gpu_minutes_for(payload: Mapping[str, Any]) -> float:
    mode = str(payload.get("mode") or DEFAULT_MODE).lower()
    params = _require_mapping(payload.get("parameters") or {}, "parameters missing")
    steps = float(params.get("steps") or 30)
    resolution = str(params.get("resolution") or "1024x1024")

    base_minutes = 1.5 if mode == "flux" else 1.0
    if "1536" in resolution or "2048" in resolution:
        base_minutes *= 1.5
    if steps > 40:
        base_minutes *= steps / 40.0
    return max(base_minutes, 0.5)


def estimate_cost(payload: Mapping[str, Any]) -> Dict[str, Any]:
    gpu_minutes = _gpu_minutes_for(payload)
    gpu_type = str(payload.get("parameters", {}).get("gpu") or DEFAULT_GPU)
    hourly_cost = GPU_PRICING_USD_PER_HOUR.get(
        gpu_type, GPU_PRICING_USD_PER_HOUR[DEFAULT_GPU]
    )
    cost = hourly_cost * (gpu_minutes / 60.0)
    return {
        "unit": "gpu_minute",
        "gpu_type": gpu_type,
        "minutes": round(gpu_minutes, 2),
        "hourly_rate_usd": hourly_cost,
        "estimated_cost_usd": round(cost, 4),
    }


def generate(request: Mapping[str, Any], *, execute: bool) -> Dict[str, Any]:
    payload = prepare_request(request)
    estimates = estimate_cost(payload)
    api_key = resolve_credential(
        "fal", env_keys=ENV_KEYS, secret_keys=("api_key", "key")
    )
    execution_allowed = bool(execute and api_key)
    warnings: list[str] = []

    if not api_key:
        warnings.append("missing API key; responses are dry-run only")
    if not execute:
        warnings.append("feature flag disabled or execution not permitted")
    if execution_allowed:
        warnings.append(
            "live execution path pending implementation; returning dry-run payload"
        )

    LOGGER.info(
        "public.image.fal.dry-run",
        extra={
            "mode": payload["mode"],
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
