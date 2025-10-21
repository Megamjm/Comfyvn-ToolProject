from fastapi import APIRouter
from PySide6.QtGui import QAction

router = APIRouter()


@router.post("/correct")
async def correct(payload: dict):
    return {"ok": True, "result": payload}
