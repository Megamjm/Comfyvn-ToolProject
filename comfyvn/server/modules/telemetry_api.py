from __future__ import annotations
from PySide6.QtGui import QAction

from fastapi import APIRouter
from typing import Any, Dict
import platform, time

router = APIRouter()

@router.get("/telemetry")
def metrics() -> Dict[str, Any]:
    out = {"ts": time.time(), "system": platform.platform()}
    try:
        from comfyvn.server.app import app
        jm = getattr(app.state, "job_manager", None)
        rm = getattr(app.state, "render_manager", None)
        out["jobs"] = jm.snapshot() if jm and hasattr(jm, "snapshot") else {"queued_count": 0}
        out["renders"] = rm.snapshot() if rm and hasattr(rm, "snapshot") else {"queued": []}
    except Exception as e:
        out["error"] = str(e)
    return out