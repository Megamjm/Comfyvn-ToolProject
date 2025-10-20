from __future__ import annotations
from PySide6.QtGui import QAction
from fastapi import APIRouter, Body, Query
from typing import Dict, Any, List
from comfyvn.core.replay_memory import ReplayMemory

router = APIRouter(prefix="/replay", tags=["replay"])

_rm = ReplayMemory()

@router.post("/append")
def append(name: str = Query(...), event: Dict[str, Any] = Body(...)):
    _rm.append(name, event)
    return {"ok": True}

@router.get("/read")
def read(name: str = Query(...), limit: int|None = Query(None)):
    return {"ok": True, "items": _rm.read(name, limit)}

@router.get("/list")
def list_names():
    return {"ok": True, "items": _rm.list()}