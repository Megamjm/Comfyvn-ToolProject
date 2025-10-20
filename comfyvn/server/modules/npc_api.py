from PySide6.QtGui import QAction

# comfyvn/server/modules/npc_api.py
from fastapi import APIRouter, Body
from pathlib import Path
import json, time
from typing import Dict, Any

router = APIRouter()
NPC_DIR = Path("data/npc"); NPC_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/put/{name}")
def put_npc(name: str, body: Dict[str,Any] = Body(...)):
    p = NPC_DIR / f"{name}.json"
    p.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return {"ok": True, "saved": str(p)}

@router.get("/get/{name}")
def get_npc(name: str):
    p = NPC_DIR / f"{name}.json"
    if not p.exists(): return {"ok": False, "error": "not_found"}
    return json.loads(p.read_text(encoding="utf-8"))

@router.get("/list")
def list_npc():
    return {"ok": True, "items": [x.stem for x in NPC_DIR.glob("*.json")]}