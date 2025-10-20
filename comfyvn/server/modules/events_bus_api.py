from __future__ import annotations
from PySide6.QtGui import QAction
from fastapi import APIRouter, Body, Query
from typing import Dict, Any
from comfyvn.core.event_hub import EventHub

router = APIRouter(prefix="/events-bus", tags=["events-bus"])
_hub = EventHub()

@router.post("/publish")
def publish(payload: Dict[str, Any] = Body(...)):
    topic = str(payload.get("topic") or "").strip()
    data = payload.get("data") or {}
    if not topic:
        return {"ok": False, "error": "topic required"}
    res = _hub.publish(topic, data)
    return {"ok": True, **res}

@router.get("/history")
def history(topic: str = Query(...), since: float = Query(0.0), limit: int = Query(100)):
    return {"ok": True, "items": _hub.history(topic, since, limit)}