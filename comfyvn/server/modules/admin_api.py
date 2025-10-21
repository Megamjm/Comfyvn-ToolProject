import time

import psutil
from fastapi import APIRouter
from PySide6.QtGui import QAction

router = APIRouter()


@router.get("/status")
async def status():
    return {
        "ok": True,
        "cpu": psutil.cpu_percent(interval=0.1),
        "mem": psutil.virtual_memory()._asdict(),
        "uptime": time.time() - psutil.boot_time(),
    }
