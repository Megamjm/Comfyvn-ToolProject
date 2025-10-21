from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Query
from PySide6.QtGui import QAction

from comfyvn.core.scene_store import SceneStore

router = APIRouter(prefix="/sceneio", tags=["sceneio"])
_ss = SceneStore()


@router.post("/save")
def save(scene_id: str = Query(...), data: Dict[str, Any] = Body(...)):
    sid = _ss.save(scene_id, data)
    return {"ok": True, "id": sid}


@router.get("/load")
def load(scene_id: str = Query(...)):
    return {"ok": True, "data": _ss.load(scene_id)}


@router.get("/list")
def list_ids():
    return {"ok": True, "items": _ss.list()}
