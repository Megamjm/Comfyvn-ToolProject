from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, Body
from PySide6.QtGui import QAction

router = APIRouter()
RENDERS = Path("data/renders")
RENDERS.mkdir(parents=True, exist_ok=True)


@router.post("/render/scene")
def render_scene(payload: dict = Body(...)):
    scene = payload.get("scene")
    device = payload.get("device", "cpu")
    job = f"render_{scene}_{int(time.time())}"
    info = {"scene": scene, "device": device, "job": job, "status": "queued"}
    (RENDERS / f"{job}.json").write_text(json.dumps(info, indent=2))
    return {"ok": True, "job": job, "device": device}
