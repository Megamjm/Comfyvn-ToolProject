from PySide6.QtGui import QAction
from fastapi import APIRouter
router = APIRouter()
@router.get('/sample')
async def sample(): return {"ok": True, "choices": ["happy","sad","angry"]}