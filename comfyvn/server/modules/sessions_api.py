from __future__ import annotations
from PySide6.QtGui import QAction

from fastapi import APIRouter, Body
from typing import Dict, List

router = APIRouter()
_SESS: Dict[str, Dict] = {}

@router.get("/sessions/list")
def list_sessions():
    return {"ok": True, "items": list(_SESS.values())}

@router.post("/sessions/open")
def open_session(payload: Dict = Body(...)):
    name = str(payload.get("name") or "")
    if not name:
        return {"ok": False, "error": "name required"}
    _SESS[name] = {"name": name, "active": True}
    return {"ok": True, "name": name}

@router.post("/sessions/close")
def close_session(payload: Dict = Body(...)):
    name = str(payload.get("name") or "")
    if name in _SESS:
        _SESS[name]["active"] = False
        return {"ok": True}
    return {"ok": False, "error": "not_found"}