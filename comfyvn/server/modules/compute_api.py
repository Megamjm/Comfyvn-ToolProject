from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Query

from comfyvn.core.compute_advisor import advise as compute_advise
from comfyvn.core.compute_registry import get_provider_registry
from comfyvn.core.gpu_manager import get_gpu_manager

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/compute", tags=["Compute Advisor"])
GPU_MANAGER = get_gpu_manager()
REGISTRY = get_provider_registry()

_TASK_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "img": {"type": "render", "min_vram_gb": 8.0},
    "tts": {"type": "tts", "min_vram_gb": 12.0},
    "export": {"type": "export", "min_vram_gb": 0.0},
}


def _parse_size_mb(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return None
        multiplier = 1.0
        if text.endswith("gb"):
            multiplier = 1024.0
            text = text[:-2]
        elif text.endswith("mb"):
            text = text[:-2]
        elif text.endswith("kb"):
            multiplier = 1.0 / 1024.0
            text = text[:-2]
        try:
            return float(text) * multiplier
        except ValueError:
            LOGGER.debug("Unable to parse size '%s'", value)
            return None
    return None


def _infer_vram(task: str, size_mb: Optional[float], default: float) -> Optional[float]:
    if size_mb is None or size_mb <= 0:
        return default if default > 0 else None
    if task == "img":
        if size_mb >= 4096:
            return 24.0
        if size_mb >= 2048:
            return 16.0
        if size_mb >= 1024:
            return 12.0
        return max(default, 8.0)
    if task == "tts":
        return max(default, 12.0)
    if task == "export":
        if size_mb >= 2048:
            return 8.0
        return None
    return default if default > 0 else None


def _build_workload_from_query(task: str, size_mb: Optional[float]) -> Dict[str, Any]:
    normalized = task.lower().strip() if isinstance(task, str) else ""
    defaults = _TASK_DEFAULTS.get(normalized, {"type": normalized or "generic", "min_vram_gb": 0.0})
    min_vram = _infer_vram(normalized, size_mb, float(defaults.get("min_vram_gb", 0.0)))
    workload = {
        "type": defaults.get("type"),
        "requirements": {
            "type": defaults.get("type"),
            "min_vram_gb": min_vram,
        },
    }
    if size_mb is not None:
        workload["assets"] = [{"name": "payload", "size_mb": size_mb}]
    return workload


def _rationale_from_choice(choice: Dict[str, Any], job_type: str) -> str:
    reason = choice.get("reason")
    policy = choice.get("policy")
    device = choice.get("device")
    if reason == "preferred":
        return f"Using preferred device '{device}' supplied by client request."
    if reason == "manual":
        return f"Manual policy forces device '{device}'."
    if reason == "sticky":
        return f"Sticky policy reusing previously successful device '{device}'."
    if device.startswith("remote:"):
        provider_id = device.split(":", 1)[1]
        entry = REGISTRY.get(provider_id) or {}
        name = entry.get("name", provider_id)
        return f"Auto policy selected remote provider '{name}' for {job_type} workload."
    if device.startswith("cuda:"):
        return f"Auto policy selected local GPU {device} for {job_type} workload."
    return "Falling back to CPU compute."


@router.post("/advise")
async def advise(body: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    body = body or {}
    prefer = body.get("prefer")
    requirements = body.get("requirements")
    job_type = body.get("job_type", "render")

    devices = GPU_MANAGER.list_all(refresh=True)
    choice = GPU_MANAGER.select_device(prefer=prefer, requirements=requirements)
    rationale = _rationale_from_choice(choice, job_type)

    response = {
        "ok": True,
        "choice": choice,
        "policy": GPU_MANAGER.get_policy(),
        "considered": devices,
        "rationale": rationale,
    }
    LOGGER.debug(
        "Compute advice -> device=%s policy=%s reason=%s",
        choice.get("device"),
        choice.get("policy"),
        choice.get("reason"),
    )
    return response


@router.get("/advise")
async def advise_query(
    task: str = Query("img", description="Workload classification (img|tts|export)"),
    size: Optional[str | float] = Query(None, description="Approximate payload size (e.g. 1gb, 512mb)"),
    prefer_remote: bool = Query(False, description="Hint advisor to prefer remote providers"),
    hardware_override: bool = Query(False, description="Force CPU fallback (for debugging)"),
) -> Dict[str, Any]:
    size_mb = _parse_size_mb(size)
    workload = _build_workload_from_query(task, size_mb)
    recommendation = compute_advise(
        GPU_MANAGER,
        workload=workload,
        prefer_remote=prefer_remote,
        hardware_override=hardware_override,
    )
    rationale = recommendation.get("reason") or ""
    choice = recommendation.get("choice")
    summary = f"{choice.upper() if isinstance(choice, str) else choice}: {rationale}" if choice else rationale
    return {
        "ok": True,
        "task": task,
        "size_mb": size_mb,
        "choice": choice,
        "rationale": summary,
        "advice": recommendation,
    }
