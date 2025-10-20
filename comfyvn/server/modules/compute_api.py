from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body

from comfyvn.core.compute_registry import get_provider_registry
from comfyvn.core.gpu_manager import get_gpu_manager

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/compute", tags=["Compute Advisor"])
GPU_MANAGER = get_gpu_manager()
REGISTRY = get_provider_registry()


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
