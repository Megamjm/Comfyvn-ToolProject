from __future__ import annotations

"""Savepoint API for persisting runtime checkpoints."""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from comfyvn.runtime.savepoints import (
    SavepointError,
    SavepointNotFound,
    list_slots,
    load_slot,
)
from comfyvn.runtime.savepoints import (
    save_slot as persist_slot,
)

router = APIRouter(prefix="/api/save", tags=["Savepoints"])


def _expect_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    required = [key for key in ("vars", "node_pointer", "seed") if key not in payload]
    if required:
        missing = ", ".join(required)
        raise HTTPException(status_code=400, detail=f"missing keys: {missing}")
    return payload


@router.get("/list")
async def save_list() -> Dict[str, Any]:
    slots = [item.summary() for item in list_slots()]
    return {"ok": True, "slots": slots}


@router.get("/{slot}")
async def save_load(slot: str) -> Dict[str, Any]:
    try:
        savepoint = load_slot(slot)
    except SavepointNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SavepointError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "save": savepoint.payload()}


@router.post("/{slot}")
async def save_store(slot: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = _expect_payload(payload)
    try:
        savepoint = persist_slot(slot, data)
    except SavepointError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "save": savepoint.payload()}
