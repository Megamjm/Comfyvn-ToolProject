from PySide6.QtGui import QAction

from fastapi import APIRouter, Body
from pathlib import Path
import json

router = APIRouter(prefix="/settings", tags=["settings"])
CFG = Path("data/config.json"); CFG.parent.mkdir(parents=True, exist_ok=True)
if not CFG.exists(): CFG.write_text(json.dumps({"version":"0.7.0"}, indent=2), encoding="utf-8")

@router.get("/get")
def get_settings():
    return json.loads(CFG.read_text(encoding="utf-8"))

@router.post("/set")
def set_settings(payload: dict = Body(...)):
    cur = get_settings()
    cur.update(payload or {})
    CFG.write_text(json.dumps(cur, indent=2), encoding="utf-8")
    return {"ok": True, "saved": str(CFG)}