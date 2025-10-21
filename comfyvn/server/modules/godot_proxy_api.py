from fastapi import APIRouter, Body
from PySide6.QtGui import QAction

router = APIRouter(prefix="/play3d", tags=["play3d"])
_STATE = {"running": False, "scene": "Empty", "status": "stopped"}


@router.post("/start")
def start(body: dict = Body(None)):
    _STATE["running"] = True
    _STATE["status"] = "ready"
    _STATE["scene"] = body.get("scene", "Empty") if body else "Empty"
    return {"ok": True, "state": _STATE}


@router.post("/stop")
def stop():
    _STATE["running"] = False
    _STATE["status"] = "stopped"
    return {"ok": True, "state": _STATE}


@router.get("/status")
def status():
    return {"ok": True, "state": _STATE}
