from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from comfyvn.obs.telemetry import TelemetrySettings, get_telemetry

router = APIRouter(prefix="/api/telemetry", tags=["Telemetry"])


def _telemetry(request: Request):
    telemetry = getattr(request.app.state, "telemetry", None)
    if telemetry is None:
        telemetry = get_telemetry(
            app_version=getattr(request.app.state, "version", None)
        )
        request.app.state.telemetry = telemetry
    return telemetry


class FeatureEvent(BaseModel):
    feature: str = Field(..., description="Feature identifier to increment.")
    variant: Optional[str] = Field(
        None, description="Optional variant or mode for the feature."
    )


class TelemetryEvent(BaseModel):
    event: str = Field(..., description="Event name to record.")
    payload: Dict[str, Any] | None = Field(
        default=None, description="Additional structured metadata."
    )
    category: str | None = Field(
        default="custom", description="Optional category bucket."
    )


class ConsentPayload(BaseModel):
    telemetry_opt_in: Optional[bool] = Field(
        default=None, description="Enable minimal telemetry aggregation."
    )
    crash_opt_in: Optional[bool] = Field(
        default=None, description="Allow crash report uploads/diagnostics."
    )
    diagnostics_opt_in: Optional[bool] = Field(
        default=None, description="Allow diagnostics bundle exports."
    )
    dry_run: Optional[bool] = Field(
        default=None,
        description="Keep telemetry in dry-run mode (never sends external requests).",
    )


@router.get("/summary")
def telemetry_summary(request: Request):
    telemetry = _telemetry(request)
    return telemetry.summary(include_events=False)


@router.get("/settings")
def telemetry_settings(request: Request):
    telemetry = _telemetry(request)
    settings = telemetry.settings.to_dict()
    return {
        "settings": settings,
        "telemetry_active": telemetry.telemetry_allowed(),
        "crash_uploads_active": telemetry.crash_uploads_allowed(),
        "diagnostics_opt_in": telemetry.diagnostics_allowed(),
    }


@router.post("/settings")
def update_settings(request: Request, payload: ConsentPayload):
    telemetry = _telemetry(request)
    updated: TelemetrySettings = telemetry.update_settings(
        telemetry_opt_in=payload.telemetry_opt_in,
        crash_opt_in=payload.crash_opt_in,
        diagnostics_opt_in=payload.diagnostics_opt_in,
        dry_run=payload.dry_run,
    )
    return {
        "settings": updated.to_dict(),
        "telemetry_active": telemetry.telemetry_allowed(),
        "crash_uploads_active": telemetry.crash_uploads_allowed(),
        "diagnostics_opt_in": telemetry.diagnostics_allowed(),
    }


@router.post("/features")
def record_feature(request: Request, payload: FeatureEvent):
    telemetry = _telemetry(request)
    recorded = telemetry.record_feature(payload.feature, variant=payload.variant)
    return {
        "ok": True,
        "recorded": recorded,
        "telemetry_active": telemetry.telemetry_allowed(),
    }


@router.post("/events")
def record_event(request: Request, payload: TelemetryEvent):
    telemetry = _telemetry(request)
    recorded = telemetry.record_event(
        payload.event,
        payload=payload.payload or {},
        category=payload.category or "custom",
    )
    return {
        "ok": True,
        "recorded": recorded,
        "telemetry_active": telemetry.telemetry_allowed(),
    }


@router.get("/events")
def list_events(request: Request, limit: int = Query(20, ge=1, le=200)):
    telemetry = _telemetry(request)
    summary = telemetry.summary(include_events=True)
    events = summary.get("events", [])
    return {"events": events[-limit:]}


@router.get("/hooks")
def list_hook_counts(request: Request):
    telemetry = _telemetry(request)
    return {"hooks": telemetry.summary().get("hooks", {})}


@router.get("/crashes")
def list_crashes(request: Request):
    telemetry = _telemetry(request)
    snapshot = telemetry.summary()
    return {"crashes": snapshot.get("crashes", [])}


@router.get("/diagnostics")
def export_diagnostics(request: Request):
    telemetry = _telemetry(request)
    if not telemetry.diagnostics_allowed():
        raise HTTPException(
            status_code=403,
            detail="Diagnostics export requires opt-in (see /api/telemetry/settings).",
        )
    bundle = telemetry.export_bundle()
    return FileResponse(
        bundle,
        filename=bundle.name,
        media_type="application/zip",
    )
