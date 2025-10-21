from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body

from comfyvn.core.comfy_bridge import ComfyBridge

router = APIRouter(prefix="/comfyui", tags=["comfyui"])
_bridge = ComfyBridge()


@router.post("/set")
def set_base(payload: Dict[str, Any] = Body(...)):
    base = str(payload.get("base") or "")
    if not base:
        return {"ok": False, "error": "base required"}
    _bridge.set_base(base)
    return {"ok": True, "base": _bridge.base}


@router.get("/ping")
def ping():
    return _bridge.ping()


@router.post("/submit")
def submit(payload: Dict[str, Any] = Body(...)):
    return _bridge.submit(payload)
