from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/server/modules/system_api_safe.py
from fastapi import APIRouter, HTTPException
import shutil

router = APIRouter(prefix="/system", tags=["SystemSafe"])

# Try import psutil; optional
try:
    import psutil
except Exception:
    psutil = None

@router.get("/metrics")
async def metrics():
    try:
        cpu = mem = disk = None
        if psutil:
            cpu = psutil.cpu_percent(interval=0.05)
            mem = psutil.virtual_memory().percent
        try:
            du = shutil.disk_usage(".")
            disk = round(100.0 * du.used / max(1, du.total), 2)
        except Exception:
            disk = None
        return {"ok": True, "cpu": cpu, "mem": mem, "disk": disk, "gpus": []}
    except Exception as e:
        raise HTTPException(500, f"metrics error: {e}")