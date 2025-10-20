from __future__ import annotations
from PySide6.QtGui import QAction
import json
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from comfyvn.server.modules.auth import require_scope
from comfyvn.server.core.job_manager import JobManager

RUNS_DIR = Path("./data/runs"); RUNS_DIR.mkdir(parents=True, exist_ok=True)

def router_factory(jm: JobManager) -> APIRouter:
    router = APIRouter()

    @router.post("/run")
    async def run(body: Dict[str, Any], _: bool = Depends(require_scope(["jobs.write"]))):
        # body: {workflow?, name?, inputs?, cache?}
        jid = jm.enqueue("wf_run", body)
        return {"ok": True, "id": jid}

    @router.get("/runs/{rid}")
    async def get_run(rid: str):
        p = RUNS_DIR / f"{rid}.json"
        if not p.exists(): raise HTTPException(status_code=404, detail="not found")
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))

    @router.get("/list")
    async def list_runs():
        items = []
        for p in sorted(RUNS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:200]:
            try: items.append(json.loads(p.read_text(encoding="utf-8", errors="replace")))
            except Exception: pass
        return {"ok": True, "items": items}

    return router

def router(jm: JobManager): return router_factory(jm)
def WfRuntimeRouter(jm: JobManager): return router_factory(jm)