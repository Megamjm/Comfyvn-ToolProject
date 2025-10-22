from __future__ import annotations

"""
Public GPU provider metadata + dry-run helpers.
"""

from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

from fastapi import APIRouter, Body, HTTPException

from comfyvn.config import feature_flags
from comfyvn.public_providers import (
    catalog,
    gpu_hf_endpoints,
    gpu_modal,
    gpu_replicate,
    gpu_runpod,
)

router = APIRouter(prefix="/api/providers/gpu/public", tags=["GPU Providers (public)"])

DEFAULT_FEATURE_FLAG = "enable_public_gpu"
GPU_MODULES: Sequence[object] = (
    gpu_runpod,
    gpu_hf_endpoints,
    gpu_replicate,
    gpu_modal,
)


def _feature_context(module: object | None = None) -> Dict[str, Any]:
    flag_name = getattr(module, "FEATURE_FLAG", DEFAULT_FEATURE_FLAG)
    enabled = feature_flags.is_enabled(flag_name)
    return {"feature": flag_name, "enabled": enabled}


def _aliases_for(module: object) -> Iterable[str]:
    aliases = getattr(module, "ALIASES", None)
    if aliases:
        return tuple(str(alias).lower() for alias in aliases)
    ident = getattr(module, "PROVIDER_ID", None)
    if ident:
        return (str(ident).lower(),)
    try:
        meta = module.metadata()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        return ()
    provider_id = meta.get("id")
    if provider_id:
        return (str(provider_id).lower(),)
    return ()


def _build_module_map(modules: Sequence[object]) -> Dict[str, object]:
    mapping: Dict[str, object] = {}
    for module in modules:
        for alias in _aliases_for(module):
            if alias:
                mapping[alias] = module
    return mapping


GPU_PROVIDER_MAP = _build_module_map(GPU_MODULES)


def _metadata(module: object) -> Dict[str, Any]:
    try:
        meta = dict(module.metadata())  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail="provider metadata unavailable"
        ) from exc
    return meta


def _enrich_result(module: object, payload: Mapping[str, Any]) -> Dict[str, Any]:
    meta = _metadata(module)
    result = dict(payload)
    result.setdefault("provider", meta.get("id"))
    result.setdefault("pricing_url", meta.get("pricing_url"))
    result.setdefault("docs_url", meta.get("docs_url"))
    result.setdefault("last_checked", meta.get("last_checked"))
    result.setdefault("capabilities", meta.get("capabilities"))
    result.setdefault("dry_run", True)

    feature = _feature_context(module)
    result["feature"] = feature
    if not feature["enabled"]:
        result.setdefault("ok", False)
        result.setdefault("reason", "feature disabled")
    return result


def _resolve_module(provider_id: str) -> object:
    module = GPU_PROVIDER_MAP.get(provider_id.lower())
    if module:
        return module
    raise HTTPException(
        status_code=404, detail=f"provider '{provider_id}' not supported"
    )


def _extract_config(payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    cfg = payload.get("config") or payload.get("cfg") or {}
    if isinstance(cfg, Mapping):
        return dict(cfg)
    return {}


def _extract_job(payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    job = payload.get("job") or payload.get("payload") or {}
    if isinstance(job, Mapping):
        return dict(job)
    return {}


def _ensure_mapping(payload: Any, detail: str) -> MutableMapping[str, Any]:
    if isinstance(payload, MutableMapping):
        return payload
    raise HTTPException(status_code=400, detail=detail)


@router.get("/catalog", summary="List public GPU providers + pricing heuristics")
async def gpu_catalog() -> Dict[str, Any]:
    return {
        "ok": True,
        "feature": _feature_context(),
        "providers": catalog.catalog_for("gpu_backends"),
    }


@router.post(
    "/{provider_id}/health",
    summary="Dry-run GPU credential check",
)
async def gpu_health(
    provider_id: str,
    payload: Mapping[str, Any] | None = Body(None),
) -> Dict[str, Any]:
    module = _resolve_module(provider_id)
    cfg = _extract_config(payload)
    status = module.health(cfg)  # type: ignore[attr-defined]
    return _enrich_result(module, status)


@router.post(
    "/{provider_id}/submit",
    summary="Dry-run GPU job submission",
)
async def gpu_submit(
    provider_id: str,
    payload: Any = Body(default_factory=dict),
) -> Dict[str, Any]:
    data = _ensure_mapping(payload, "payload must be an object")
    cfg = _extract_config(data)
    job = _extract_job(data)
    module = _resolve_module(provider_id)
    result = module.submit(job, cfg)  # type: ignore[attr-defined]
    return _enrich_result(module, result)


@router.post(
    "/{provider_id}/poll",
    summary="Dry-run GPU job polling",
)
async def gpu_poll(
    provider_id: str,
    payload: Any = Body(default_factory=dict),
) -> Dict[str, Any]:
    data = _ensure_mapping(payload, "payload must be an object")
    cfg = _extract_config(data)
    module = _resolve_module(provider_id)
    job_id = str(data.get("job_id") or data.get("id") or "").strip()
    status = module.poll(job_id or f"mock-{provider_id}-1", cfg)  # type: ignore[attr-defined]
    return _enrich_result(module, status)


__all__ = ["router"]
