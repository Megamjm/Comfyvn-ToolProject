# comfyvn/server/modules/jobs_api.py
# 🧩 Jobs API — unified with JobManager + EventBus (Phase 3.3)
# [Server Core Production Chat | ComfyVN Architect Integration Sync]

from __future__ import annotations
import json, time, uuid
from fastapi import APIRouter, Request, HTTPException

router = APIRouter(prefix="/jobs", tags=["Jobs"])


# -------------------------------------------------------------------
# Utilities
# -------------------------------------------------------------------
def _jm(request: Request):
    """Helper to safely access JobManager from app state."""
    jm = getattr(request.app.state, "job_manager", None)
    if jm is None:
        raise HTTPException(500, "JobManager not initialized")
    return jm


# -------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------
@router.get("/status")
async def status(request: Request):
    """Return full job listing and summary."""
    jm = _jm(request)
    return jm.poll()


@router.get("/poll")
async def poll(request: Request):
    """Alias for GUI job polling."""
    jm = _jm(request)
    return jm.poll()


@router.post("/create")
async def create_job(request: Request):
    """Register a new job with optional metadata."""
    jm = _jm(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    job_type = payload.get("type", "generic")
    origin = payload.get("origin", "api")
    token = payload.get("token")
    job = jm.create(job_type=job_type, payload=payload, origin=origin, token=token)
    return {"ok": True, "job": job}


@router.post("/update/{job_id}")
async def update_job(job_id: str, request: Request):
    """Update job status or progress."""
    jm = _jm(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    jm.update(job_id, **payload)
    return {"ok": True, "job": jm.get(job_id)}


@router.post("/complete/{job_id}")
async def complete_job(job_id: str, request: Request):
    """Mark a job as completed."""
    jm = _jm(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    jm.complete(job_id, payload.get("result", {}))
    return {"ok": True, "job": jm.get(job_id)}


@router.post("/fail/{job_id}")
async def fail_job(job_id: str, request: Request):
    """Mark job as failed with an error message."""
    jm = _jm(request)
    try:
        payload = await request.json()
        error_msg = payload.get("error", "Unknown error")
    except Exception:
        error_msg = "Unknown error"
    jm.fail(job_id, error_msg)
    return {"ok": True, "job": jm.get(job_id)}


@router.post("/cancel/{job_id}")
async def cancel_job(job_id: str, request: Request):
    """Cancel a running job."""
    jm = _jm(request)
    jm.cancel(job_id)
    return {"ok": True, "job": jm.get(job_id)}


@router.post("/progress/{job_id}")
async def job_progress(job_id: str, request: Request):
    """Incrementally update progress percentage."""
    jm = _jm(request)
    try:
        payload = await request.json()
        progress = float(payload.get("progress", 0))
    except Exception:
        raise HTTPException(400, "Invalid progress value")
    jm.progress(job_id, progress)
    return {"ok": True, "job": jm.get(job_id)}


@router.post("/clear")
async def clear_jobs(request: Request):
    """Clear completed or errored jobs from memory."""
    jm = _jm(request)
    cleared = jm.purge(status="complete") + jm.purge(status="error")
    return {"ok": True, "cleared": cleared}


@router.get("/history")
async def job_history(request: Request):
    """Return in-memory job history for GUI display."""
    jm = _jm(request)
    return {"ok": True, "history": jm.list()}


# -------------------------------------------------------------------
# Optional debug / event tests
# -------------------------------------------------------------------
@router.get("/emit_test")
async def emit_test(request: Request):
    """Emit a dummy event via EventBus for testing TaskManagerDock."""
    jm = _jm(request)
    evt = {"type": "job.test", "msg": "Hello from Jobs API"}
    try:
        jm.event_bus.publish(evt)
        return {"ok": True, "sent": evt}
    except Exception as e:
        raise HTTPException(500, f"Emit failed: {e}")
