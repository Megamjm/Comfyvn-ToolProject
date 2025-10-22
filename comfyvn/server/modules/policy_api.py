from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from comfyvn.core.content_filter import content_filter
from comfyvn.core.policy_gate import policy_gate
from comfyvn.policy.audit import policy_audit
from comfyvn.policy.enforcer import policy_enforcer
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


class EnforceRequest(BaseModel):
    action: str = Field(..., description="Action identifier (e.g. export.bundle)")
    bundle: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional advisory bundle payload (scenes/assets/licenses) to evaluate.",
    )
    override: bool = Field(
        False,
        description="Pass-through override flag for policy gate (still logged).",
    )
    source: Optional[str] = Field(
        None,
        description="Override source descriptor for audit timeline entries.",
    )


class AuditResponse(BaseModel):
    ok: bool = True
    events: List[Dict[str, Any]]
    summary: Dict[str, Any]
    report: Optional[Dict[str, Any]] = None


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


@router.post(
    "/enforce",
    summary="Evaluate bundle against policy enforcement rules",
    response_model=Dict[str, Any],
)
def enforce(payload: EnforceRequest = Body(...)) -> Dict[str, Any]:
    result = policy_enforcer.enforce(
        payload.action,
        payload.bundle or {},
        override=payload.override,
        source=payload.source,
    ).to_dict()
    if not result.get("allow", False):
        raise HTTPException(
            status_code=423,
            detail={
                "message": "policy enforcement blocked",
                "result": result,
            },
        )
    return {"ok": True, "result": result}


@router.get(
    "/audit",
    summary="List recent policy enforcement events",
    response_model=AuditResponse,
)
def audit(
    limit: int = Query(50, ge=1, le=500, description="Maximum events to return."),
    action: Optional[str] = Query(
        None, description="Filter to a specific policy action identifier."
    ),
    export: bool = Query(
        False,
        description="When true, persist a JSON report and include the file path.",
    ),
) -> AuditResponse:
    events = policy_audit.list_events(limit=limit, action=action)
    summary = policy_audit.summary()
    report_payload: Optional[Dict[str, Any]] = None
    if export:
        report_path = policy_audit.export_report()
        report_payload = {"path": report_path.as_posix()}
    return AuditResponse(events=events, summary=summary, report=report_payload)
