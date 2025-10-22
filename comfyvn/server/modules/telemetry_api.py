from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from comfyvn.config import feature_flags
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


def _feature_flag_enabled() -> bool:
    if feature_flags.is_enabled("enable_observability", default=False):
        return True
    return feature_flags.is_enabled("enable_privacy_telemetry", default=False)


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


class OptInPayload(BaseModel):
    crash: bool = Field(
        default=False, description="Also enable crash uploads when opting in."
    )
    diagnostics: bool = Field(
        default=False, description="Also enable diagnostics bundle exports."
    )
    dry_run: bool = Field(
        default=False,
        description="Retain dry-run mode (true keeps events local only).",
    )


@router.get("/summary")
def telemetry_summary(request: Request):
    telemetry = _telemetry(request)
    summary = telemetry.summary(include_events=False)
    summary["feature_flag"] = _feature_flag_enabled()
    return summary


@router.get("/health")
def telemetry_health(request: Request):
    telemetry = _telemetry(request)
    health = telemetry.health()
    return {"ok": True, **health, "feature_flag": _feature_flag_enabled()}


@router.get("/settings")
def telemetry_settings(request: Request):
    telemetry = _telemetry(request)
    settings = telemetry.settings.to_dict()
    return {
        "settings": settings,
        "telemetry_active": telemetry.telemetry_allowed(),
        "crash_uploads_active": telemetry.crash_uploads_allowed(),
        "diagnostics_opt_in": bool(settings.get("diagnostics_opt_in", False)),
        "diagnostics_active": telemetry.diagnostics_allowed(),
        "health": telemetry.health(),
        "feature_flag": _feature_flag_enabled(),
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
        "diagnostics_opt_in": bool(updated.diagnostics_opt_in),
        "diagnostics_active": telemetry.diagnostics_allowed(),
        "health": telemetry.health(),
        "feature_flag": _feature_flag_enabled(),
    }


@router.post("/opt_in")
def telemetry_opt_in(request: Request, payload: OptInPayload | None = None):
    telemetry = _telemetry(request)
    data = payload or OptInPayload()
    updated = telemetry.update_settings(
        telemetry_opt_in=True,
        crash_opt_in=data.crash,
        diagnostics_opt_in=data.diagnostics,
        dry_run=data.dry_run,
    )
    return {
        "ok": True,
        "settings": updated.to_dict(),
        "telemetry_active": telemetry.telemetry_allowed(),
        "crash_uploads_active": telemetry.crash_uploads_allowed(),
        "diagnostics_active": telemetry.diagnostics_allowed(),
        "health": telemetry.health(),
        "feature_flag": _feature_flag_enabled(),
    }


@router.post("/features")
def record_feature(request: Request, payload: FeatureEvent):
    telemetry = _telemetry(request)
    recorded = telemetry.record_feature(payload.feature, variant=payload.variant)
    return {
        "ok": True,
        "recorded": recorded,
        "telemetry_active": telemetry.telemetry_allowed(),
        "feature_flag": _feature_flag_enabled(),
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
        "feature_flag": _feature_flag_enabled(),
    }


@router.get("/events")
def list_events(request: Request, limit: int = Query(20, ge=1, le=200)):
    telemetry = _telemetry(request)
    summary = telemetry.summary(include_events=True)
    events = summary.get("events", [])
    return {"events": events[-limit:], "feature_flag": _feature_flag_enabled()}


@router.get("/hooks")
def list_hook_counts(request: Request):
    telemetry = _telemetry(request)
    return {
        "hooks": telemetry.summary().get("hooks", {}),
        "feature_flag": _feature_flag_enabled(),
    }


@router.get("/crashes")
def list_crashes(request: Request):
    telemetry = _telemetry(request)
    snapshot = telemetry.summary()
    return {
        "crashes": snapshot.get("crashes", []),
        "feature_flag": _feature_flag_enabled(),
    }


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
