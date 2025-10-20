from PySide6.QtGui import QAction
from fastapi import APIRouter
import psutil, time
router = APIRouter()

@router.get("/status")
async def status():
    return {
        "ok": True,
        "cpu": psutil.cpu_percent(interval=0.1),
        "mem": psutil.virtual_memory()._asdict(),
        "uptime": time.time() - psutil.boot_time(),
    }