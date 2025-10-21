from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Body
from PySide6.QtGui import QAction

from comfyvn.server.core import asset_cache as cache

router = APIRouter(tags=["assetsx"])


@router.get("/assetsx/list")
def list_assets():
    return {"ok": True, "items": cache.list_all()}


@router.post("/assetsx/lora")
def put_lora(payload: Dict = Body(...)):
    name = str(payload.get("name") or "")
    path = str(payload.get("path") or "")
    if not name or not path:
        return {"ok": False, "error": "name and path required"}
    return cache.put("lora", name, path)


@router.post("/assetsx/ipadapter")
def put_ipadapter(payload: Dict = Body(...)):
    name = str(payload.get("name") or "")
    path = str(payload.get("path") or "")
    if not name or not path:
        return {"ok": False, "error": "name and path required"}
    return cache.put("ipadapter", name, path)
