from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from comfyvn.core.gpu_manager import get_gpu_manager
from comfyvn.core.compute_advisor import advise as compute_advise

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gpu", tags=["GPU"])
GPU_MANAGER = get_gpu_manager()


@router.get("/list")
async def list_gpus(refresh: bool = Query(True)) -> Dict[str, Any]:
    devices = GPU_MANAGER.list_all(refresh=refresh)
    policy = GPU_MANAGER.get_policy()
    LOGGER.debug("GPU list requested -> %d devices, mode=%s", len(devices), policy.get("mode"))
    return {"ok": True, "devices": devices, "policy": policy}


def _set_policy(mode: str, device: Optional[str]) -> Dict[str, Any]:
    try:
        policy = GPU_MANAGER.set_policy(mode, device=device)
    except AssertionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "policy": policy}


@router.get("/policy")
async def get_policy() -> Dict[str, Any]:
    return {"ok": True, "policy": GPU_MANAGER.get_policy()}


@router.post("/policy")
async def set_policy(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    mode = payload.get("mode")
    if not isinstance(mode, str):
        raise HTTPException(status_code=400, detail="mode is required")
    device = payload.get("device")
    return _set_policy(mode, device)


@router.post("/policy/{mode}")
async def set_policy_legacy(mode: str, payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    device = payload.get("device") if isinstance(payload, dict) else None
    return _set_policy(mode, device)


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
