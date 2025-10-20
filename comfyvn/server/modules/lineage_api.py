from __future__ import annotations
from PySide6.QtGui import QAction
import json
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from comfyvn.server.core.artifacts import list_local
RUNS_DIR = Path("./data/runs")

router = APIRouter()

@router.get("/run/{rid}")
async def lineage_run(rid: str):
    rp = RUNS_DIR / f"{rid}.json"
    if not rp.exists(): raise HTTPException(status_code=404, detail="run not found")
    run = json.loads(rp.read_text(encoding="utf-8"))
    arts = list_local(run_id=rid, limit=500).get("items", [])
    return {"ok": True, "run": run, "artifacts": arts}

@router.get("/scene/{scene_id}")
async def lineage_scene(scene_id: str):
    runs = []
    for p in sorted(RUNS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:500]:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            if r.get("inputs",{}).get("scene_id")==scene_id or r.get("scene_id")==scene_id:
                runs.append(r)
        except Exception:
            pass
    arts = list_local(scene_id=scene_id, limit=500).get("items", [])
    return {"ok": True, "runs": runs, "artifacts": arts}