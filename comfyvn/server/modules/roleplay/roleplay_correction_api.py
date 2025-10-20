from PySide6.QtGui import QAction
from fastapi import APIRouter
router = APIRouter()
@router.post('/correct')
async def correct(payload: dict): return {"ok": True, "result": payload}