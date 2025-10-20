from PySide6.QtGui import QAction
# comfyvn/server/modules/bridge_api.py
from fastapi import APIRouter, Body, HTTPException
from pathlib import Path
import json, shutil, uuid

router = APIRouter()
SCENES = Path("data/scenes"); SCENES.mkdir(parents=True, exist_ok=True)
ARTDIR = Path("data/assets/scenes"); ARTDIR.mkdir(parents=True, exist_ok=True)

@router.get("/ping")
def ping(): return {"ok": True, "pong": True}

def _scene_path(scene_id: str) -> Path:
    return SCENES / f"{scene_id}.json"

@router.post("/comfyui/link")
def comfyui_link(payload: dict = Body(...)):
    """
    Accepts: { "scene_id": "intro_scene", "image": "path/or/url" }
    If image is a local file path, it is copied under data/assets/scenes/<scene_id>/.
    Scene JSON gets an 'art' array updated with the new relative path.
    """
    scene_id = payload.get("scene_id")
    image = payload.get("image")
    if not scene_id or not image:
        raise HTTPException(status_code=400, detail="scene_id and image required")

    sp = _scene_path(scene_id)
    if not sp.exists():
        raise HTTPException(status_code=404, detail="scene not found")

    sj = json.loads(sp.read_text(encoding="utf-8"))
    target_dir = ARTDIR / scene_id
    target_dir.mkdir(parents=True, exist_ok=True)

    rel = None
    src = Path(image)
    if src.exists():
        name = f"{uuid.uuid4().hex[:8]}_{src.name}"
        dst = target_dir / name
        shutil.copy2(src, dst)
        rel = str(dst.as_posix())
    else:
        # treat as URL or non-existent local path; store as-is
        rel = image

    art = list(sj.get("art") or [])
    art.append(rel)
    sj["art"] = art
    sp.write_text(json.dumps(sj, indent=2), encoding="utf-8")
    return {"ok": True, "scene_id": scene_id, "added": rel}