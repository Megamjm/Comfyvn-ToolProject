from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from comfyvn.advisory.policy import gate_status, set_ack
from comfyvn.config import feature_flags
from comfyvn.policy.enforcer import policy_enforcer


class GateResponse(BaseModel):
    ok: bool = True
    status: dict
    message: str
    allow_override: bool


class AckRequest(BaseModel):
    user: str = Field("anonymous", description="User acknowledging the policy")
    notes: str | None = Field(
        None, description="Optional acknowledgement notes stored with the status"
    )


class ScanRequest(BaseModel):
    action: str = Field(
        "export.bundle.preview",
        description="Action identifier evaluated against the policy gate.",
    )
    bundle: Dict[str, Any] = Field(
        default_factory=dict,
        description="Bundle payload (scenes/assets/licenses) for advisory scanning.",
    )
    override: bool = Field(
        False,
        description="Set to true to request a policy override (still recorded).",
    )
    source: Optional[str] = Field(
        None,
        description="Optional override for the enforcement source descriptor.",
    )
    include_debug: bool = Field(
        False,
        description="Include diagnostic bundle metadata and log path in the response.",
    )


class ScanResponse(BaseModel):
    ok: bool = True
    allow: bool
    gate: Dict[str, Any]
    counts: Dict[str, int]
    findings: list[Dict[str, Any]]
    warnings: list[Dict[str, Any]]
    blocked: list[Dict[str, Any]]
    info: list[Dict[str, Any]]
    status: Dict[str, Any]
    log_path: Optional[str] = None
    bundle: Optional[Dict[str, Any]] = None
    source: Optional[str] = None


policy_router = APIRouter(prefix="/api/policy", tags=["Advisory"])
advisory_router = APIRouter(prefix="/api/advisory", tags=["Advisory"])
router = APIRouter(tags=["Advisory"])
router.include_router(policy_router)
router.include_router(advisory_router)


def _status_response(message: str | None = None) -> GateResponse:
    status = gate_status()
    default_message = (
        "Legal acknowledgement required before completing exports."
        if status.requires_ack
        else "Legal acknowledgement recorded; proceed responsibly."
    )
    return GateResponse(
        status=status.to_dict(),
        message=message or default_message,
        allow_override=status.warn_override_enabled,
    )


@policy_router.get(
    "/ack", response_model=GateResponse, summary="Read acknowledgement status"
)
def read_ack() -> GateResponse:
    return _status_response()


@policy_router.post(
    "/ack",
    response_model=GateResponse,
    summary="Persist acknowledgement for liability gate",
)
def write_ack(payload: AckRequest = Body(...)) -> GateResponse:
    set_ack(True, user=payload.user, notes=payload.notes)
    return _status_response("Acknowledgement recorded. Proceed with caution.")


@advisory_router.post(
    "/scan",
    response_model=ScanResponse,
    summary="Evaluate a bundle payload with advisory scanners and policy gate",
)
def scan_bundle(payload: ScanRequest = Body(...)) -> ScanResponse:
    if not feature_flags.is_enabled("enable_advisory", default=False):
        raise HTTPException(status_code=403, detail="enable_advisory disabled")

    action = payload.action or "export.bundle.preview"
    bundle = payload.bundle or {}
    result = policy_enforcer.enforce(
        action,
        bundle,
        override=payload.override,
        source=payload.source or "api.advisory.scan",
    ).to_dict()

    response = ScanResponse(
        allow=result.get("allow", False),
        gate=result.get("gate") or {},
        counts=result.get("counts") or {},
        findings=result.get("findings") or [],
        warnings=result.get("warnings") or [],
        blocked=result.get("blocked") or [],
        info=result.get("info") or [],
        status=gate_status().to_dict(),
        log_path=result.get("log_path"),
    )
    if payload.include_debug:
        response.bundle = result.get("bundle") or {}
        response.source = result.get("source")

    if not result.get("allow", False):
        gate = result.get("gate") or {}
        message = (
            "Policy acknowledgement required before running this action."
            if gate.get("requires_ack")
            else "Advisory findings blocked the requested action."
        )
        raise HTTPException(
            status_code=423,
            detail={
                "message": message,
                "result": result,
            },
        )

    return response
