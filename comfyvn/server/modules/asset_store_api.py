from __future__ import annotations

from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PySide6.QtGui import QAction

from comfyvn.server.core.asset_store import (delete_keys, get_url, list_keys,
                                             put_bytes)

router = APIRouter()


@router.get("/list")
async def list_assets(prefix: str = ""):
    return {"ok": True, "items": list_keys(prefix)}


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    try:
        data = await file.read()
        key = put_bytes(data, filename=file.filename or "blob")
        return {"ok": True, "key": key, "url": get_url(key)}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.delete("/delete")
async def delete(keys: List[str]):
    n = delete_keys(keys)
    return {"ok": True, "deleted": n}


@router.get("/url")
async def url(key: str):
    return {"ok": True, "url": get_url(key)}
