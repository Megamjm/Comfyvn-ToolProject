from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.advisory.policy import (
    gate_status,
    get_ack_record,
    require_ack_or_raise,
    set_ack,
)
from comfyvn.config import feature_flags
from comfyvn.policy.enforcer import policy_enforcer


class AckRequest(BaseModel):
    user: str = Field("anonymous", description="User acknowledging the policy")
    name: str | None = Field(
        None, description="Display name recorded with the acknowledgement"
    )
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


class GateResponse(BaseModel):
    ack: bool
    status: Dict[str, Any] = Field(default_factory=dict)
    name: str | None = None
    at: float | None = None
    message: str | None = None
    allow_override: bool = False

    model_config = ConfigDict(extra="ignore")


policy_router = APIRouter(prefix="/api/policy", tags=["Advisory"])
advisory_router = APIRouter(prefix="/api/advisory", tags=["Advisory"])
router = APIRouter(tags=["Advisory"])
router.include_router(policy_router)
router.include_router(advisory_router)


def _ack_payload(message: Optional[str] = None) -> GateResponse:
    status = gate_status()
    record = get_ack_record()
    detail = message or (
        "Legal acknowledgement required before completing exports."
        if status.requires_ack
        else "Legal acknowledgement recorded; proceed responsibly."
    )
    return GateResponse(
        ack=bool(record.get("ack")),
        name=record.get("name"),
        at=record.get("at"),
        status=status.to_dict(),
        allow_override=status.warn_override_enabled,
        message=detail,
    )


@policy_router.get("/ack", summary="Read acknowledgement status")
def read_ack() -> GateResponse:
    """Return the persisted acknowledgement flag and gate metadata."""
    return _ack_payload()


@policy_router.post(
    "/ack",
    summary="Persist acknowledgement for liability gate",
)
def write_ack(payload: AckRequest = Body(...)) -> GateResponse:
    set_ack(True, user=payload.user, name=payload.name, notes=payload.notes)
    return _ack_payload("Acknowledgement recorded. Proceed with caution.")


@policy_router.delete(
    "/ack",
    summary="Clear acknowledgement (development/testing only)",
)
def clear_ack() -> GateResponse:
    set_ack(False, user="system", notes="cleared via API")
    return _ack_payload("Acknowledgement cleared.")


@advisory_router.post(
    "/scan",
    summary="Evaluate a bundle payload with advisory scanners and policy gate",
)
def scan_bundle(payload: ScanRequest = Body(...)) -> Dict[str, Any]:
    if not feature_flags.is_enabled("enable_advisory", default=False):
        raise HTTPException(status_code=403, detail="enable_advisory disabled")

    action = payload.action or "export.bundle.preview"
    bundle = payload.bundle or {}

    try:
        require_ack_or_raise(action, override=payload.override)
    except PermissionError as exc:
        raise HTTPException(
            status_code=423,
            detail={"message": str(exc), "gate": gate_status().to_dict()},
        ) from exc

    result = policy_enforcer.enforce(
        action,
        bundle,
        override=payload.override,
        source=payload.source or "api.advisory.scan",
    ).to_dict()

    status = gate_status()
    ack_record = get_ack_record()

    response: Dict[str, Any] = {
        "allow": result.get("allow", False),
        "gate": result.get("gate") or {},
        "counts": result.get("counts") or {},
        "findings": result.get("findings") or [],
        "warnings": result.get("warnings") or [],
        "blocked": result.get("blocked") or [],
        "info": result.get("info") or [],
        "log_path": result.get("log_path"),
        "status": status.to_dict(),
        "ack": bool(ack_record.get("ack")),
        "ack_detail": ack_record,
    }
    if payload.include_debug:
        response["bundle"] = result.get("bundle") or {}
        response["source"] = result.get("source")

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

    response["ok"] = True
    return response
