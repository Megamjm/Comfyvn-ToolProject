from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional

from fastapi import APIRouter, HTTPException

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

    base_state = state or runner.initial_state(seed=seed)

    try:
        next_state = runner.step(base_state, choice_id=choice_id, seed=seed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    peek = runner.peek(next_state)

    return {
        "ok": True,
        "state": next_state,
        "node": peek["node"],
        "choices": peek["choices"],
        "finished": peek["finished"],
    }
