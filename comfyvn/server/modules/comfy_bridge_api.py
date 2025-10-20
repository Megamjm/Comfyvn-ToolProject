from __future__ import annotations
from PySide6.QtGui import QAction
from fastapi import APIRouter, Body
from typing import Dict, Any

router = APIRouter()
_STATE: Dict[str, Any] = {"base": None}

@router.post("/comfy/set")
def set_base(payload: Dict = Body(...)):
    base = str(payload.get("base") or "")
    if not base:
        return {"ok": False, "error": "base required"}
    _STATE["base"] = base.rstrip("/")
    return {"ok": True, "base": _STATE["base"]}

@router.post("/comfy/ping")
def ping():
    return {"ok": True, "base": _STATE.get("base")}

@router.post("/comfy/submit")
def submit(payload: Dict = Body(...)):
    # stub: accept and echo; real bridge posts to ComfyUI
    return {"ok": True, "submitted": payload, "base": _STATE.get("base")}