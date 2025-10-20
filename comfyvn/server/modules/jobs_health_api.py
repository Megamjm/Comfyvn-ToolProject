from PySide6.QtGui import QAction
from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
def jobs_health():
    return {"ok": True, "jobs": "ready"}