import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, Body
from PySide6.QtGui import QAction

# comfyvn/server/modules/export_hook.py
# 🔄 Auto-export hook – triggers Ren'Py export when a workflow job completes


router = APIRouter()
EXPORTS = Path("exports/renpy")
EXPORTS.mkdir(parents=True, exist_ok=True)


@router.post("/notify")
def notify_export(payload: dict = Body(...)):
    """Called internally when a workflow finishes"""
    jid = payload.get("job_id")
    name = payload.get("workflow", "unnamed")
    if not jid:
        return {"ok": False, "error": "missing job_id"}

    src = Path("data/workflows") / f"done_{jid}.json"
    if not src.exists():
        return {"ok": False, "error": "job file missing"}

    # Call the Ren'Py exporter
    try:
        subprocess.run(
            ["python", "scripts/export_renpy.py"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "exported": True, "job_id": jid, "workflow": name}
