from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query
from pydantic import BaseModel, Field

from comfyvn.advisory.license_snapshot import (
    LicenseAcknowledgementRequired,
    LicenseSnapshotError,
    SnapshotResult,
    capture_snapshot,
    record_ack,
    require_ack,
)
from comfyvn.advisory.license_snapshot import (
    status as snapshot_status,
)

router = APIRouter(prefix="/api/advisory/license", tags=["Advisory"])


class SnapshotRequest(BaseModel):
    asset_id: str = Field(
        ..., min_length=1, description="Unique identifier for the asset/model."
    )
    asset_path: Optional[str] = Field(
        default=None,
        description="Filesystem path to the downloaded asset; snapshot stored alongside.",
    )
    snapshot_dir: Optional[str] = Field(
        default=None,
        description="Optional override directory where the snapshot should be written.",
    )
    source_url: Optional[str] = Field(
        default=None, description="URL containing the license/EULA text."
    )
    text: Optional[str] = Field(
        default=None,
        description="Raw license text (when already fetched by the caller).",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata payload stored with the snapshot.",
    )
    user: Optional[str] = Field(
        default=None,
        description="User identifier performing the snapshot (recorded for audit logs).",
    )
    max_bytes: int = Field(
        default=1_000_000,
        ge=4_096,
        le=8_000_000,
        description="Guardrail for the maximum license payload size fetched from source_url.",
    )


class SnapshotResponse(BaseModel):
    ok: bool = Field(True, description="Flag indicating the snapshot completed.")
    asset_id: str
    hash: str
    captured_at: str
    snapshot_path: str
    requires_ack: bool
    acknowledgements: Dict[str, Any]
    text: str
    source_url: Optional[str]
    metadata: Dict[str, Any]


class AckRequest(BaseModel):
    asset_id: str = Field(
        ..., min_length=1, description="Asset identifier to acknowledge."
    )
    user: str = Field(
        default="anonymous",
        min_length=1,
        description="User recording the acknowledgement.",
    )
    asset_path: Optional[str] = Field(
        default=None,
        description="Optional filesystem path stored with the acknowledgement.",
    )
    source_url: Optional[str] = Field(
        default=None,
        description="Optional override for the license source URL (defaults to snapshot source).",
    )
    hash: Optional[str] = Field(
        default=None,
        description="Optional snapshot hash to guard against stale acknowledgements.",
    )
    notes: Optional[str] = Field(
        default=None, description="Optional notes recorded with the acknowledgement."
    )
    provenance: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional provenance payload persisted with the acknowledgement.",
    )


class AckResponse(BaseModel):
    ok: bool = Field(True, description=" acknowledgement persisted successfully.")
    asset_id: str
    hash: str | None
    requires_ack: bool
    acknowledgements: Dict[str, Any]
    snapshot_path: Optional[str]
    source_url: Optional[str]
    captured_at: Optional[str]


@router.post(
    "/snapshot",
    response_model=SnapshotResponse,
    summary="Capture or refresh a license snapshot for an asset.",
)
def create_snapshot(payload: SnapshotRequest = Body(...)) -> SnapshotResponse:
    try:
        result: SnapshotResult = capture_snapshot(
            payload.asset_id,
            asset_path=payload.asset_path,
            snapshot_dir=payload.snapshot_dir,
            source_url=payload.source_url,
            text=payload.text,
            metadata=payload.metadata,
            user=payload.user,
            max_bytes=payload.max_bytes,
        )
    except LicenseSnapshotError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = asdict(result)
    data["ok"] = True
    return SnapshotResponse(**data)


@router.post(
    "/ack",
    response_model=AckResponse,
    summary="Record a user acknowledgement for a captured license snapshot.",
)
def acknowledge(payload: AckRequest = Body(...)) -> AckResponse:
    try:
        status_payload = record_ack(
            payload.asset_id,
            user=payload.user,
            asset_path=payload.asset_path,
            source_url=payload.source_url,
            hash_value=payload.hash,
            notes=payload.notes,
            provenance=payload.provenance,
        )
    except LicenseSnapshotError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AckResponse(
        ok=True,
        asset_id=payload.asset_id,
        hash=status_payload.get("hash"),
        requires_ack=bool(status_payload.get("requires_ack")),
        acknowledgements=status_payload.get("acknowledgements") or {},
        snapshot_path=status_payload.get("snapshot_path"),
        source_url=status_payload.get("source_url"),
        captured_at=status_payload.get("captured_at"),
    )


@router.get(
    "/{asset_id}",
    summary="Inspect the acknowledgement status for a stored license snapshot.",
)
def inspect_status(
    asset_id: str = Path(..., description="Asset identifier."),
    include_text: bool = Query(
        False, description="Include the normalized license text in the response."
    ),
) -> Dict[str, Any]:
    try:
        status_payload = snapshot_status(asset_id, include_text=include_text)
    except LicenseSnapshotError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    status_payload.update({"ok": True})
    return status_payload


@router.post(
    "/require",
    summary="Verify an acknowledgement exists for the supplied asset snapshot.",
)
def ensure_ack(
    payload: Dict[str, Any] = Body(
        default_factory=dict,
        description="Payload containing asset_id and optional hash guard.",
    )
) -> Dict[str, Any]:
    asset_id = str(payload.get("asset_id") or "").strip()
    if not asset_id:
        raise HTTPException(status_code=400, detail="asset_id required")
    hash_value = payload.get("hash")
    if hash_value is not None:
        hash_value = str(hash_value)
    try:
        info = require_ack(asset_id, hash_value=hash_value)
    except LicenseAcknowledgementRequired as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except LicenseSnapshotError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    response = dict(info)
    response["ok"] = True
    response["acknowledged"] = True
    return response
