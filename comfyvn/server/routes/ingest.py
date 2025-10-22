from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.config import feature_flags
from comfyvn.core import modder_hooks
from comfyvn.core.modder_hooks import HookSpec
from comfyvn.ingest.queue import (
    AssetIngestQueue,
    IngestError,
    RateLimitExceeded,
    get_ingest_queue,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["Asset Ingest"])


class QueueRequest(BaseModel):
    provider: str = Field(
        default="furaffinity", description="Source provider identifier."
    )
    metadata: Dict[str, Any] | None = Field(
        default=None, description="Raw provider metadata payload."
    )
    source_path: str | None = Field(
        default=None,
        description="Local filesystem path to stage. Required for FurAffinity uploads.",
    )
    remote_url: str | None = Field(
        default=None,
        description="Remote URL for optional pulls (Civitai/HuggingFace when terms acked).",
    )
    dest_relative: str | None = Field(
        default=None,
        description="Optional relative path under the asset registry root.",
    )
    asset_type: str | None = Field(
        default=None,
        description="Optional asset bucket override (e.g. portraits, audio).",
    )
    pin: bool = Field(
        default=True, description="Keep the staged artefact pinned in the dedup cache."
    )
    terms_acknowledged: bool | None = Field(
        default=None,
        description="Set to true when provider terms for remote pulls have been acknowledged.",
    )

    model_config = ConfigDict(extra="ignore")


class ApplyRequest(BaseModel):
    job_ids: list[str] | None = Field(
        default=None,
        description="Specific job identifiers to apply. Defaults to all staged entries.",
    )
    asset_type: str | None = Field(
        default=None,
        description="Optional asset type override that applies to every processed job.",
    )

    model_config = ConfigDict(extra="ignore")


def _install_hook_specs() -> None:
    enqueued = HookSpec(
        name="on_asset_ingest_enqueued",
        description="Emitted when an asset ingest job is staged (or deduped) by the queue.",
        payload_fields={
            "job_id": "Queue identifier generated for the staged asset.",
            "provider": "Provider key used for metadata normalisation (furaffinity/civitai/huggingface/generic).",
            "status": "Queue status after staging (staged, duplicate, failed).",
            "source_kind": "Source type recorded for the job (local or remote).",
            "digest": "SHA256 digest of the staged artefact when available.",
            "asset_type_hint": "Bucket the mapper inferred for the asset.",
            "dest_relative": "Relative asset path requested by the caller when supplied.",
            "notes": "List of notes produced during queueing (duplicate markers, etc).",
            "timestamp": "UTC timestamp when the job entered the queue.",
        },
        ws_topic="modder.on_asset_ingest_enqueued",
        rest_event="on_asset_ingest_enqueued",
    )
    applied = HookSpec(
        name="on_asset_ingest_applied",
        description="Emitted after a staged ingest job registers an asset in the registry.",
        payload_fields={
            "job_id": "Queue identifier that was applied.",
            "asset_uid": "UID assigned by the asset registry.",
            "asset_path": "Relative path under the asset registry root.",
            "thumb_path": "Relative thumbnail path returned by the registry when generated.",
            "bytes": "Size of the staged artefact in bytes.",
            "meta": "Metadata payload persisted in the registry.",
            "provenance": "Provenance payload recorded alongside the asset.",
            "digest": "Content digest recorded during staging.",
            "timestamp": "UTC timestamp when the apply action completed.",
        },
        ws_topic="modder.on_asset_ingest_applied",
        rest_event="on_asset_ingest_applied",
    )
    failed = HookSpec(
        name="on_asset_ingest_failed",
        description="Emitted when applying an ingest job fails or a remote pull hits an error.",
        payload_fields={
            "job_id": "Queue identifier that failed.",
            "provider": "Provider key used for the ingest job.",
            "error": "Human-readable error message.",
            "status": "Queue status captured after the failure.",
            "digest": "Content digest recorded during staging when available.",
            "meta": "Metadata payload captured for the job.",
            "provenance": "Provenance payload captured for the job.",
            "timestamp": "UTC timestamp when the failure occurred.",
        },
        ws_topic="modder.on_asset_ingest_failed",
        rest_event="on_asset_ingest_failed",
    )
    for spec in (enqueued, applied, failed):
        modder_hooks.HOOK_SPECS[spec.name] = spec
        bus = getattr(modder_hooks, "_BUS", None)
        if bus is not None:
            with bus._lock:  # type: ignore[attr-defined]
                bus._listeners.setdefault(spec.name, [])  # type: ignore[attr-defined]


