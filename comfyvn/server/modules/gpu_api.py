from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from comfyvn.core.compute_advisor import advise as compute_advise
from comfyvn.core.gpu_manager import POLICY_MODES, get_gpu_manager
from comfyvn.server.system_metrics import collect_system_metrics

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gpu", tags=["GPU"])
GPU_MANAGER = get_gpu_manager()


def _summarise_devices(devices: list[dict[str, Any]], metrics: dict) -> list[dict]:
    result: list[dict[str, Any]] = []
    metric_map: dict[str, dict[str, Any]] = {}
    for gpu in metrics.get("gpus") or []:
        gpu_id = gpu.get("id")
        if gpu_id is None:
            continue
        metric_map[f"cuda:{gpu_id}"] = gpu

    for device in devices:
        if device.get("kind") != "gpu":
            continue
        metric = metric_map.get(device.get("id") or "")
        mem_total = metric.get("mem_total") if metric else device.get("memory_total")
        mem_used = metric.get("mem_used") if metric else device.get("memory_used")
        mem_free: float | None = None
        try:
            if mem_total is not None and mem_used is not None:
                mem_free = float(mem_total) - float(mem_used)
        except (TypeError, ValueError):
            mem_free = None
        util = metric.get("util") if metric else device.get("utilization")
        summary = {
            "id": device.get("id"),
            "name": device.get("name") or device.get("id"),
            "mem_total": mem_total,
            "mem_free": mem_free,
            "util": util,
        }
        if metric and metric.get("temp_c") is not None:
            summary["temp_c"] = metric.get("temp_c")
        result.append(summary)
    return result


@router.get("/list")
async def list_gpus(
    refresh: bool = Query(True),
    debug: bool = Query(False, description="Include raw metrics payload"),
) -> Dict[str, Any]:
    devices = GPU_MANAGER.list_all(refresh=refresh)
    local_devices = GPU_MANAGER.list_local(refresh=False)
    policy = GPU_MANAGER.get_policy()
    metrics = collect_system_metrics() or {}
    summaries = _summarise_devices(devices, metrics)
    LOGGER.debug(
        "GPU list requested -> %d devices (%d local), mode=%s",
        len(devices),
        len(local_devices),
        policy.get("mode"),
    )
    response: Dict[str, Any] = {
        "ok": True,
        "devices": summaries,
        "policy": policy,
        "modes": sorted(POLICY_MODES),
        "local": local_devices,
    }
    if metrics:
        response["system"] = {
            "cpu": metrics.get("cpu"),
            "mem": metrics.get("mem"),
            "timestamp": metrics.get("timestamp"),
        }
    if debug:
        response["metrics"] = metrics
        response["raw_devices"] = devices
    return response


def _set_policy(
    mode: str, device: Optional[str], preferred_id: Optional[str]
) -> Dict[str, Any]:
    try:
        policy = GPU_MANAGER.set_policy(
            mode,
            device=device,
            preferred_id=preferred_id,
        )
    except AssertionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    LOGGER.info(
        "GPU policy updated -> mode=%s, preferred=%s device=%s",
        policy.get("mode"),
        policy.get("preferred_id"),
        policy.get("manual_device"),
    )
    return {
        "ok": True,
        "policy": policy,
        "devices": GPU_MANAGER.list_all(refresh=False),
    }


@router.get("/policy")
async def get_policy() -> Dict[str, Any]:
    return {"ok": True, "policy": GPU_MANAGER.get_policy()}


@router.post("/policy")
async def set_policy(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    mode = payload.get("mode")
    if not isinstance(mode, str):
        raise HTTPException(status_code=400, detail="mode is required")
    device = payload.get("device")
    preferred_id = payload.get("preferred_id")
    return _set_policy(mode, device, preferred_id)


@router.post("/policy/{mode}")
async def set_policy_legacy(
    mode: str, payload: Optional[Dict[str, Any]] = Body(None)
) -> Dict[str, Any]:
    device = payload.get("device") if isinstance(payload, dict) else None
    preferred_id = payload.get("preferred_id") if isinstance(payload, dict) else None
    return _set_policy(mode, device, preferred_id)


@router.post("/select")
async def select_device(body: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    body = body or {}
    prefer = body.get("prefer")
    requirements = body.get("requirements")
    choice = GPU_MANAGER.select_device(prefer=prefer, requirements=requirements)
    return {"ok": True, "choice": choice, "policy": GPU_MANAGER.get_policy()}


@router.post("/advise")
async def gpu_advise(body: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    body = body or {}
    prefer_remote = bool(body.get("prefer_remote"))
    workload = body.get("workload") or {}
    hardware_override = bool(body.get("hardware_override"))
    recommendation = compute_advise(
        GPU_MANAGER,
        workload=workload,
        prefer_remote=prefer_remote,
        hardware_override=hardware_override,
    )
    return {"ok": True, "advice": recommendation}
