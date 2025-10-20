from __future__ import annotations
from PySide6.QtGui import QAction
from fastapi import APIRouter
router = APIRouter()
@router.get("/status")
async def status(): return {"ok": True}