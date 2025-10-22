from __future__ import annotations

"""
Lightweight REST surface for collaboration hubs.

These endpoints complement the WebSocket workflow (`server/modules/collab_api.py`)
by exposing helper calls for health checks, explicit room creation, and
headless clients that need to fetch snapshots or book soft-lock control without
establishing a persistent socket connection.
"""

import logging
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.collab import CRDTOperation
from comfyvn.config import feature_flags
from comfyvn.server.core.collab import HUB, get_room

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/collab", tags=["Collaboration"])


def _ensure_collaboration_enabled() -> Dict[str, bool]:
    flags = feature_flags.load_feature_flags()
    enabled = flags.get("enable_collab")
    if enabled is None:
        enabled = flags.get("enable_collaboration", False)
    if not enabled:
        raise HTTPException(status_code=403, detail="collaboration_disabled")
    return flags


def _coerce_caps(values: Optional[Iterable[str]]) -> List[str]:
    if not values:
        return []
    seen: List[str] = []
    for value in values:
        if not value:
            continue
        item = str(value)
        if item not in seen:
            seen.append(item)
    return seen


class RoomCreateRequest(BaseModel):
    scene_id: str = Field(..., min_length=1, max_length=256)
    include_presence: bool | None = None

    model_config = ConfigDict(extra="forbid")


class RoomJoinRequest(BaseModel):
    scene_id: str = Field(..., min_length=1, max_length=256)
    client_id: str | None = Field(default=None, min_length=1, max_length=256)
    user_name: str | None = Field(default=None, max_length=256)
    clock: int | None = Field(default=None, ge=0)
    cursor: Dict[str, Any] | None = None
    selection: Dict[str, Any] | None = None
    focus: str | None = None
    typing: bool | None = None
    capabilities: List[str] | None = None
    since: int | None = Field(default=None, ge=0)
    request_control: bool | None = None
    control_ttl: float | None = Field(default=None, ge=1.0, le=600.0)
    presence: Dict[str, Any] | None = None
    control: Dict[str, Any] | None = None
    include_snapshot: bool | None = None

    model_config = ConfigDict(extra="forbid")


class RoomLeaveRequest(BaseModel):
    scene_id: str = Field(..., min_length=1, max_length=256)
    client_id: str = Field(..., min_length=1, max_length=256)
    release_control: bool | None = None

    model_config = ConfigDict(extra="forbid")


class RoomApplyRequest(BaseModel):
    scene_id: str = Field(..., min_length=1, max_length=256)
    client_id: str = Field(..., min_length=1, max_length=256)
    operations: Sequence[Dict[str, Any]] = Field(default_factory=list)
    include_snapshot: bool | None = None
    history_since: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")


def _parse_operations(
    ops: Sequence[Dict[str, Any]], client_id: str
) -> List[CRDTOperation]:
    operations: List[CRDTOperation] = []
    for item in ops:
        if not isinstance(item, dict):
            continue
        op_id = str(item.get("op_id") or f"{client_id}:{uuid.uuid4().hex}")
        kind = str(item.get("kind") or "").strip()
        if not kind:
            continue
        payload = item.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        actor = str(item.get("actor") or client_id)
        try:
            clock = int(item.get("clock") or 0)
        except Exception:
            clock = 0
        timestamp = item.get("timestamp")
        try:
            ts_value = float(timestamp) if timestamp is not None else time.time()
        except Exception:
            ts_value = time.time()
        operations.append(
            CRDTOperation(
                op_id=op_id,
                actor=actor,
                clock=clock,
                kind=kind,
                payload=payload,
                timestamp=ts_value,
            )
        )
    return operations


@router.post("/room/create")
async def room_create(request: RoomCreateRequest) -> Dict[str, Any]:
    flags = _ensure_collaboration_enabled()
    room = await get_room(request.scene_id)
    LOGGER.debug("Collab room created/loaded: %s", request.scene_id)
    include_presence = (
        True if request.include_presence is None else bool(request.include_presence)
    )
    payload: Dict[str, Any] = {
        "ok": True,
        "scene_id": room.scene_id,
        "version": room.document.version,
        "clock": room.document.clock,
        "snapshot": room.document.snapshot(),
        "feature_flags": flags,
    }
    if include_presence:
        payload["presence"] = room.presence().as_dict()
    return payload


