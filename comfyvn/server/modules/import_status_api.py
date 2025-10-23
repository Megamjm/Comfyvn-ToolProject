from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from comfyvn.server.core.import_status import import_status_store

router = APIRouter(prefix="/imports", tags=["Imports"])


@router.get("/status/{job_id}")
def import_status(job_id: str):
    """Return the normalized status snapshot for any import job."""
    try:
        status = import_status_store.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "job": status.to_dict()}


@router.get("/status")
def list_import_status(kinds: Optional[List[str]] = Query(default=None)):
    """List import jobs filtered by kind if provided."""
    statuses = import_status_store.list(kinds=kinds)
    return {"ok": True, "jobs": [status.to_dict() for status in statuses]}
