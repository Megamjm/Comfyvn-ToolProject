from __future__ import annotations
from PySide6.QtGui import QAction
import os
from fastapi import APIRouter
router = APIRouter()

@router.get("/status")
async def status():
    return {
        "ok": True,
        "REDIS_URL": bool(os.getenv("REDIS_URL")),
        "S3_BUCKET": os.getenv("S3_BUCKET") or "",
        "API_KEY": bool(os.getenv("API_KEY")),
    }