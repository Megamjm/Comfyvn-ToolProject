from __future__ import annotations
from PySide6.QtGui import QAction
from fastapi import APIRouter, Body
from typing import Dict, Any
from comfyvn.core.device_registry import DeviceRegistry

router = APIRouter(prefix="/devices", tags=["devices"])
_registry = DeviceRegistry()

@router.get("/list")
def list_devices():
    return {"ok": True, "items": _registry.list()}

@router.post("/register")
def register_device(payload: Dict[str, Any] = Body(...)):
    name = str(payload.get("name") or "").strip()
    kind = str(payload.get("kind") or "compute").strip()
    info = payload.get("info") or {}
    if not name:
        return {"ok": False, "error": "name required"}
    return {"ok": True, "device": _registry.register(name, kind, info)}

@router.post("/status")
def set_status(payload: Dict[str, Any] = Body(...)):
    name = str(payload.get("name") or "").strip()
    status = str(payload.get("status") or "idle").strip()
    if not name:
        return {"ok": False, "error": "name required"}
    return {"ok": True, "device": _registry.set_status(name, status)}