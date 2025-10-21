from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from comfyvn.core.advisory import list_logs, resolve_issue, scan_text

LOGGER = logging.getLogger("comfyvn.api.advisory")
router = APIRouter(prefix="/api/advisory", tags=["Advisory/Policy"])


class AdvisoryScanRequest(BaseModel):
    target_id: str = Field(..., description="Asset, scene, or import identifier")
    text: str = Field("", description="Raw text to scan")
    license_scan: bool = Field(False, description="Enable license heuristic scan")


class AdvisoryScanResponse(BaseModel):
    ok: bool = True
    issues: list[dict]


class AdvisoryResolveRequest(BaseModel):
    issue_id: str = Field(..., description="Issue identifier to resolve")
    notes: Optional[str] = Field(None, description="Optional resolution notes")


@router.post("/scan", response_model=AdvisoryScanResponse, summary="Run advisory scan")
def scan(payload: AdvisoryScanRequest = Body(...)) -> AdvisoryScanResponse:
    LOGGER.debug(
        "Advisory scan request target=%s license_scan=%s",
        payload.target_id,
        payload.license_scan,
    )
    if not payload.text.strip():
        LOGGER.warning(
            "Advisory scan rejected: empty text target=%s", payload.target_id
        )
        raise HTTPException(status_code=400, detail="text must not be empty")

    issues = scan_text(
        payload.target_id,
        payload.text,
        license_scan=payload.license_scan,
    )
    return AdvisoryScanResponse(issues=issues)


@router.get("/logs", summary="List advisory findings")
def logs(resolved: Optional[bool] = Query(None)) -> dict:
    data = list_logs(resolved=resolved)
    LOGGER.debug("Advisory logs fetched count=%s", len(data))
    return {"ok": True, "items": data}


@router.post("/resolve", summary="Resolve an advisory issue")
def resolve(payload: AdvisoryResolveRequest = Body(...)) -> dict:
    updated = resolve_issue(payload.issue_id, payload.notes)
    if not updated:
        LOGGER.warning("Resolve attempt failed issue_id=%s", payload.issue_id)
        raise HTTPException(status_code=404, detail="issue not found")
    return {"ok": True, "issue_id": payload.issue_id}
