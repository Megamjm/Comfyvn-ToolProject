from __future__ import annotations

"""
FastAPI routes exposing the Civitai public provider (Phase-7).

Endpoints stay dry-run only: search/metadata return normalized payloads while
download produces a gated plan that documents requirements for the eventual
Phase-7 license enforcer.
"""

from typing import Any, Dict, Optional, Sequence

from fastapi import APIRouter, Body, HTTPException, Query

from comfyvn.config import feature_flags
from comfyvn.public_providers import civitai

router = APIRouter(
    prefix="/api/providers/civitai",
    tags=["Public Model Hubs"],
)


def _feature_context() -> Dict[str, Any]:
    enabled = feature_flags.is_enabled(civitai.FEATURE_FLAG)
    return {"flag": civitai.FEATURE_FLAG, "enabled": enabled}


def _model_types_param(types: Sequence[str] | None) -> Sequence[str] | None:
    if not types:
        return None
    filtered = [item for item in types if isinstance(item, str) and item.strip()]
    return tuple(dict.fromkeys(filtered)) or None


@router.get("/health")
async def civitai_health() -> Dict[str, Any]:
    payload = civitai.health()
    payload["feature"] = _feature_context()
    return payload


@router.get("/search")
async def civitai_search(
    query: str = Query(
        ...,
        alias="q",
        description="Search query. Matches model name, tags, and description.",
        min_length=1,
    ),
    limit: int = Query(
        civitai.DEFAULT_LIMIT,
        ge=1,
        le=civitai.MAX_LIMIT,
        description="Maximum number of results (Civitai caps at 50).",
    ),
    model_types: Optional[Sequence[str]] = Query(
        None,
        alias="type",
        description="Optional Civitai model types (e.g. Checkpoint, LORA, TextualInversion).",
    ),
    include_nsfw: bool = Query(
        False,
        alias="nsfw",
        description="Return NSFW-tagged models when true.",
    ),
) -> Dict[str, Any]:
    try:
        result = civitai.search_models(
            query=query,
            limit=limit,
            model_types=_model_types_param(model_types),
            allow_nsfw=include_nsfw,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except civitai.CivitaiError as exc:
        status = getattr(exc, "status_code", None) or 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    result["feature"] = _feature_context()
    return result


@router.get("/metadata/{model_id}")
async def civitai_metadata(
    model_id: int,
    version_id: Optional[int] = Query(
        None,
        alias="version",
        description="Optional version id to prioritise when summarising files.",
    ),
) -> Dict[str, Any]:
    try:
        result = civitai.fetch_metadata(model_id, version_id=version_id)
    except civitai.CivitaiError as exc:
        status = getattr(exc, "status_code", None) or 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    result["feature"] = _feature_context()
    result["download_requires_ack"] = True
    return result


def _coerce_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


@router.post("/download")
async def civitai_download_plan(
    payload: Dict[str, Any] = Body(
        ...,
        description=(
            "Dry-run download planner. Requires license acknowledgement and "
            "sufficient storage quota before a real download will be enabled."
        ),
    )
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")

    feature = _feature_context()
    ack = bool(
        payload.get("license_ack")
        or payload.get("accept_license")
        or payload.get("acknowledged")
    )
    if not ack:
        raise HTTPException(
            status_code=412,
            detail={
                "reason": "license_ack_required",
                "terms_url": civitai.TERMS_URL,
                "feature": feature,
            },
        )

    model_id_value = payload.get("model_id") or payload.get("id")
    if model_id_value is None:
        raise HTTPException(status_code=400, detail="model_id is required")
    try:
        model_id = int(model_id_value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="model_id must be an integer"
        ) from exc

    version_hint = payload.get("version_id") or payload.get("version")
    version_id = None
    if version_hint is not None:
        try:
            version_id = int(version_hint)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail="version_id must be an integer"
            ) from exc

    try:
        plan = civitai.plan_download(model_id, version_id=version_id)
    except civitai.CivitaiError as exc:
        status = getattr(exc, "status_code", None) or 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    required_mb = plan.get("total_size_mb")
    available_mb = (
        payload.get("available_mb")
        or payload.get("quota_mb")
        or payload.get("storage_available_mb")
    )
    available_numeric = _coerce_float(available_mb)
    required_numeric = _coerce_float(required_mb)

    quota_ok = True
    if available_numeric is not None and required_numeric is not None:
        quota_ok = available_numeric >= required_numeric

    plan.update(
        {
            "feature": feature,
            "acknowledged": True,
            "dry_run": True,
            "download_allowed": False,
            "license_ack_required": True,
            "quota": {
                "available_mb": available_numeric,
                "required_mb": required_numeric,
                "ok": quota_ok,
            },
            "ok": False,
            "reason": None,
        }
    )

    if not quota_ok:
        plan["reason"] = "insufficient_storage_quota"
        return plan

    if not feature["enabled"]:
        plan["reason"] = "feature_disabled"
        return plan

    plan["reason"] = "phase7_download_gate_active"
    return plan


__all__ = ["router"]
