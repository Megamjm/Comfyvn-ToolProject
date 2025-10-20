from PySide6.QtGui import QAction
from fastapi import APIRouter, Body

router = APIRouter()
_endpoints = {
    "sillytavern": None,
    "lmstudio": None,
    "comfyui": None,
}

@router.get("/status")
def status():
    return {"ok": True, "endpoints": _endpoints}

@router.post("/configure")
def configure(payload: dict = Body(...)):
    _endpoints.update({k: payload.get(k, v) for k, v in _endpoints.items()})
    return {"ok": True, "endpoints": _endpoints}