@router.post("/room/join")
async def room_join(request: RoomJoinRequest) -> Dict[str, Any]:
    flags = _ensure_collaboration_enabled()
    room = await get_room(request.scene_id)

    client_id = request.client_id or f"http_{uuid.uuid4().hex}"
    user_name = (request.user_name or "").strip() or "anon"
    presence_body = request.presence or {}
    cursor = (
        request.cursor if request.cursor is not None else presence_body.get("cursor")
    )
    selection = (
        request.selection
        if request.selection is not None
        else presence_body.get("selection")
    )
    focus = request.focus if request.focus is not None else presence_body.get("focus")
    typing = (
        request.typing if request.typing is not None else presence_body.get("typing")
    )

    caps_override: Optional[List[str]] = None
    if request.capabilities is not None:
        caps_override = _coerce_caps(request.capabilities)
    else:
        caps_from_presence = presence_body.get("capabilities")
        if isinstance(caps_from_presence, Iterable):
            caps_override = _coerce_caps(caps_from_presence)

    capabilities_for_presence: Optional[List[str]] = caps_override

    state = room.register_headless_client(
        client_id,
        user_name,
        capabilities=(
            caps_override
            if (request.capabilities is not None or caps_override is not None)
            else None
        ),
        clock=request.clock,
    )

    presence_payload: Dict[str, Any] = {}
    if cursor is not None:
        presence_payload["cursor"] = cursor
    if selection is not None:
        presence_payload["selection"] = selection
    if focus is not None or focus is None:
        presence_payload["focus"] = focus
    if typing is not None:
        presence_payload["typing"] = typing
    if capabilities_for_presence is not None:
        presence_payload["capabilities"] = capabilities_for_presence
    elif request.capabilities is not None:
        presence_payload["capabilities"] = []
    if presence_payload:
        room.update_presence(client_id, presence_payload)
    else:
        room.touch(client_id)

    control_state: Dict[str, Any] | None = None
    control_body = request.control or {}
    if request.request_control or control_body.get("request"):
        ttl = request.control_ttl
        if ttl is None:
            ttl_raw = control_body.get("ttl")
            try:
                ttl = float(ttl_raw) if ttl_raw is not None else None
            except Exception:
                ttl = None
        control_state = room.request_control(client_id, ttl=ttl)

    history: List[Dict[str, Any]] | None = None
    if request.since is not None:
        history = [
            record.as_dict() for record in room.document.operations_since(request.since)
        ]

    presence = room.presence().as_dict()

    response: Dict[str, Any] = {
        "ok": True,
        "scene_id": room.scene_id,
        "client_id": client_id,
        "user_name": state.user_name,
        "headless": state.headless,
        "version": room.document.version,
        "clock": room.document.clock,
        "snapshot": (
            room.document.snapshot()
            if request.include_snapshot or request.include_snapshot is None
            else None
        ),
        "presence": presence,
        "control": control_state or presence["control"],
        "feature_flags": flags,
    }
    if response["snapshot"] is None:
        response.pop("snapshot", None)
    if history is not None:
        response["history"] = history
    return response


@router.post("/room/leave")
async def room_leave(request: RoomLeaveRequest) -> Dict[str, Any]:
    _ensure_collaboration_enabled()
    room = await get_room(request.scene_id)
    if request.release_control:
        room.release_control(request.client_id)
    left = room.leave(request.client_id)
    presence = room.presence().as_dict()
    return {
        "ok": True,
        "scene_id": room.scene_id,
        "client_id": request.client_id,
        "was_present": left,
        "presence": presence,
        "control": presence["control"],
    }


@router.post("/room/apply")
async def room_apply(request: RoomApplyRequest) -> Dict[str, Any]:
    _ensure_collaboration_enabled()
    room = await get_room(request.scene_id)
    operations = _parse_operations(request.operations, request.client_id)
    if not operations:
        raise HTTPException(status_code=400, detail="no_operations_supplied")

    results = room.apply_operations(request.client_id, operations)
    changed = any(res.applied for res in results)
    result_payload: Dict[str, Any] = {
        "scene_id": room.scene_id,
        "client_id": request.client_id,
        "version": room.document.version,
        "clock": room.document.clock,
        "operations": [res.as_dict() for res in results],
    }
    include_snapshot = bool(request.include_snapshot) or changed
    if include_snapshot:
        result_payload["snapshot"] = room.document.snapshot()
    history_since = request.history_since
    if history_since is not None:
        result_payload["history"] = [
            record.as_dict() for record in room.document.operations_since(history_since)
        ]
    return {"ok": True, "result": result_payload}


@router.get("/room/cache")
async def room_cache_stats() -> Dict[str, Any]:
    """Expose hub cache stats for debugging without the WebSocket handshake."""
    flags = _ensure_collaboration_enabled()
    stats = HUB.stats()
    return {"ok": True, "stats": stats, "feature_flags": flags}


__all__ = ["router"]
