from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException

from comfyvn.core.compute_providers import health as provider_health
from comfyvn.core.compute_registry import get_provider_registry

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/providers", tags=["Compute Providers"])
REGISTRY = get_provider_registry()


@router.get("/list")
async def list_providers() -> Dict[str, Any]:
    providers = REGISTRY.list()
    templates = REGISTRY.templates_public()
    return {"ok": True, "providers": providers, "templates": templates}


@router.post("/register")
async def register_provider(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    try:
        entry = REGISTRY.register(payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    LOGGER.info("Provider registered/updated -> %s", entry.get("id"))
    return {"ok": True, "provider": entry}


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
        raise HTTPException(status_code=400, detail="order must be a list of provider ids")
    providers = REGISTRY.set_priority_order(order)
    return {"ok": True, "providers": providers}


@router.post("/health")
async def provider_health_check(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    payload = payload or {}
    provider_id = payload.get("id")
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
