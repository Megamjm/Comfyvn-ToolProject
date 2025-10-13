# comfyvn/server/modules/roleplay/roleplay_correction_api.py
# 🤝 Roleplay Scene Correction API — Phase 3.6
# [Roleplay Import & Collaboration Chat | ComfyVN_Architect]

import os, json, datetime
from typing import List, Dict
from fastapi import APIRouter, Body

router = APIRouter(prefix="/roleplay", tags=["Roleplay Import"])

CONVERTED_DIR = "./data/roleplay/converted"
META_DIR = "./data/roleplay/metadata"
os.makedirs(CONVERTED_DIR, exist_ok=True)
os.makedirs(META_DIR, exist_ok=True)


@router.post("/apply_corrections")
async def apply_corrections(payload: Dict = Body(...)):
    """
    Overwrites the scene JSON with corrected lines and optional character metadata.
    Expected payload:
      {
        "scene_id": "rp_xxxx",
        "lines": [{"speaker":"A","text":"..."}],
        "character_meta": {"A":"desc", "B":"desc"}
      }
    """
    sid = payload.get("scene_id")
    if not sid:
        return {"error": "missing scene_id"}

    path = os.path.join(CONVERTED_DIR, f"{sid}.json")
    if not os.path.exists(path):
        return {"error": "scene not found"}

    # --- update scene ---
    with open(path, "r", encoding="utf-8") as f:
        scene = json.load(f)

    if "lines" in payload and isinstance(payload["lines"], list):
        scene["lines"] = payload["lines"]
        scene["meta"]["last_corrected"] = datetime.datetime.now().isoformat()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(scene, f, indent=2)

    # --- save character meta if provided ---
    cm = payload.get("character_meta")
    if cm:
        meta_path = os.path.join(META_DIR, f"{sid}_characters.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(cm, f, indent=2)

    return {"status": "ok", "scene_id": sid, "lines": len(scene["lines"])}
