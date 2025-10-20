from __future__ import annotations
from PySide6.QtGui import QAction

from fastapi import APIRouter, Body
from pathlib import Path
import json, time

router = APIRouter()
SCENE_DIR = Path("data/scenes"); SCENE_DIR.mkdir(parents=True, exist_ok=True)

def _scene_path(sid): return SCENE_DIR / f"{sid}.json"

@router.post("/scene/create")
def create_scene(payload: dict = Body(...)):
    sid = payload.get("id") or f"scene_{int(time.time())}"
    path = _scene_path(sid)
    data = {
        "id": sid,
        "world": payload.get("world", "default"),
        "characters": payload.get("characters", []),
        "dialogue": payload.get("dialogue", []),
        "created": time.time(),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"ok": True, "scene": sid}

@router.get("/scene/list")
def list_scenes():
    items = [p.stem for p in SCENE_DIR.glob("*.json")]
    return {"ok": True, "items": items}

@router.get("/scene/get/{sid}")
def get_scene(sid: str):
    p = _scene_path(sid)
    if not p.exists():
        return {"ok": False, "error": "not found"}
    return {"ok": True, "data": json.loads(p.read_text(encoding="utf-8"))}

@router.get("/scene/play/{sid}")
def play_scene(sid: str):
    from comfyvn.server.modules.persona_api import _load as _personas
    from comfyvn.server.modules.lore_api import _load as _lore
    from comfyvn.server.modules.voice_api import _cfg
    p = _scene_path(sid)
    if not p.exists():
        return {"ok": False, "error": "scene not found"}
    scene = json.loads(p.read_text(encoding="utf-8"))
    personas = _personas()
    lore = _lore()
    cfg = _cfg()
    enriched = []
    for line in scene.get("dialogue", []):
        speaker = line.get("speaker")
        traits = personas.get(speaker, {}).get("traits", {})
        world = scene.get("world")
        lore_info = lore.get(world, {})
        enriched.append({
            "speaker": speaker,
            "text": line.get("text"),
            "traits": traits,
            "lore": lore_info,
            "voice_engine": cfg.get("engine"),
        })
    return {"ok": True, "scene": scene["id"], "lines": enriched}