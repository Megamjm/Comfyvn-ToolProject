from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.config import feature_flags
from comfyvn.perf import budget_manager, perf_profiler

router = APIRouter(prefix="/api/perf", tags=["Performance"])

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------- Validators
def _ensure_budgets_enabled() -> None:
    if feature_flags.is_enabled("enable_perf_budgets", default=False):
        return
    raise HTTPException(status_code=403, detail="enable_perf_budgets flag disabled")


def _ensure_profiler_enabled() -> None:
    if feature_flags.is_enabled("enable_perf_profiler_dashboard", default=False):
        return
    raise HTTPException(
        status_code=403, detail="enable_perf_profiler_dashboard flag disabled"
    )


# -------------------------------------------------------------------------- Models
class BudgetUpdateRequest(BaseModel):
    max_cpu_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    max_mem_mb: int | None = Field(default=None, ge=0)
    max_vram_mb: int | None = Field(default=None, ge=0)
    max_running_jobs: int | None = Field(default=None, ge=0)
    max_queue_depth: int | None = Field(default=None, ge=1)
    lazy_asset_target_mb: int | None = Field(default=None, ge=0)
    evaluation_interval: float | None = Field(default=None, ge=0.1)

    model_config = ConfigDict(extra="forbid")


class JobSubmissionRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=128)
    job_type: str = Field(default="generic", min_length=1, max_length=128)
    payload: Dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class JobFinishRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=128)
    status: str = Field(default="complete")
    reason: str | None = None

    model_config = ConfigDict(extra="allow")


class AssetRegisterRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=256)
    size_mb: float = Field(..., ge=0.0)
    metadata: Dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class AssetTouchRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=256)

    model_config = ConfigDict(extra="forbid")


class AssetEvictRequest(BaseModel):
    target_mb: float = Field(default=256.0, ge=0.0)

    model_config = ConfigDict(extra="forbid")


class ProfilerMarkRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    category: str = Field(default="general", min_length=1, max_length=64)
    metadata: Dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


# ------------------------------------------------------------------------ Budgets
@router.get("/budgets")
async def get_budget_snapshot() -> Dict[str, Any]:
    _ensure_budgets_enabled()
    snapshot = budget_manager.snapshot()
    LOGGER.debug("Budget snapshot requested → %s", snapshot)
    return snapshot


@router.post("/budgets/apply")
async def apply_budget_limits(payload: BudgetUpdateRequest) -> Dict[str, Any]:
    _ensure_budgets_enabled()
    limits = budget_manager.configure(**payload.model_dump(exclude_none=True))
    return {"ok": True, "limits": limits.__dict__}


@router.post("/budgets/jobs/register")
async def register_budgeted_job(payload: JobSubmissionRequest) -> Dict[str, Any]:
    _ensure_budgets_enabled()
    result = budget_manager.register_job(
        payload.job_id,
        kind=payload.job_type,
        payload=(payload.payload or {}),
    )
    return {"ok": True, **result}


@router.post("/budgets/jobs/start")
async def mark_budget_job_started(payload: JobSubmissionRequest) -> Dict[str, Any]:
    _ensure_budgets_enabled()
    record = budget_manager.mark_started(payload.job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"job {payload.job_id} not found")
    return {"ok": True, "job": record.to_public_dict()}


@router.post("/budgets/jobs/finish")
async def mark_budget_job_finished(payload: JobFinishRequest) -> Dict[str, Any]:
    _ensure_budgets_enabled()
    record = budget_manager.mark_finished(
        payload.job_id,
        status=payload.status,
        reason=payload.reason,
    )
    if record is None:
        raise HTTPException(status_code=404, detail=f"job {payload.job_id} not found")
    return {"ok": True, "job": record.to_public_dict()}


@router.post("/budgets/jobs/refresh")
async def refresh_budget_queue() -> Dict[str, Any]:
    _ensure_budgets_enabled()
    transitions = budget_manager.refresh_queue()
    return {"ok": True, "transitions": transitions}


@router.post("/budgets/assets/register")
async def register_lazy_asset(payload: AssetRegisterRequest) -> Dict[str, Any]:
    _ensure_budgets_enabled()
    handle = budget_manager.register_asset(
        payload.asset_id,
        size_mb=payload.size_mb,
        metadata=payload.metadata or {},
        unload_callback=None,
    )
    return {
        "ok": True,
        "asset": {"asset_id": handle.asset_id, "size_mb": handle.size_mb},
    }


@router.post("/budgets/assets/touch")
async def touch_lazy_asset(payload: AssetTouchRequest) -> Dict[str, Any]:
    _ensure_budgets_enabled()
    handle = budget_manager.touch_asset(payload.asset_id)
    if handle is None:
        raise HTTPException(
            status_code=404, detail=f"asset {payload.asset_id} not registered"
        )
    return {
        "ok": True,
        "asset": {"asset_id": handle.asset_id, "last_used": handle.last_used},
    }


@router.post("/budgets/assets/evict")
async def evict_lazy_assets(payload: AssetEvictRequest) -> Dict[str, Any]:
    _ensure_budgets_enabled()
    events = budget_manager.evict_lazy_assets(target_mb=payload.target_mb)
    return {"ok": True, "evicted": events}


# ----------------------------------------------------------------------- Profiler
@router.post("/profiler/mark")
async def profiler_mark(payload: ProfilerMarkRequest) -> Dict[str, Any]:
    _ensure_profiler_enabled()
    entry = perf_profiler.mark(
        payload.name, category=payload.category, metadata=payload.metadata
    )
    return {"ok": True, "mark": entry}


@router.get("/profiler/dashboard")
async def profiler_dashboard(limit: int = 5) -> Dict[str, Any]:
    _ensure_profiler_enabled()
    return {"ok": True, "dashboard": perf_profiler.dashboard(limit=limit)}


@router.post("/profiler/reset")
async def profiler_reset() -> Dict[str, Any]:
    _ensure_profiler_enabled()
    perf_profiler.reset()
    return {"ok": True}


__all__ = ["router"]