_install_hook_specs()


def _ensure_enabled() -> None:
    if feature_flags.is_enabled("enable_asset_ingest", default=False):
        return
    raise HTTPException(status_code=403, detail="enable_asset_ingest disabled")


def _record_payload(record: Mapping[str, Any]) -> Dict[str, Any]:
    payload = dict(record)
    payload.setdefault(
        "timestamp", record.get("updated_at") or record.get("created_at")
    )
    return payload


@router.post("/queue")
async def queue_asset(payload: QueueRequest) -> Mapping[str, Any]:
    _ensure_enabled()
    queue = get_ingest_queue()
    try:
        record = queue.enqueue(
            provider=payload.provider,
            raw_metadata=payload.metadata,
            source_path=payload.source_path,
            remote_url=payload.remote_url,
            dest_relative=payload.dest_relative,
            asset_type_hint=payload.asset_type,
            pin=payload.pin,
            terms_acknowledged=payload.terms_acknowledged,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_dict = record.as_dict()
    modder_hooks.emit(
        "on_asset_ingest_enqueued",
        {
            "job_id": record_dict["id"],
            "provider": record_dict["provider"],
            "status": record_dict["status"],
            "source_kind": record_dict["source_kind"],
            "digest": record_dict.get("digest"),
            "asset_type_hint": record_dict.get("asset_type_hint"),
            "dest_relative": record_dict.get("dest_relative"),
            "notes": list(record_dict.get("notes") or []),
            "timestamp": record_dict.get("updated_at") or record_dict.get("created_at"),
        },
    )
    return {"job": record_dict}


@router.get("/status")
async def queue_status(
    job_id: str | None = Query(
        default=None, description="Optional job identifier to inspect."
    ),
    limit: int = Query(
        default=25, ge=1, le=200, description="Number of recent jobs to return."
    ),
    include_cache: bool = Query(
        default=False, description="Include a snapshot of the ingest dedup cache."
    ),
) -> Mapping[str, Any]:
    queue = get_ingest_queue()
    summary = queue.summary()
    response: Dict[str, Any] = {"summary": summary}
    if job_id:
        job = queue.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Unknown ingest job: {job_id}")
        response["job"] = job
    else:
        response["recent"] = queue.list_jobs(limit=limit)
    if include_cache:
        try:
            response["cache"] = queue.cache.snapshot()
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Failed to snapshot ingest cache: %s", exc)
    return response


@router.post("/apply")
async def apply_queue(payload: ApplyRequest) -> Mapping[str, Any]:
    _ensure_enabled()
    queue: AssetIngestQueue = get_ingest_queue()
    try:
        summary = queue.apply(
            job_ids=payload.job_ids,
            asset_type_override=payload.asset_type,
        )
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    applied_jobs = []
    for job_id in summary.get("applied", []):
        job = queue.get(job_id)
        if job:
            applied_jobs.append(job)
            modder_hooks.emit(
                "on_asset_ingest_applied",
                {
                    "job_id": job_id,
                    "asset_uid": job.get("asset_uid"),
                    "asset_path": job.get("asset_path"),
                    "thumb_path": job.get("thumb_path"),
                    "bytes": job.get("size"),
                    "meta": job.get("normalised_metadata"),
                    "provenance": job.get("provenance"),
                    "digest": job.get("digest"),
                    "timestamp": job.get("updated_at"),
                },
            )
    failed_jobs: Dict[str, Dict[str, Any]] = {}
    for job_id, error in summary.get("failed", {}).items():
        job = queue.get(job_id) or {"id": job_id}
        payload = {
            "job_id": job_id,
            "provider": job.get("provider"),
            "error": error,
            "status": job.get("status"),
            "digest": job.get("digest"),
            "meta": job.get("normalised_metadata"),
            "provenance": job.get("provenance"),
            "timestamp": job.get("updated_at"),
        }
        failed_jobs[job_id] = payload
        modder_hooks.emit("on_asset_ingest_failed", payload)
    return {
        "applied": applied_jobs,
        "skipped": summary.get("skipped", []),
        "failed": failed_jobs,
    }
