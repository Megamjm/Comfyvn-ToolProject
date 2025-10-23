"""FastAPI routes exposing the production manga pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field, field_validator

from comfyvn.manga.pipeline import (
    build_config,
    provider_catalog,
)
from comfyvn.manga.pipeline import (
    start as start_job,
)
from comfyvn.manga.pipeline import (
    status as job_status,
)

DATA_ROOT_ENV = "COMFYVN_MANGA_DATA_ROOT"
DEFAULT_DATA_ROOT = Path("data/manga")

router = APIRouter(prefix="/manga/pipeline", tags=["Manga Pipeline"])


def _data_root() -> Path:
    configured = os.getenv(DATA_ROOT_ENV)
    root = Path(configured) if configured else DEFAULT_DATA_ROOT
    return root.expanduser().resolve()


class ProviderSelection(BaseModel):
    segment: Optional[str] = None
    ocr: Optional[str] = None
    group: Optional[str] = None
    speaker: Optional[str] = None


class MangaPipelineStartRequest(BaseModel):
    sources: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    providers: ProviderSelection = Field(default_factory=ProviderSelection)
    provider_settings: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    @field_validator("sources", mode="before")
    def _normalize_source(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, dict):
            return [str(value).strip()]
        if isinstance(value, (list, tuple, set)):
            trimmed = [str(entry).strip() for entry in value if str(entry).strip()]
            return trimmed
        text = str(value).strip()
        return [text] if text else []


@router.get("/providers")
def list_providers() -> Dict[str, Any]:
    """Return available providers grouped by stage."""
    return {"providers": provider_catalog()}


@router.post("/start", status_code=http_status.HTTP_202_ACCEPTED)
def start_pipeline(payload: MangaPipelineStartRequest = Body(...)) -> Dict[str, Any]:
    """Start the manga pipeline and return the job identifier."""
    root = _data_root()
    provider_overrides = payload.providers.dict(exclude_none=True)
    config = build_config(
        sources=payload.sources,
        providers=provider_overrides,
        provider_settings=payload.provider_settings,
        metadata=payload.metadata,
    )
    job_id = start_job(root, config)
    snapshot = job_status(job_id)
    return {"job": job_id, "state": snapshot.get("state"), "snapshot": snapshot}


@router.get("/status/{job_id}")
def pipeline_status(job_id: str) -> Dict[str, Any]:
    """Fetch the current pipeline status for a job."""
    snapshot = job_status(job_id)
    if snapshot.get("state") == "not_found":
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return snapshot
