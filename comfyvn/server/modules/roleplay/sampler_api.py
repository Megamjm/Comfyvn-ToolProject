from fastapi import APIRouter
from PySide6.QtGui import QAction

router = APIRouter()


@router.get("/sample")
async def sample():
    return {"ok": True, "choices": ["happy", "sad", "angry"]}
