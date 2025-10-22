from __future__ import annotations

import copy
import logging
from typing import Any, Dict, Mapping, MutableMapping, Optional

from fastapi import APIRouter, HTTPException

from comfyvn.battle import engine
from comfyvn.core import modder_hooks

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/battle", tags=["Battle"])


def _ensure_mapping(value: Any, *, detail: str) -> MutableMapping[str, Any]:
    if isinstance(value, MutableMapping):
        return value
    raise HTTPException(status_code=400, detail=detail)


def _context_payload(data: Mapping[str, Any]) -> Dict[str, Any]:
    context: Dict[str, Any] = {}
    for key in ("scene_id", "node_id", "pov"):
        raw = data.get(key)
        if isinstance(raw, str) and raw.strip():
            context[key] = raw.strip()
    return context


@router.post("/resolve")
async def battle_resolve(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")

    winner = data.get("winner")
    persist_state = bool(data.get("persist_state", True))

    state_raw = data.get("state")
    state_copy: Optional[MutableMapping[str, Any]] = None
    if state_raw is not None:
        state_copy = _ensure_mapping(state_raw, detail="state must be an object")

    try:
        result = engine.resolve(
            winner,
            state=state_copy,
            persist_state=persist_state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    context = _context_payload(data)
    response: Dict[str, Any] = {
        "outcome": result["outcome"],
        "vars": result["vars"],
        "persisted": result["persisted"],
    }
    if "state" in result:
        response["state"] = result["state"]
    if context:
        response["context"] = context

    hook_payload = {
        **context,
        "outcome": response["outcome"],
        "vars": response["vars"],
        "persisted": response["persisted"],
    }
    try:
        modder_hooks.emit("on_battle_resolved", hook_payload)
    except Exception:
        LOGGER.warning("modder hook on_battle_resolved failed", exc_info=True)

    return response


@router.post("/simulate")
async def battle_simulate(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")
    stats_raw = data.get("stats")
    if not isinstance(stats_raw, Mapping):
        raise HTTPException(
            status_code=400, detail="stats must be an object of contenders"
        )

    rounds_raw = data.get("rounds", engine.DEFAULT_ROUNDS)
    try:
        rounds_value = max(1, int(rounds_raw))
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail="rounds must be an integer"
        ) from exc

    seed = data.get("seed")
    pov_raw = data.get("pov")
    pov_value = pov_raw if isinstance(pov_raw, str) else None

    state_raw = data.get("state")
    state_copy: Optional[MutableMapping[str, Any]] = None
    rng_state: Optional[Mapping[str, Any]] = None
    if state_raw is not None:
        state_copy = _ensure_mapping(state_raw, detail="state must be an object")
        rng_from_state = state_copy.get("rng")
        if isinstance(rng_from_state, Mapping):
            rng_state = rng_from_state

    rng_payload = data.get("rng")
    if isinstance(rng_payload, Mapping):
        rng_state = rng_payload

    try:
        result = engine.simulate(
            stats_raw,
            seed=seed,
            rng_state=rng_state,
            pov=pov_value,
            rounds=rounds_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    persist_state = bool(data.get("persist_state", False))
    response = result.as_dict()
    response["persisted"] = False

    if state_copy is not None:
        working_state = copy.deepcopy(state_copy)
        if persist_state:
            working_state["rng"] = result.rng_state
            response["persisted"] = True
        response["state"] = working_state

    context = _context_payload(data)
    if context:
        response["context"] = context

    hook_payload = {
        **context,
        "outcome": result.outcome,
        "seed": result.seed,
        "weights": result.weights,
        "log": result.log,
        "persisted": response.get("persisted", False),
    }
    try:
        modder_hooks.emit("on_battle_simulated", hook_payload)
    except Exception:
        LOGGER.warning("modder hook on_battle_simulated failed", exc_info=True)

    return response
