from __future__ import annotations

"""
Rating API surfaces used by reviewer tooling and automation.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query
from pydantic import BaseModel, Field

from comfyvn.config import feature_flags
from comfyvn.rating import rating_service

LOGGER = logging.getLogger("comfyvn.api.rating")

router = APIRouter(prefix="/api/rating", tags=["Rating"])


class ClassifyRequest(BaseModel):
    item_id: str = Field(..., description="Stable identifier for the asset or prompt.")
    payload: Optional[Dict[str, Any]] = Field(
        None, description="Metadata payload (text, tags, meta) to score."
    )
    mode: Optional[str] = Field(
        "sfw",
        description="Filter mode (sfw|warn|unrestricted). Defaults to SFW.",
    )
    acknowledged: bool = Field(
        False,
        description="Set to true when the caller already acknowledged an earlier risk prompt.",
    )
    action: Optional[str] = Field(
        "generic",
        description="Action name used in audit logs (e.g. export.renpy, prompt.generate).",
    )
    ack_token: Optional[str] = Field(
        None,
        description="Previously issued acknowledgement token to verify.",
    )


class OverrideRequest(BaseModel):
    item_id: str = Field(..., description="Target identifier to override.")
    rating: str = Field(..., description="Rating bucket (E|T|M|Adult).")
    reviewer: str = Field(
        ...,
        description="Reviewer or moderator applying the override.",
        min_length=1,
    )
    reason: str = Field(
        ...,
        description="Short justification for the override decision.",
        min_length=3,
    )
    scope: Optional[str] = Field(
        "asset",
        description="Scope context (asset|prompt|export).",
    )


class AckRequest(BaseModel):
    token: str = Field(..., description="Ack token issued by /classify.")
    user: str = Field(..., description="User acknowledging the risk.")
    notes: Optional[str] = Field(
        None, description="Optional reviewer notes stored alongside the ack."
    )


@router.get("/matrix", summary="Get rating keyword matrix")
def get_matrix() -> Dict[str, Any]:
    _ensure_enabled()
    service = rating_service()
    matrix = service.matrix()
    return {
        "ok": True,
        "matrix": matrix,
        "order": list(matrix.keys()),
    }


@router.post("/classify", summary="Classify an item and evaluate SFW gating")
def classify(payload: ClassifyRequest = Body(...)) -> Dict[str, Any]:
    _ensure_enabled()
    service = rating_service()
    result = service.evaluate(
        payload.item_id,
        payload.payload,
        mode=payload.mode or "sfw",
        acknowledged=payload.acknowledged,
        action=payload.action or "generic",
        ack_token=payload.ack_token,
    )
    LOGGER.debug(
        "Rating classify item=%s rating=%s allowed=%s ack_required=%s",
        payload.item_id,
        result["rating"]["rating"],
        result["allowed"],
        result["requires_ack"],
    )
    return result


@router.get("/overrides", summary="List reviewer overrides")
def list_overrides(limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
    _ensure_enabled()
    service = rating_service()
    overrides = service.list_overrides()
    if limit < len(overrides):
        overrides = overrides[:limit]
    return {"ok": True, "items": overrides}


@router.post("/overrides", summary="Set or update a manual rating override")
def set_override(payload: OverrideRequest = Body(...)) -> Dict[str, Any]:
    _ensure_enabled()
    service = rating_service()
    try:
        result = service.put_override(
            payload.item_id,
            payload.rating,
            payload.reviewer,
            payload.reason,
            scope=payload.scope or "asset",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    LOGGER.info(
        "Rating override via API item=%s rating=%s reviewer=%s",
        payload.item_id,
        payload.rating,
        payload.reviewer,
    )
    return {"ok": True, "item": result.to_dict()}


@router.delete("/overrides/{item_id}", summary="Remove a manual rating override")
def delete_override(
    item_id: str = Path(..., description="Item identifier to clear.")
) -> Dict[str, Any]:
    _ensure_enabled()
    service = rating_service()
    removed = service.delete_override(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="override not found")
    return {"ok": True, "item_id": item_id}


@router.post("/ack", summary="Acknowledge a risk token issued by /classify")
def acknowledge(payload: AckRequest = Body(...)) -> Dict[str, Any]:
    _ensure_enabled()
    service = rating_service()
    try:
        entry = service.acknowledge(payload.token, payload.user, payload.notes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "ack": entry}


@router.get("/acks", summary="List acknowledgement audit entries")
def list_acks(limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
    _ensure_enabled()
    service = rating_service()
    entries = service.list_acks()
    if limit < len(entries):
        entries = entries[:limit]
    return {"ok": True, "items": entries}


def _ensure_enabled() -> None:
    if not feature_flags.is_enabled("enable_rating_api"):
        raise HTTPException(
            status_code=403,
            detail={"feature": "enable_rating_api", "message": "rating API disabled"},
        )
