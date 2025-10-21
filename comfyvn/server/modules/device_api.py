from __future__ import annotations

import os

from fastapi import APIRouter
from PySide6.QtGui import QAction

router = APIRouter()


@router.get("/devices/list")
def list_devices():
    # Minimal discovery. Extend with torch if available.
    gpu_count = 0
    try:
        import torch

        gpu_count = torch.cuda.device_count()
    except Exception:
        pass
    gpus = [f"cuda:{i}" for i in range(gpu_count)]
    return {"ok": True, "devices": ["cpu"] + gpus}
