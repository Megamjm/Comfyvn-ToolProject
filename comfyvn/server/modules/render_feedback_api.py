from __future__ import annotations
from PySide6.QtGui import QAction
from fastapi import APIRouter, Body, Query
from typing import Dict, Any
from comfyvn.core.feedback_tracker import FeedbackTracker
from comfyvn.core.render_cache import RenderCache

router = APIRouter(prefix="/render-feedback", tags=["render-feedback"])
_fb = FeedbackTracker()
_cache = RenderCache()

@router.post("/push")
def push_feedback(payload: Dict[str, Any] = Body(...)):
    job_id = str(payload.get("job_id") or "").strip()
    msg = payload.get("msg") or {}
    if not job_id:
        return {"ok": False, "error": "job_id required"}
    _fb.append(job_id, msg)
    _cache.save(job_id, {"feedback": msg})
    return {"ok": True, "job_id": job_id}

@router.get("/read")
def read_feedback(job_id: str = Query(...), limit: int|None = Query(None)):
    return {"ok": True, "items": _fb.read(job_id, limit)}

@router.get("/list")
def list_feedback():
    return {"ok": True, "jobs": _fb.list_jobs()}

@router.get("/cache")
def get_cache(job_id: str = Query(...)):
    return {"ok": True, "cache": _cache.load(job_id)}

@router.delete("/cache/cleanup")
def cleanup_cache(ttl: int = Query(3600*12)):
    _cache.cleanup(ttl)
    return {"ok": True, "ttl": ttl}