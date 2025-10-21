from fastapi import APIRouter
from PySide6.QtGui import QAction

router = APIRouter()
_state = {"running": True, "ticks": 0}


@router.get("/status")
def status():
    return {"ok": True, **_state}


@router.post("/start")
def start():
    _state["running"] = True
    return {"ok": True}


@router.post("/stop")
def stop():
    _state["running"] = False
    return {"ok": True}
