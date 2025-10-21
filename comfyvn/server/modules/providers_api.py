from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request

from comfyvn.core.compute_providers import health as provider_health
from comfyvn.core.compute_registry import get_provider_registry

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/providers", tags=["Compute Providers"])
REGISTRY = get_provider_registry()


def _build_provider_listing() -> Dict[str, Any]:
    providers = REGISTRY.list()
    templates = REGISTRY.templates_public()
    return {"ok": True, "providers": providers, "templates": templates}


@router.get("")
async def list_providers_root() -> Dict[str, Any]:
    return _build_provider_listing()


@router.get("/")
async def list_providers_root_slash() -> Dict[str, Any]:
    return _build_provider_listing()


@router.get("/list")
async def list_providers() -> Dict[str, Any]:
    return _build_provider_listing()


@router.post("/register")
async def register_provider(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    try:
        entry = REGISTRY.register(payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    LOGGER.info("Provider registered/updated -> %s", entry.get("id"))
    return {"ok": True, "provider": entry}


@router.post("/create")
async def create_provider(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    template_id = payload.get("template_id")
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id is required")
    try:
        entry = REGISTRY.create_from_template(
            template_id,
            provider_id=payload.get("id"),
            name=payload.get("name"),
            base_url=payload.get("base_url"),
            config=payload.get("config"),
            meta_overrides=payload.get("meta"),
            priority=payload.get("priority"),
            active=bool(payload.get("active", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    providers = REGISTRY.list()
    masked = next((p for p in providers if p.get("id") == entry.get("id")), entry)
    LOGGER.info(
        "Provider created from template '%s' -> %s", template_id, entry.get("id")
    )
    return {"ok": True, "provider": masked}


@router.post("/activate")
async def activate_provider(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    provider_id = payload.get("id")
    if not provider_id:
        raise HTTPException(status_code=400, detail="id is required")
    active = bool(payload.get("active", True))
    entry = REGISTRY.set_active(provider_id, active)
    if not entry:
        raise HTTPException(status_code=404, detail="provider not found")
    LOGGER.info("Provider %s -> active=%s", provider_id, active)
    return {"ok": True, "provider": entry}


@router.post("/order")
async def reorder_providers(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    order = payload.get("order")
    if not isinstance(order, list):
        raise HTTPException(
            status_code=400, detail="order must be a list of provider ids"
        )
    providers = REGISTRY.set_priority_order(order)
    return {"ok": True, "providers": providers}


def _provider_health(provider_id: Optional[str]) -> Dict[str, Any]:
    if provider_id:
        entry = REGISTRY.get(provider_id)
        if not entry:
            raise HTTPException(status_code=404, detail="provider not found")
        status = provider_health(entry)
        status["provider_id"] = provider_id
        status["ts"] = int(time.time() * 1000)
        REGISTRY.record_health(provider_id, status)
        return {"ok": True, "status": status}

    # health check for all active providers
    results = []
    for entry in REGISTRY.active_providers():
        pid = entry["id"]
        status = provider_health(entry)
        status["provider_id"] = pid
        status["ts"] = int(time.time() * 1000)
        REGISTRY.record_health(pid, status)
        results.append(status)
    return {"ok": True, "results": results}


@router.get("/health")
async def provider_health_query(
    provider_id: Optional[str] = Query(None, alias="id")
) -> Dict[str, Any]:
    return _provider_health(provider_id)


@router.post("/health")
async def provider_health_check(
    payload: Optional[Dict[str, Any]] = Body(None),
) -> Dict[str, Any]:
    payload = payload or {}
    provider_id = payload.get("id")
    return _provider_health(provider_id)


@router.delete("/remove/{provider_id}")
async def remove_provider(provider_id: str) -> Dict[str, Any]:
    try:
        removed = REGISTRY.remove(provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not removed:
        raise HTTPException(status_code=404, detail="provider not found")
    LOGGER.info("Provider removed -> %s", provider_id)
    return {"ok": True, "removed": provider_id}


def _client_is_local(request: Request) -> bool:
    try:
        client = request.client
        if not client or not client.host:
            return True
        return client.host in {"127.0.0.1", "::1", "localhost"}
    except Exception:  # pragma: no cover - defensive
        return True


def _secrets_export_allowed(request: Request) -> bool:
    env_flag = os.getenv("COMFYVN_ALLOW_SECRET_EXPORT", "").lower()
    if env_flag in {"1", "true", "yes"}:
        return True
    return _client_is_local(request)


@router.get("/export")
async def export_providers(
    request: Request, include_secrets: bool = False
) -> Dict[str, Any]:
    if include_secrets and not _secrets_export_allowed(request):
        raise HTTPException(
            status_code=403,
            detail="Secrets export permitted only from localhost or when COMFYVN_ALLOW_SECRET_EXPORT=1.",
        )
    export = REGISTRY.export_all(mask_secrets=not include_secrets)
    return {"ok": True, "export": export}


@router.post("/import")
async def import_providers(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    replace = bool(payload.get("replace", False))
    overwrite = payload.get("overwrite", True)
    try:
        imported = REGISTRY.import_data(
            payload, replace=replace, overwrite=bool(overwrite)
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    imported_ids: List[str] = [
        row.get("id") for row in imported if isinstance(row, dict) and row.get("id")
    ]
    providers = REGISTRY.list()
    LOGGER.info(
        "Imported %d provider(s) (replace=%s overwrite=%s)",
        len(imported),
        replace,
        overwrite,
    )
    return {"ok": True, "imported": imported_ids, "providers": providers}
