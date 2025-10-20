from __future__ import annotations
from PySide6.QtGui import QAction
from fastapi import APIRouter, HTTPException
from typing import Any
from comfyvn.core.task_registry import task_registry

router = APIRouter(prefix="/jobs", tags=["Jobs"])

@router.post("/enqueue")
async def enqueue_job(job: dict[str, Any]):
    """Accepts {"kind": str, "payload": {...}}; returns {"id": "..."}"""
    kind = job.get("kind") or "generic"
    payload = job.get("payload") or {}
    tid = task_registry.register(kind, payload)
    return {"ok": True, "id": tid}

@router.get("/status/{tid}")
async def job_status(tid: str):
    j = task_registry.get(tid)
    if not j:
        raise HTTPException(404, "job not found")
    return {"ok": True, "job": j}

@router.get("/all")
async def job_all():
    return {"ok": True, "jobs": task_registry.list()}