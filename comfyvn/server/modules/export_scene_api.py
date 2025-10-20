from __future__ import annotations
from PySide6.QtGui import QAction

from fastapi import APIRouter, Body
from pathlib import Path
import json

router = APIRouter()
OUT = Path("exports/renpy"); OUT.mkdir(parents=True, exist_ok=True)

@router.post("/export/scene")
def export_scene(payload: dict = Body(...)):
    from comfyvn.server.modules.scene_api import _scene_path
    sid = payload.get("scene")
    if not sid:
        return {"ok": False, "error": "scene required"}
    src = _scene_path(sid)
    if not src.exists():
        return {"ok": False, "error": "scene not found"}
    data = json.loads(src.read_text(encoding="utf-8"))
    out = OUT / f"{sid}.rpy"
    with out.open("w", encoding="utf-8") as f:
        f.write(f"label {sid}:\n")
        for l in data.get("dialogue", []):
            f.write(f'    "{l.get("speaker")}": "{l.get("text")}"\n')
    return {"ok": True, "file": str(out)}