from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from comfyvn.core.task_registry import TaskItem, task_registry

router = APIRouter(prefix="/jobs", tags=["Jobs"])

LOGGER = logging.getLogger(__name__)


def _format_ts(value: float | None) -> str | None:
    if not value:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _serialize_task(task: TaskItem) -> Dict[str, Any]:
    data = {
        "id": task.id,
        "kind": task.kind,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "meta": task.meta,
        "created_at": _format_ts(task.created_at),
        "updated_at": _format_ts(task.updated_at),
    }
    return data


@router.post("/enqueue")
async def enqueue_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Accepts {"kind": str, "payload": {...}}; returns {"id": "..."}."""
    kind = job.get("kind") or "generic"
    payload = job.get("payload") or {}
    message = job.get("message", "")
    meta = job.get("meta")
    task_id = task_registry.register(kind, payload, message=message, meta=meta)
    return {"ok": True, "id": task_id}


@router.get("/status/{task_id}")
async def job_status(task_id: str) -> Dict[str, Any]:
    task = task_registry.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": _serialize_task(task)}


@router.get("/all")
async def job_all() -> Dict[str, Any]:
    tasks = [_serialize_task(task) for task in task_registry.list()]
    return {"ok": True, "jobs": tasks}


@router.get("/logs/{task_id}", response_class=PlainTextResponse)
async def job_logs(task_id: str) -> str:
    task = task_registry.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="job not found")
    meta = task.meta or {}
    logs_path = meta.get("logs_path")
    if not logs_path:
        raise HTTPException(status_code=404, detail="log not available for job")

    path = Path(str(logs_path)).expanduser().resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail="log file missing")

    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:  # pragma: no cover - filesystem dependent
        raise HTTPException(
            status_code=500, detail=f"failed to read log file: {exc}"
        ) from exc


@router.websocket("/ws")
async def job_stream(websocket: WebSocket):
    await websocket.accept()
    LOGGER.info("Job stream client connected from %s", websocket.client)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=128)

    def listener(task: TaskItem) -> None:
        payload = {
            "type": "job.update",
            "job": _serialize_task(task),
        }

        def _enqueue() -> None:
            if queue.full():
                try:
                    queue.get_nowait()
                    LOGGER.debug("Job stream queue full; dropping oldest event")
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(payload)

        loop.call_soon_threadsafe(_enqueue)

    task_registry.subscribe(listener)

    async def send_snapshot() -> None:
        snapshot = [_serialize_task(task) for task in task_registry.list()]
        await websocket.send_json({"type": "snapshot", "jobs": snapshot})

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(15)
            await websocket.send_json({"type": "ping"})

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        await send_snapshot()
        LOGGER.debug("Job stream snapshot sent (%d jobs)", len(task_registry.list()))
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        LOGGER.info("Job stream client disconnected: %s", websocket.client)
    except Exception as exc:
        LOGGER.warning("Job stream error for %s: %s", websocket.client, exc)
    finally:
        heartbeat_task.cancel()
        task_registry.unsubscribe(listener)
