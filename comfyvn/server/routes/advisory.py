from __future__ import annotations

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from comfyvn.advisory.policy import gate_status, set_ack


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


router = APIRouter(prefix="/api/policy", tags=["Advisory"])


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


@router.get("/ack", response_model=GateResponse, summary="Read acknowledgement status")
def read_ack() -> GateResponse:
    return _status_response()


@router.post(
    "/ack",
    response_model=GateResponse,
    summary="Persist acknowledgement for liability gate",
)
def write_ack(payload: AckRequest = Body(...)) -> GateResponse:
    set_ack(True, user=payload.user, notes=payload.notes)
    return _status_response("Acknowledgement recorded. Proceed with caution.")
