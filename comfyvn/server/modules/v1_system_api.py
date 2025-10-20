from PySide6.QtGui import QAction
from fastapi import APIRouter
router = APIRouter()

@router.get("/system/health")
def v1_system_health():
    return {"ok": True, "v1": True}