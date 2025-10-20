from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/server/modules/gpu_api.py
from fastapi import APIRouter, HTTPException
from comfyvn.core.gpu_manager import GPUManager

router = APIRouter(prefix="/api/gpu", tags=["GPU"])
_mgr = GPUManager()

@router.get("/list")
async def gpu_list():
    return {"ok": True, "devices": _mgr.list_all(), "policy": _mgr.get_policy()}

@router.post("/policy/{mode}")
async def gpu_set_policy(mode: str):
    try:
        return {"ok": True, "policy": _mgr.set_policy(mode)}
    except AssertionError:
        raise HTTPException(400, "mode must be one of: auto|manual|sticky")