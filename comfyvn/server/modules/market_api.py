from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException

from comfyvn.config import feature_flags
from comfyvn.market import ExtensionMarket, ManifestError

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["Marketplace"])
_market = ExtensionMarket()


def _ensure_enabled() -> None:
    if not feature_flags.is_enabled("enable_extension_market", default=False):
        raise HTTPException(status_code=403, detail="extension marketplace disabled")


@router.get("/catalog")
def catalog() -> Dict[str, Any]:
    _ensure_enabled()
    return {"ok": True, "items": _market.list_catalog()}


@router.get("/installed")
def installed() -> Dict[str, Any]:
    _ensure_enabled()
    return {"ok": True, "items": _market.list_installed()}


@router.post("/install")
def install(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _ensure_enabled()
    package = str(payload.get("package") or payload.get("package_path") or "").strip()
    if not package:
        raise HTTPException(status_code=400, detail="package path is required")
    trust_override = payload.get("trust")
    if trust_override is not None:
        trust_override = str(trust_override)
    try:
        result = _market.install(package, trust_override=trust_override)
    except ManifestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = result.to_payload()
    LOGGER.info(
        "market.install",
        extra={
            "event": "market.install",
            "extension_id": result.extension_id,
            "trust": result.trust.level,
            "package": str(result.package_path),
        },
    )
    return {"ok": True, "installed": payload}


@router.post("/uninstall")
def uninstall(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _ensure_enabled()
    extension_id = str(
        payload.get("id")
        or payload.get("extension_id")
        or payload.get("plugin_id")
        or ""
    ).strip()
    if not extension_id:
        raise HTTPException(status_code=400, detail="extension id is required")
    try:
        _market.uninstall(extension_id)
    except ManifestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    LOGGER.info(
        "market.uninstall",
        extra={
            "event": "market.uninstall",
            "extension_id": extension_id,
        },
    )
    return {"ok": True, "id": extension_id}
