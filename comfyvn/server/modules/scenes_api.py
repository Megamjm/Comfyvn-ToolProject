import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from PySide6.QtGui import QAction

from comfyvn.server.core.trash import move_to_trash
from comfyvn.server.modules.auth import require_scope

router = APIRouter()
SCENE_DIR = Path("./data/scenes")
SCENE_DIR.mkdir(parents=True, exist_ok=True)


def _path(name: str) -> Path:
    return (SCENE_DIR / f"{name}.json").resolve()


@router.get("/list")
async def list_scenes():
    out = []
    for p in sorted(SCENE_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            data = {}
        out.append(
            {
                "name": p.stem,
                "size": p.stat().st_size,
                "lines": len(data.get("lines", [])),
            }
        )
    return {"ok": True, "items": out}


@router.post("/create")
async def create_scene(
    body: Dict[str, Any], _: bool = Depends(require_scope(["content.write"]))
):
    name = body.get("scene_id") or f"scene_{uuid.uuid4().hex[:8]}"
    rec = {"scene_id": name, "created": time.time(), "lines": body.get("lines") or []}
    p = _path(name)
    p.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return {"ok": True, "name": name}


@router.get("/get/{name}")
async def get_scene(name: str):
    p = _path(name)
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    return json.loads(p.read_text(encoding="utf-8", errors="replace"))


@router.put("/update/{name}")
async def update_scene(
    name: str, body: Dict[str, Any], _: bool = Depends(require_scope(["content.write"]))
):
    p = _path(name)
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    data.update(
        {
            k: v
            for k, v in body.items()
            if k in {"lines", "meta", "participants", "background", "cues"}
        }
    )
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"ok": True}


@router.delete("/delete/{name}")
async def delete_scene(name: str, _: bool = Depends(require_scope(["content.write"]))):
    p = _path(name)
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    move_to_trash(p)
    return {"ok": True, "trashed": True}
