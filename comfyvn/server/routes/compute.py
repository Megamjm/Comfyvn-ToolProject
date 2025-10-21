from __future__ import annotations

"""Compute device routes: local GPU snapshot, provider registry, advisor."""

import platform
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from comfyvn.compute.advisor import choose_device
from comfyvn.compute.providers import ProviderRegistry, load_seed_from_config
from comfyvn.server.system_metrics import collect_system_metrics

router = APIRouter(prefix="/api", tags=["Compute"])

_STORAGE_PATH = Path("config/compute_providers.json")
_REGISTRY = ProviderRegistry(
    storage_path=_STORAGE_PATH,
    seed=load_seed_from_config(),
)


def _cpu_entry(metrics: Dict[str, Any]) -> Dict[str, Any]:
    name = platform.processor() or "CPU"
    return {
        "id": "cpu",
        "type": "cpu",
        "name": name.strip() or "CPU",
        "load": metrics.get("cpu"),
    }


def _gpu_entries(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for gpu in metrics.get("gpus", []) or []:
        mem_total = gpu.get("mem_total")
        mem_used = gpu.get("mem_used")
        entries.append(
            {
                "id": f"gpu:{gpu.get('id')}",
                "type": "gpu",
                "name": gpu.get("name") or "GPU",
                "load": gpu.get("util"),
                "mem_total_mb": mem_total,
                "mem_used_mb": mem_used,
                "temp_c": gpu.get("temp_c"),
            }
        )
    return entries


def _queue_depth(request: Request) -> int:
    manager = getattr(request.app.state, "job_manager", None)
    if manager is None:
        return 0
    if hasattr(manager, "queue_depth") and callable(manager.queue_depth):
        try:
            return int(manager.queue_depth())
        except Exception:  # pragma: no cover - defensive
            return 0
    queue = getattr(manager, "q", None)
    try:
        return len(queue) if queue is not None else 0
    except Exception:  # pragma: no cover - defensive
        return 0


def _local_vram_gb(metrics: Dict[str, Any]) -> float:
    first = (metrics.get("gpus") or [None])[0] or {}
    total_mb = first.get("mem_total")
    if not total_mb:
        return 0.0
    try:
        return round(float(total_mb) / 1024.0, 2)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 0.0


def _remote_available() -> bool:
    providers = _REGISTRY.list()
    for entry in providers:
        kind = (entry.get("kind") or "").lower()
        if kind != "local":
            return True
    return False


@router.get("/gpu/list")
async def gpu_list() -> Dict[str, Any]:
    metrics = collect_system_metrics() or {}
    devices = [_cpu_entry(metrics)]
    devices.extend(_gpu_entries(metrics))
    return {"devices": devices}


@router.get("/providers")
async def providers_list() -> Dict[str, Any]:
    return {"providers": _REGISTRY.list()}


@router.post("/providers")
async def providers_add(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    provider_id = payload.get("id")
    if not provider_id:
        raise HTTPException(status_code=400, detail="missing provider id")
    try:
        record = _REGISTRY.add(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TypeError as exc:
        raise HTTPException(status_code=400, detail="invalid provider fields") from exc
    data = asdict(record)
    return {"ok": True, "provider": data}


@router.delete("/providers/{provider_id}")
async def providers_remove(provider_id: str) -> Dict[str, Any]:
    removed = _REGISTRY.remove(provider_id)
    if not removed:
        raise HTTPException(status_code=404, detail="provider not found")
    return {"ok": True}


@router.post("/compute/advise")
async def compute_advise(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    job = payload.get("job")
    if not isinstance(job, dict):
        job = payload

    allow_remote = bool(payload.get("allow_remote") or payload.get("prefer_remote"))

    metrics = collect_system_metrics() or {}
    context = {
        "has_gpu": bool((metrics.get("gpus") or [])),
        "local_queue_depth": _queue_depth(request),
        "local_vram_gb": _local_vram_gb(metrics),
        "remote_available": _remote_available(),
    }

    override_ctx = payload.get("context")
    if isinstance(override_ctx, dict):
        context.update(override_ctx)

    decision, reason = choose_device(job, context)

    if decision == "remote":
        if not allow_remote:
            fallback = "gpu" if context.get("has_gpu") else "cpu"
            reason = f"{reason}; remote offload disabled"
            decision = fallback
        elif not context.get("remote_available"):
            fallback = "gpu" if context.get("has_gpu") else "cpu"
            reason = f"{reason}; no remote providers configured"
            decision = fallback

    return {"decision": decision, "reason": reason}
