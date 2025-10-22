from __future__ import annotations

import copy
import logging
from typing import Any, Dict, Mapping, MutableMapping, Optional

from fastapi import APIRouter, HTTPException

from comfyvn.battle import engine
from comfyvn.config import feature_flags
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


def _coerce_bool(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _ensure_sim_enabled() -> None:
    if feature_flags.is_enabled("enable_battle_sim", default=False):
        return
    raise HTTPException(status_code=403, detail="enable_battle_sim disabled")


def _handle_simulation_request(data: Mapping[str, Any]) -> Dict[str, Any]:
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
    narrate_value = _coerce_bool(data.get("narrate"), default=True)

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
            narrate=narrate_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    persist_state = bool(data.get("persist_state", False))
    response = result.as_dict(include_log=narrate_value)
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
        "outcome": response["outcome"],
        "seed": result.seed,
        "weights": response["weights"],
        "breakdown": response["breakdown"],
        "persisted": response.get("persisted", False),
        "rng": response["rng"],
        "provenance": response["provenance"],
        "narrate": narrate_value,
        "rounds": rounds_value,
    }
    hook_payload["formula"] = response["formula"]
    if narrate_value and response.get("log"):
        hook_payload["log"] = response["log"]
    if response.get("narration"):
        hook_payload["narration"] = response["narration"]
    try:
        modder_hooks.emit("on_battle_simulated", hook_payload)
    except Exception:
        LOGGER.warning("modder hook on_battle_simulated failed", exc_info=True)

    return response


@router.post("/resolve")
async def battle_resolve(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = _ensure_mapping(payload, detail="payload must be an object")

    winner = data.get("winner")
    persist_state = bool(data.get("persist_state", True))
    seed = data.get("seed")
    pov_raw = data.get("pov")
    pov_value = pov_raw if isinstance(pov_raw, str) else None
    narrate_value = _coerce_bool(data.get("narrate"), default=True)

    rounds_raw = data.get("rounds", 1)
    try:
        rounds_value = max(1, int(rounds_raw))
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail="rounds must be an integer"
        ) from exc

    stats_raw = data.get("stats")
    stats_payload: Optional[Mapping[str, Any]] = None
    if stats_raw is not None:
        if not isinstance(stats_raw, Mapping):
            raise HTTPException(
                status_code=400, detail="stats must be an object of contenders"
            )
        stats_payload = stats_raw

    state_raw = data.get("state")
    state_copy: Optional[MutableMapping[str, Any]] = None
    if state_raw is not None:
        state_copy = _ensure_mapping(state_raw, detail="state must be an object")

    try:
        result = engine.resolve(
            winner,
            state=state_copy,
            persist_state=persist_state,
            stats=stats_payload,
            seed=seed,
            pov=pov_value,
            rounds=rounds_value,
            narrate=narrate_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    context = _context_payload(data)
    response: Dict[str, Any] = {
        "outcome": result["outcome"],
        "vars": result["vars"],
        "persisted": result["persisted"],
    }
    for key in (
        "editor_prompt",
        "formula",
        "seed",
        "log",
        "narration",
        "rng",
        "weights",
        "breakdown",
        "predicted_outcome",
        "provenance",
    ):
        if key in result:
            response[key] = result[key]

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
    for key in (
        "editor_prompt",
        "formula",
        "seed",
        "rng",
        "weights",
        "breakdown",
        "narration",
        "log",
        "predicted_outcome",
        "provenance",
    ):
        if key in response:
            hook_payload[key] = response[key]
    hook_payload["narrate"] = narrate_value
    hook_payload["rounds"] = rounds_value
    try:
        modder_hooks.emit("on_battle_resolved", hook_payload)
    except Exception:
        LOGGER.warning("modder hook on_battle_resolved failed", exc_info=True)

    return response


@router.post("/sim")
async def battle_sim(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    _ensure_sim_enabled()
    data = _ensure_mapping(payload, detail="payload must be an object")
    return _handle_simulation_request(data)


@router.post("/simulate")
async def battle_simulate(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    _ensure_sim_enabled()
    data = _ensure_mapping(payload, detail="payload must be an object")
    LOGGER.debug("battle.simulate legacy route invoked via /api/battle/simulate")
    return _handle_simulation_request(data)
