from fastapi import APIRouter, Body
from PySide6.QtGui import QAction

from comfyvn.core.analyzers import simple_character_scan

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("/scan")
def scan(body: dict = Body(...)):
    text = body.get("text", "")
    return {"ok": True, "scan": simple_character_scan(text)}
