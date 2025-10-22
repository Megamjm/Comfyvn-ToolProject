from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping, Optional

from fastapi import APIRouter, Body, HTTPException

from ...pov import (
    WORLDLINES,
    diff_worlds,
    list_worlds,
    merge_worlds,
)
from ...pov import (
    active_world as get_active_world,
)
from ...pov import (
    switch_world as switch_worldline,
)

router = APIRouter(prefix="/api/pov", tags=["POV Worlds"])


def _ensure_mapping(payload: Any, *, detail: str) -> MutableMapping[str, Any]:
    if isinstance(payload, MutableMapping):
        return payload
    raise HTTPException(status_code=400, detail=detail)


def _ensure_optional_mapping(
    payload: Optional[Any], *, detail: str
) -> Optional[Mapping[str, Any]]:
    if payload is None:
        return None
    if isinstance(payload, Mapping):
        return payload
    raise HTTPException(status_code=400, detail=detail)


@router.get("/worlds")
async def get_worlds() -> Dict[str, Any]:
    return {
        "items": list_worlds(),
        "active": get_active_world(),
    }


@router.post("/worlds")
async def create_or_update_world(payload: Any = Body(...)) -> Dict[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")
    world_id = data.get("id")
    if not isinstance(world_id, str) or not world_id.strip():
        raise HTTPException(status_code=400, detail="id must be a non-empty string")

    metadata_payload = _ensure_optional_mapping(
        data.get("metadata"), detail="metadata must be an object"
    )

    activate = bool(data.get("activate") or data.get("switch"))
    label = data.get("label")
    pov = data.get("pov")
    root_node = data.get("root_node")
    notes = data.get("notes")

    metadata = dict(metadata_payload or {})
    snapshot_before = get_active_world()
    world_obj, created, pov_snapshot = WORLDLINES.create_or_update(
        world_id.strip(),
        label=label,
        pov=pov,
        root_node=root_node,
        notes=notes,
        metadata=metadata,
        set_active=activate,
    )
    response: Dict[str, Any] = {
        "world": world_obj.snapshot(),
        "active": get_active_world(),
        "created": created,
    }
    if activate:
        response["pov"] = pov_snapshot or {}
    else:
        response["previous_active"] = snapshot_before
    return response


@router.post("/worlds/switch")
async def switch_world(payload: Any = Body(...)) -> Dict[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")
    world_id = data.get("id")
    if not isinstance(world_id, str) or not world_id.strip():
        raise HTTPException(status_code=400, detail="id must be a non-empty string")
    try:
        world, pov_snapshot = switch_worldline(world_id.strip())
    except KeyError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "world": world,
        "pov": pov_snapshot,
        "active": get_active_world(),
    }


@router.post("/diff")
async def diff_world(payload: Any = Body(...)) -> Dict[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")
    source_id = data.get("source") or data.get("world_a")
    target_id = data.get("target") or data.get("world_b")
    if not isinstance(source_id, str) or not source_id.strip():
        raise HTTPException(status_code=400, detail="source must be a non-empty string")
    if not isinstance(target_id, str) or not target_id.strip():
        raise HTTPException(status_code=400, detail="target must be a non-empty string")
    mask = data.get("mask_pov")
    mask_by_pov = True if mask is None else bool(mask)
    try:
        return diff_worlds(
            source_id.strip(),
            target_id.strip(),
            mask_by_pov=mask_by_pov,
        )
    except KeyError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/merge")
async def merge_world(payload: Any = Body(...)) -> Dict[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")
    source_id = data.get("source")
    target_id = data.get("target")
    if not isinstance(source_id, str) or not source_id.strip():
        raise HTTPException(status_code=400, detail="source must be a non-empty string")
    if not isinstance(target_id, str) or not target_id.strip():
        raise HTTPException(status_code=400, detail="target must be a non-empty string")
    try:
        result = merge_worlds(source_id.strip(), target_id.strip())
    except KeyError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result)
    return result
