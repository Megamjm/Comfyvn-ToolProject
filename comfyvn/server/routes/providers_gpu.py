from __future__ import annotations

"""
Public GPU provider metadata + dry-run helpers.
"""

from typing import Any, Dict, Mapping

from fastapi import APIRouter, Body

from comfyvn.config import feature_flags
from comfyvn.public_providers import catalog, gpu_runpod

router = APIRouter(prefix="/api/providers/gpu/public", tags=["GPU Providers (public)"])

FEATURE_FLAG = "enable_public_gpu"


def _feature_context() -> Dict[str, Any]:
    enabled = feature_flags.is_enabled(FEATURE_FLAG)
    return {"feature": FEATURE_FLAG, "enabled": enabled}


@router.get("/catalog", summary="List public GPU providers + pricing heuristics")
async def gpu_catalog() -> Dict[str, Any]:
    return {
        "ok": True,
        "feature": _feature_context(),
        "providers": catalog.catalog_for("gpu_backends"),
    }


@router.post("/runpod/health", summary="Dry-run RunPod credential check")
async def runpod_health(
    payload: Mapping[str, Any] | None = Body(None)
) -> Dict[str, Any]:
    cfg = {}
    if isinstance(payload, Mapping):
        raw_cfg = payload.get("config") or payload.get("cfg")
        if isinstance(raw_cfg, Mapping):
            cfg = dict(raw_cfg)
    status = gpu_runpod.health(cfg)
    status.setdefault("provider", "runpod")
    status.setdefault("feature", _feature_context())
    if not status.get("dry_run"):
        status["dry_run"] = True
    if not status["feature"]["enabled"]:
        status.setdefault("ok", False)
        status.setdefault("reason", "feature disabled")
    return status


@router.post("/runpod/submit", summary="Dry-run RunPod job submission")
async def runpod_submit(
    payload: Mapping[str, Any] = Body(default_factory=dict)
) -> Dict[str, Any]:
    cfg = {}
    job = {}
    if isinstance(payload, Mapping):
        raw_cfg = payload.get("config") or payload.get("cfg")
        if isinstance(raw_cfg, Mapping):
            cfg = dict(raw_cfg)
        raw_job = payload.get("job") or payload.get("payload")
        if isinstance(raw_job, Mapping):
            job = dict(raw_job)
    result = gpu_runpod.submit(job, cfg)
    result.setdefault("provider", "runpod")
    result.setdefault("feature", _feature_context())
    if not result["feature"]["enabled"]:
        result.setdefault("ok", False)
        result.setdefault("reason", "feature disabled")
    return result


@router.post("/runpod/poll", summary="Dry-run RunPod job polling")
async def runpod_poll(
    payload: Mapping[str, Any] = Body(default_factory=dict)
) -> Dict[str, Any]:
    job_id = ""
    cfg = {}
    if isinstance(payload, Mapping):
        raw_job_id = payload.get("job_id") or payload.get("id")
        if isinstance(raw_job_id, str):
            job_id = raw_job_id
        raw_cfg = payload.get("config") or payload.get("cfg")
        if isinstance(raw_cfg, Mapping):
            cfg = dict(raw_cfg)
    status = gpu_runpod.poll(job_id or "mock-runpod-1", cfg)
    status.setdefault("provider", "runpod")
    status.setdefault("feature", _feature_context())
    if not status["feature"]["enabled"]:
        status.setdefault("ok", False)
        status.setdefault("reason", "feature disabled")
    return status


__all__ = ["router"]
