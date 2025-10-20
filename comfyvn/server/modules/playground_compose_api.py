from __future__ import annotations
from PySide6.QtGui import QAction

from fastapi import APIRouter, Body
import json
from pathlib import Path

router = APIRouter()

@router.post("/playground/compose")
def compose(payload: dict = Body(...)):
    from comfyvn.server.modules.scene_api import _scene_path
    from comfyvn.server.modules.persona_api import _load as _personas
    scene = payload.get("scene")
    if not scene:
        return {"ok": False, "error": "scene id required"}
    p = _scene_path(scene)
    if not p.exists():
        return {"ok": False, "error": "scene not found"}
    s = json.loads(p.read_text(encoding="utf-8"))
    personas = _personas()
    composed = []
    for line in s.get("dialogue", []):
        spk = line.get("speaker")
        traits = personas.get(spk, {}).get("traits", {})
        image_stub = f"sprites/{spk}_{traits.get('mood','neutral')}.png"
        composed.append({"speaker": spk, "text": line.get("text"), "image": image_stub})
    return {"ok": True, "scene": s["id"], "frames": composed}