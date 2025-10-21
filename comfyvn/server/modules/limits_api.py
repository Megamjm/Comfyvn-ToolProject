from __future__ import annotations

from fastapi import APIRouter
from PySide6.QtGui import QAction

router = APIRouter()


@router.get("/status")
async def status():
    return {"ok": True}
