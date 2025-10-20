from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/server/modules/render_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import json, time, uuid

router = APIRouter(prefix="/render", tags=["Render"])

QUEUE_FILE = Path("comfyvn/data/render_queue.json")
QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
if not QUEUE_FILE.exists(): QUEUE_FILE.write_text("[]", encoding="utf-8")

def _load() -> list:
    try:
        return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def _save(jobs: list):
    QUEUE_FILE.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

class SubmitPayload(BaseModel):
    scene_id: str | None = None
    params: dict = {}
    target: str = "local"  # or "remote:profile"

@router.get("/health")
def health():
    return {"ok": True, "queue_size": len(_load())}

@router.post("/submit")
def submit(payload: SubmitPayload):
    jobs = _load()
    jid = str(uuid.uuid4())
    job = {
        "id": jid,
        "scene_id": payload.scene_id,
        "params": payload.params,
        "target": payload.target,
        "progress": 0,
        "status": "queued",
        "ts": time.time()
    }
    jobs.append(job)
    _save(jobs)
    return {"ok": True, "id": jid}

@router.get("/status/{jid}")
def status(jid: str):
    jobs = _load()
    for j in jobs:
        if j["id"] == jid:
            # simulate progress if still running
            if j["status"] in ("queued","running"):
                j["status"] = "running"
                j["progress"] = min(100, j.get("progress",0) + 20)
                if j["progress"] >= 100:
                    j["status"] = "done"
            _save(jobs)
            return {"ok": True, "job": j}
    raise HTTPException(404, "job not found")

@router.post("/cancel/{jid}")
def cancel(jid: str):
    jobs = _load()
    for j in jobs:
        if j["id"] == jid and j.get("status") not in ("done","canceled"):
            j["status"] = "canceled"
            _save(jobs)
            return {"ok": True}
    raise HTTPException(404, "job not found or already finished")