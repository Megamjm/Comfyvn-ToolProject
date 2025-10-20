from PySide6.QtGui import QAction
import json, time, uuid
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from comfyvn.server.core.trash import move_to_trash
from comfyvn.server.modules.auth import require_scope

router = APIRouter()
CHAR_DIR = Path("./data/characters"); CHAR_DIR.mkdir(parents=True, exist_ok=True)

def _path(name: str) -> Path: return (CHAR_DIR / f"{name}.json").resolve()

@router.get("/list")
async def list_characters():
    out=[]
    for p in sorted(CHAR_DIR.glob("*.json")):
        try: data=json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception: data={}
        out.append({"name": p.stem, "avatar": data.get("avatar"), "tags": data.get("tags", [])})
    return {"ok": True, "items": out}

@router.post("/create")
async def create_character(body: Dict[str, Any], _: bool = Depends(require_scope(["content.write"]))):
    name = body.get("name") or f"char_{uuid.uuid4().hex[:6]}"
    rec = {"name": name, "created": time.time(), "tags": body.get("tags", []), "avatar": body.get("avatar"), "prompt": body.get("prompt")}
    p = _path(name); p.write_text(json.dumps(rec, indent=2), encoding="utf-8"); return {"ok": True, "name": name}

@router.get("/get/{name}")
async def get_character(name: str):
    p = _path(name)
    if not p.exists(): raise HTTPException(status_code=404, detail="not found")
    return json.loads(p.read_text(encoding="utf-8", errors="replace"))

@router.put("/update/{name}")
async def update_character(name: str, body: Dict[str, Any], _: bool = Depends(require_scope(["content.write"]))):
    p = _path(name); 
    if not p.exists(): raise HTTPException(status_code=404, detail="not found")
    data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    for k in ["tags","avatar","prompt"]: 
        if k in body: data[k]=body[k]
    p.write_text(json.dumps(data, indent=2), encoding="utf-8"); return {"ok": True}

@router.delete("/delete/{name}")
async def delete_character(name: str, _: bool = Depends(require_scope(["content.write"]))):
    p = _path(name); 
    if not p.exists(): raise HTTPException(status_code=404, detail="not found")
    move_to_trash(p); return {"ok": True, "trashed": True}