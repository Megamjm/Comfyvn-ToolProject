from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from comfyvn.core.content_filter import content_filter
from comfyvn.core.policy_gate import policy_gate
from comfyvn.server.routes.advisory import GateResponse

LOGGER = logging.getLogger("comfyvn.api.policy")
router = APIRouter(prefix="/api/policy", tags=["Advisory/Policy"])


class EvaluateRequest(BaseModel):
    action: str = Field(..., description="Action identifier, e.g. export/import/share")
    override: bool = Field(False, description="User requested override (still logged)")


class FilterPreviewRequest(BaseModel):
    items: List[Dict[str, Any]] = Field(
        default_factory=list, description="Items with `id` and `meta` payloads"
    )
    mode: Optional[str] = Field(
        None, description="Override filter mode for this preview"
    )


@router.get("/status", response_model=GateResponse, summary="Get liability gate status")
def get_status() -> GateResponse:
    status = policy_gate.status()
    message = (
        "Legal acknowledgement required before completing exports."
        if status.requires_ack
        else "Legal acknowledgement recorded; continue responsibly."
    )
    return GateResponse(
        status=status.to_dict(),
        message=message,
        allow_override=status.warn_override_enabled,
    )


@router.post("/evaluate", summary="Evaluate an action against policy gate")
def evaluate(payload: EvaluateRequest = Body(...)) -> Dict[str, Any]:
    result = policy_gate.evaluate_action(payload.action, override=payload.override)
    LOGGER.debug("Policy evaluate action=%s result=%s", payload.action, result)
    return {"ok": True, **result}


@router.get("/filters", summary="Get current content filter mode")
def get_filters(mode: Optional[str] = Query(None)) -> Dict[str, Any]:
    active_mode = mode.lower() if mode else content_filter.mode()
    if mode:
        LOGGER.debug("Filter preview mode override=%s", active_mode)
    return {"ok": True, "mode": active_mode}


@router.post("/filters", summary="Set content filter mode (sfw|warn|unrestricted)")
def set_filters(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    mode = payload.get("mode")
    if not isinstance(mode, str):
        raise HTTPException(status_code=400, detail="mode required")
    try:
        active = content_filter.set_mode(mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "mode": active}


@router.post("/filter-preview", summary="Preview content filtering results")
def filter_preview(payload: FilterPreviewRequest = Body(...)) -> Dict[str, Any]:
    result = content_filter.filter_items(payload.items or [], mode=payload.mode)
    return {"ok": True, **result}
