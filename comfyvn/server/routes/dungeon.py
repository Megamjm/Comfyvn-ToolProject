from __future__ import annotations

import logging
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException

from comfyvn.config import feature_flags
from comfyvn.dungeon.api import (
    API as dungeon_api,
)
from comfyvn.dungeon.api import (
    DungeonAPIError,
    DungeonSessionNotFound,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dungeon", tags=["Dungeon"])


def _require_feature() -> None:
    if feature_flags.is_enabled("enable_dungeon_api", default=False):
        return
    raise HTTPException(status_code=403, detail="enable_dungeon_api disabled")


def _ensure_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    raise HTTPException(status_code=400, detail="payload must be an object")


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, DungeonSessionNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, DungeonAPIError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    LOGGER.warning("Unhandled dungeon API error: %s", exc, exc_info=True)
    raise HTTPException(status_code=500, detail="dungeon API error") from exc


@router.post("/enter")
async def dungeon_enter(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    _require_feature()
    data = _ensure_payload(payload)
    try:
        return dungeon_api.enter(data)
    except Exception as exc:  # pragma: no cover - FastAPI bridge
        _handle_error(exc)


@router.post("/step")
async def dungeon_step(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    _require_feature()
    data = _ensure_payload(payload)
    try:
        return dungeon_api.step(data)
    except Exception as exc:  # pragma: no cover - FastAPI bridge
        _handle_error(exc)


@router.post("/encounter_start")
async def dungeon_encounter_start(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    _require_feature()
    data = _ensure_payload(payload)
    try:
        return dungeon_api.encounter_start(data)
    except Exception as exc:  # pragma: no cover - FastAPI bridge
        _handle_error(exc)


@router.post("/resolve")
async def dungeon_resolve(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    _require_feature()
    data = _ensure_payload(payload)
    try:
        return dungeon_api.resolve(data)
    except Exception as exc:  # pragma: no cover - FastAPI bridge
        _handle_error(exc)


@router.post("/leave")
async def dungeon_leave(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    _require_feature()
    data = _ensure_payload(payload)
    try:
        return dungeon_api.leave(data)
    except Exception as exc:  # pragma: no cover - FastAPI bridge
        _handle_error(exc)
