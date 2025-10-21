from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError
from PySide6.QtGui import QAction

from comfyvn.scenario import (
    ScenarioRuntime,
    ScenarioRuntimeError,
    validate_scenario,
)

router = APIRouter(prefix="/scenario-runtime", tags=["Scenario"])


def _extract_scenario(body: Dict[str, Any]) -> Dict[str, Any]:
    scenario = body.get("scenario") if isinstance(body, dict) else None
    if isinstance(scenario, dict):
        return scenario
    if isinstance(body, dict):
        return body
    raise HTTPException(status_code=400, detail="scenario payload is missing")


@router.post("/validate")
def scenario_validate(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    scenario_doc = _extract_scenario(body)
    result = validate_scenario(scenario_doc)
    return result


@router.post("/step")
def scenario_step(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    scenario_doc = _extract_scenario(body)
    seed = body.get("seed")
    state = body.get("state")
    choice_id = body.get("choice_id")
    try:
        runtime = ScenarioRuntime(scenario_doc, seed=seed, state=state)
        result = runtime.step(choice_id=choice_id)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ScenarioRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "ok": True,
        "event": result.event.model_dump(),
        "state": result.state.model_dump(),
        "done": result.done,
    }
