from __future__ import annotations

"""FastAPI endpoints for the compute job scheduler."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from comfyvn.compute.scheduler import get_scheduler

router = APIRouter(prefix="/api/schedule", tags=["Scheduler"])
SCHEDULER = get_scheduler()


@router.get("/health")
async def schedule_health() -> Dict[str, Any]:
    return {"ok": True, "queues": list(SCHEDULER.state().get("queues", {}).keys())}


@router.get("/state")
async def schedule_state() -> Dict[str, Any]:
    return SCHEDULER.state()


@router.get("/board")
async def schedule_board(limit: int = 100) -> Dict[str, Any]:
    return SCHEDULER.board(limit=limit)


@router.post("/enqueue")
async def schedule_enqueue(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    try:
        job = SCHEDULER.enqueue(payload)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "job": job}


@router.post("/claim")
async def schedule_claim(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = payload or {}
    queue = payload.get("queue") or "local"
    worker_id = payload.get("worker_id")
    device_id = payload.get("device_id")
    job = SCHEDULER.claim(queue, worker_id=worker_id, device_id=device_id)
    return {"ok": True, "job": job}


@router.post("/complete")
async def schedule_complete(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    job_id = payload.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="Missing job_id")
    try:
        job = SCHEDULER.complete(
            job_id,
            status=payload.get("status") or "succeeded",
            bytes_tx=payload.get("bytes_tx"),
            bytes_rx=payload.get("bytes_rx"),
            vram_gb=payload.get("vram_gb"),
            cost_override=payload.get("cost_estimate"),
            duration_sec=payload.get("duration_sec"),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "job": job}


@router.post("/fail")
async def schedule_fail(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    job_id = payload.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="Missing job_id")
    try:
        job = SCHEDULER.fail(job_id, error=payload.get("error"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "job": job}


@router.post("/requeue")
async def schedule_requeue(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    job_id = payload.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="Missing job_id")
    try:
        job = SCHEDULER.requeue(job_id, priority=payload.get("priority"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "job": job}
