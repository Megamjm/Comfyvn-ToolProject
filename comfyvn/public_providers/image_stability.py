from __future__ import annotations

"""
Stability Image API adapter (dry-run focused).

We surface catalog metadata, payload coercion helpers, and cost estimates so
Studio tooling can reason about Stability endpoints without making live calls.
Actual network execution remains TODO until credentials and compliance gates
are cleared.
"""

import logging
from typing import Any, Dict, Iterable, Mapping, Optional

from comfyvn.public_providers import resolve_credential

LOGGER = logging.getLogger(__name__)

PROVIDER_ID = "stability"
FEATURE_FLAG = "enable_public_image_providers"
KIND = "image"
ALIASES: tuple[str, ...] = (
    "stability",
    "stability_ai",
    "stabilityai",
    "stable",
    "stability-image",
)
ENV_KEYS: tuple[str, ...] = ("STABILITY_API_KEY",)
DEFAULT_MODE = "text-to-image"
SUPPORTED_MODES: Dict[str, str] = {
    "text-to-image": "Stable Image API (txt2img)",
    "image-to-image": "Stable Image API (img2img)",
}
UNIT_COST_USD = 0.04  # pay-as-you-go estimate per generated image (SDXL/SD3 tier)
LAST_CHECKED = "2025-02-17"
CAPABILITIES: Dict[str, Any] = {
    "modes": list(SUPPORTED_MODES.keys()),
    "features": [
        "negative_prompt",
        "image_to_image",
        "safety_settings",
        "style_presets",
    ],
    "max_resolution": "2048x2048",
}


def catalog_entry() -> Dict[str, Any]:
    return {
        "id": PROVIDER_ID,
        "label": "Stability Image API",
        "kind": KIND,
        "feature_flag": FEATURE_FLAG,
        "default_mode": DEFAULT_MODE,
        "modes": [
            {"id": key, "label": label, "default": key == DEFAULT_MODE}
            for key, label in SUPPORTED_MODES.items()
        ],
        "docs_url": "https://platform.stability.ai/docs",
        "pricing_url": "https://platform.stability.ai/pricing",
        "pricing": {
            "unit_cost_usd": UNIT_COST_USD,
            "unit": "image",
            "plan": "pay-as-you-go",
            "notes": "Costs vary by model; SD3 and Core share the same unit cost as of 2025-11.",
        },
        "tags": ["stable-diffusion", "sdxl", "sd3"],
    }


def metadata() -> Dict[str, Any]:
    entry = catalog_entry()
    return {
        "id": PROVIDER_ID,
        "name": entry.get("label"),
        "pricing_url": entry.get("pricing_url"),
        "docs_url": entry.get("docs_url"),
        "last_checked": LAST_CHECKED,
        "capabilities": CAPABILITIES,
        "feature_flag": FEATURE_FLAG,
        "env_keys": list(ENV_KEYS),
        "aliases": list(ALIASES),
    }


def credentials_present() -> bool:
    return bool(resolve_credential(PROVIDER_ID, env_keys=ENV_KEYS))


def _require_mapping(payload: Any, detail: str) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    raise ValueError(detail)


def _coerce_parameters(params: Mapping[str, Any] | None) -> Dict[str, Any]:
    coerced: Dict[str, Any] = {}
    if not params:
        return coerced
    for key, value in params.items():
        if isinstance(key, str):
            coerced[key] = value
    return coerced


