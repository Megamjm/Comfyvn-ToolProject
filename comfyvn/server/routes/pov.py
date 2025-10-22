from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional

from fastapi import APIRouter, HTTPException

from comfyvn.pov import POV, POV_RUNNER, active_world

router = APIRouter(prefix="/api/pov", tags=["POV"])


def _ensure_mapping(payload: Any, *, detail: str) -> MutableMapping[str, Any]:
    if isinstance(payload, MutableMapping):
        return payload
    raise HTTPException(status_code=400, detail=detail)


@router.get("/get")
async def pov_get(debug: bool = False) -> Mapping[str, Any]:
    snapshot = POV.snapshot()
    snapshot["world"] = active_world()
    if debug:
        snapshot["runner"] = POV_RUNNER.current_context()
    return snapshot


@router.post("/set")
async def pov_set(payload: Any) -> Mapping[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")
    return POV.set(data.get("pov"))


@router.post("/fork")
async def pov_fork(payload: Any) -> Mapping[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")

    slot_raw = data.get("slot")
    if not isinstance(slot_raw, str) or not slot_raw.strip():
        raise HTTPException(status_code=400, detail="slot must be a non-empty string")
    base_slot = slot_raw.strip()

    pov_value: Optional[str] = None
    raw_pov = data.get("pov")
    if isinstance(raw_pov, str) and raw_pov.strip():
        pov_value = raw_pov.strip()

    new_slot = POV.fork_id(base_slot, pov=pov_value)
    return {"slot": new_slot, "pov": pov_value or POV.get()}


@router.post("/candidates")
async def pov_candidates(payload: Any) -> Mapping[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")

    scene = data.get("scene")
    if not isinstance(scene, Mapping):
        # Fallback for clients sending the scene directly.
        scene = data if isinstance(data, Mapping) else {}
    include_trace = bool(data.get("debug") or data.get("with_trace"))
    if include_trace:
        filtered, trace = POV_RUNNER.candidates(scene, with_trace=True)
        return {
            "candidates": filtered,
            "trace": trace,
            "filters": POV_RUNNER.list_filters(),
        }
    candidates = POV_RUNNER.candidates(scene)
    return {"candidates": candidates}
