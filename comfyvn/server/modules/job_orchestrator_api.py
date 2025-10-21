from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Query
from PySide6.QtGui import QAction

from comfyvn.core.job_lifecycle import JobLifecycle
from comfyvn.core.scene_auto_refresh import SceneAutoRefresh

router = APIRouter(prefix="/jobs-orch", tags=["jobs-orch"])
_life = JobLifecycle()
_refresh = SceneAutoRefresh()


@router.post("/register")
def register_job(payload: Dict[str, Any] = Body(...)):
    job_id = str(payload.get("job_id") or "").strip()
    data = payload.get("payload", {})
    if not job_id:
        return {"ok": False, "error": "job_id required"}
    _life.add(job_id, data)
    return {"ok": True, "job": job_id}


@router.post("/done")
def mark_done(payload: Dict[str, Any] = Body(...)):
    job_id = str(payload.get("job_id") or "").strip()
    output = payload.get("output") or {}
    if not job_id:
        return {"ok": False, "error": "job_id required"}
    _life.mark_done(job_id, output)
    return {"ok": True, "job": job_id, "output": output}


@router.post("/heartbeat")
def heartbeat(payload: Dict[str, Any] = Body(...)):
    job_id = str(payload.get("job_id") or "").strip()
    msg = str(payload.get("msg") or "")
    if not job_id:
        return {"ok": False, "error": "job_id required"}
    _life.heartbeat(job_id, msg)
    return {"ok": True, "job": job_id}


@router.post("/scene/add")
def add_scene(payload: Dict[str, Any] = Body(...)):
    scene_id = str(payload.get("scene_id") or "").strip()
    job_id = str(payload.get("job_id") or "").strip()
    if not scene_id or not job_id:
        return {"ok": False, "error": "scene_id and job_id required"}
    _refresh.add(scene_id, job_id)
    return {"ok": True, "scene": scene_id}


@router.get("/scene/ready")
def refresh_ready(ttl: int = Query(300)):
    return {"ok": True, "ready": _refresh.refresh_ready(ttl)}


@router.get("/list")
def list_jobs():
    return {"ok": True, "jobs": _life.list_jobs()}