def prepare_request(request: Mapping[str, Any]) -> Dict[str, Any]:
    data = _require_mapping(request, "request payload must be an object")
    mode = str(data.get("mode") or data.get("operation") or DEFAULT_MODE).lower()
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"unsupported mode '{mode}'")
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    negative_prompt = str(data.get("negative_prompt") or "").strip() or None
    parameters = _coerce_parameters(
        _require_mapping(
            data.get("parameters") or {},
            "parameters must be an object",
        )
    )
    samples = int(parameters.get("samples") or parameters.get("images") or 1)
    parameters["samples"] = max(samples, 1)

    payload: Dict[str, Any] = {
        "mode": mode,
        "prompt": prompt,
        "parameters": parameters,
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt

    init_image = data.get("init_image") or data.get("image")
    if init_image and mode == "image-to-image":
        payload["init_image"] = init_image

    style_preset = data.get("style_preset")
    if isinstance(style_preset, str) and style_preset.strip():
        payload["style_preset"] = style_preset.strip()

    safety = data.get("safety")
    if isinstance(safety, Mapping):
        payload["safety"] = dict(safety)

    return payload


def _api_key(config: Optional[Mapping[str, Any]] = None) -> str:
    token = resolve_credential(
        PROVIDER_ID,
        env_keys=ENV_KEYS,
        secret_keys=("api_key", "token"),
    )
    if token:
        return token.strip()
    if config:
        raw = config.get("api_key") or config.get("token")
        if isinstance(raw, str):
            return raw.strip()
    return ""


def _with_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    meta = metadata()
    data = dict(payload)
    data.setdefault("provider", meta["id"])
    data.setdefault("pricing_url", meta["pricing_url"])
    data.setdefault("docs_url", meta["docs_url"])
    data.setdefault("last_checked", meta["last_checked"])
    data.setdefault("capabilities", meta["capabilities"])
    data.setdefault("dry_run", True)
    return data


def estimate_cost(payload: Mapping[str, Any]) -> Dict[str, Any]:
    parameters = _require_mapping(payload.get("parameters") or {}, "parameters missing")
    samples = int(parameters.get("samples") or 1)
    cost = UNIT_COST_USD * max(samples, 1)
    return {
        "unit": "image",
        "count": max(samples, 1),
        "unit_cost_usd": UNIT_COST_USD,
        "estimated_cost_usd": round(cost, 4),
    }


def health(config: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    api_key = _api_key(config)
    if not api_key:
        return _with_metadata(
            {"ok": False, "reason": "missing api key", "dry_run": True}
        )
    return _with_metadata({"ok": True, "credential": "present"})


def generate(
    request: Mapping[str, Any],
    *,
    execute: bool,
    config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = prepare_request(request)
    estimates = estimate_cost(payload)
    api_key = _api_key(config)
    execution_allowed = bool(execute and api_key)
    warnings: list[str] = []

    if not api_key:
        warnings.append("missing api key; forcing dry-run")
    if not execute:
        warnings.append("feature flag disabled or execution not permitted")
    if execution_allowed:
        warnings.append(
            "live execution path not implemented; returning dry-run payload"
        )

    LOGGER.info(
        "public.image.stability.dry-run",
        extra={
            "mode": payload["mode"],
            "payload": {k: v for k, v in payload.items() if k != "prompt"},
            "estimates": estimates,
            "has_key": bool(api_key),
        },
    )

    return _with_metadata(
        {
            "provider": PROVIDER_ID,
            "kind": KIND,
            "mode": payload["mode"],
            "dry_run": True,
            "payload": payload,
            "estimates": estimates,
            "execution_allowed": execution_allowed,
            "warnings": warnings,
        }
    )


def submit(
    request: Mapping[str, Any],
    *,
    execute: bool,
    config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    result = generate(request, execute=execute, config=config)
    ok = bool(result.get("execution_allowed"))
    if ok:
        result.setdefault("id", "mock-stability-1")
    else:
        result.setdefault("id", "mock-stability-1")
        reason = result.get("warnings", [])
        if reason:
            result.setdefault("reason", reason[0])
    result.setdefault("ok", ok)
    result["dry_run"] = True
    return _with_metadata(result)


def poll(job_id: str, config: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    _ = _api_key(config)  # ensures consistent merge even if unused
    return _with_metadata(
        {
            "ok": True,
            "status": "done",
            "job_id": job_id or "mock-stability-1",
            "artifacts": [],
        }
    )


__all__ = [
    "ALIASES",
    "FEATURE_FLAG",
    "KIND",
    "LAST_CHECKED",
    "CAPABILITIES",
    "catalog_entry",
    "credentials_present",
    "estimate_cost",
    "health",
    "metadata",
    "poll",
    "generate",
    "prepare_request",
    "submit",
]
