from fastapi import APIRouter
from PySide6.QtGui import QAction

router = APIRouter()


@router.get("/health")
def jobs_health():
    return {"ok": True, "jobs": "ready"}
