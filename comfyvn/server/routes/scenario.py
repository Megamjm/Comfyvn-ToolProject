from __future__ import annotations

import time
from typing import Any, Mapping, MutableMapping, Optional

from fastapi import APIRouter, HTTPException

from comfyvn.core import modder_hooks
from comfyvn.runner import ScenarioRunner, ValidationError, validate_scene

router = APIRouter(prefix="/api/scenario", tags=["Scenario"])


def _extract_scene(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    scene = payload.get("scene")
    if isinstance(scene, Mapping):
        return scene
    if {"id", "start", "nodes"} <= set(payload.keys()):
        # Treat direct scene payloads as valid for convenience.
        return payload
    raise HTTPException(status_code=400, detail="scene payload missing or invalid")


def _normalize_choice_id(payload: Mapping[str, Any]) -> Optional[str]:
    choice = payload.get("choice_id")
    if isinstance(choice, str):
        return choice
    choice = payload.get("choice")
    if isinstance(choice, str):
        return choice
    return None


@router.post("/validate")
async def scenario_validate(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        scene = _extract_scene(payload)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    valid, issues = validate_scene(scene)
    return {"valid": valid, "errors": issues}


def _ensure_mapping(value: Any, detail: str) -> MutableMapping[str, Any]:
    if isinstance(value, MutableMapping):
        return value
    raise HTTPException(status_code=400, detail=detail)


@router.post("/run/step")
async def scenario_step(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    scene = _extract_scene(payload)
    seed_raw = payload.get("seed")
    seed = int(seed_raw) if seed_raw is not None else None
    choice_id = _normalize_choice_id(payload)
    pov_raw = payload.get("pov")
    pov_value = None
    if isinstance(pov_raw, str) and pov_raw.strip():
        pov_value = pov_raw.strip()

    state_raw = payload.get("state")
    state: Optional[MutableMapping[str, Any]] = None
    if state_raw is not None:
        state = _ensure_mapping(state_raw, "state must be an object")

    try:
        runner = ScenarioRunner(scene)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail={"errors": exc.issues}) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if state is None:
        base_state = runner.initial_state(seed=seed, pov=pov_value)
    else:
        if pov_value:
            state["pov"] = pov_value
        base_state = state

    try:
        next_state = runner.step(
            base_state, choice_id=choice_id, seed=seed, pov=pov_value
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    peek = runner.peek(next_state)

    event_timestamp = time.time()
    node_payload = peek.get("node") or {}
    node_id = node_payload.get("id") or next_state.get("current_node")
    scene_enter_payload = {
        "scene_id": runner.scene_id,
        "node": node_id,
        "pov": next_state.get("pov"),
        "variables": next_state.get("variables"),
        "history": next_state.get("history"),
        "finished": bool(next_state.get("finished")),
        "timestamp": event_timestamp,
    }
    choice_payload = {
        "scene_id": runner.scene_id,
        "node": node_id,
        "choices": peek.get("choices") or [],
        "pov": next_state.get("pov"),
        "finished": bool(peek.get("finished")),
        "timestamp": event_timestamp,
    }
    try:
        modder_hooks.emit("on_scene_enter", scene_enter_payload)
        modder_hooks.emit("on_choice_render", choice_payload)
    except Exception:
        # Hook dispatching should never break the primary RPC.
        pass

    return {
        "ok": True,
        "state": next_state,
        "node": peek["node"],
        "choices": peek["choices"],
        "finished": peek["finished"],
    }
