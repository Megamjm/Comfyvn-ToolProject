from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException

from comfyvn.bridge.comfy_hardening import HardenedBridgeError, HardenedComfyBridge
from comfyvn.core.comfy_bridge import ComfyBridge

router = APIRouter(prefix="/comfyui", tags=["comfyui"])
_bridge = ComfyBridge()
_hardened = HardenedComfyBridge(_bridge)


@router.post("/set")
def set_base(payload: Dict[str, Any] = Body(...)):
    base = str(payload.get("base") or "")
    if not base:
        return {"ok": False, "error": "base required"}
    _bridge.set_base(base)
    _hardened.reload()
    return {"ok": True, "base": _bridge.base_url}


@router.get("/ping")
def ping():
    return _bridge.ping()


@router.post("/submit")
def submit(payload: Dict[str, Any] = Body(...)):
    _hardened.reload()
    if _hardened.enabled:
        try:
            return _hardened.submit(payload)
        except HardenedBridgeError as exc:
            raise HTTPException(
                status_code=getattr(exc, "status_code", 400), detail=str(exc)
            )
    result = _bridge.submit(payload)
    if isinstance(result, dict) and not result.get("ok", False):
        raise HTTPException(
            status_code=503,
            detail=str(result.get("error") or "ComfyUI bridge unavailable"),
        )
    return result
