from __future__ import annotations

import copy
import logging
import os
import secrets
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from comfyvn.runner.rng import DeterministicRNG, RNGError
from comfyvn.runner.scenario_runner import DEFAULT_POV

LOGGER = logging.getLogger(__name__)

ENV_SEED = "COMFYVN_BATTLE_SEED"
DEFAULT_ROUNDS = 3
VARIABLE_KEY = "battle_outcome"

_NARRATOR_TEMPLATES: Tuple[str, ...] = (
    "{winner} seizes the initiative against {opponent}.",
    "{winner} presses forward while {opponent} struggles to regroup.",
    "{opponent} falters as {winner} turns the tide.",
    "{winner} finds an opening that {opponent} fails to close.",
)
_WINNER_POV_TEMPLATES: Tuple[str, ...] = (
    "I push harder and feel {opponent} giving way.",
    "Their guard drops for a moment and I drive the advantage home.",
    "Another strike lands—{opponent} cannot keep this pace.",
    "I lock eyes with {opponent}; the battle is tipping in my favour.",
)
_LOSER_POV_TEMPLATES: Tuple[str, ...] = (
    "{winner} hammers our defences; we have to adapt fast.",
    "I misjudge their feint—{winner} capitalises immediately.",
    "{winner}'s momentum is overwhelming; we need reinforcements.",
    "Every exchange costs us ground. {winner} refuses to break.",
)


@dataclass(slots=True)
class BattleSimulationResult:
    outcome: str
    seed: int
    weights: Dict[str, float]
    log: List[Dict[str, Any]]
    rng_state: Dict[str, int]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "seed": self.seed,
            "weights": dict(self.weights),
            "log": [dict(entry) for entry in self.log],
            "rng": dict(self.rng_state),
        }


def _coerce_winner(winner: Any) -> str:
    if not isinstance(winner, str):
        raise ValueError("winner must be a non-empty string")
    candidate = winner.strip()
    if not candidate:
        raise ValueError("winner must be a non-empty string")
    return candidate


def _ensure_variables(state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    variables = state.get("variables")
    if variables is None:
        variables = {}
        state["variables"] = variables
    if not isinstance(variables, MutableMapping):
        raise ValueError("state.variables must be an object")
    return variables


def resolve(
    winner: Any,
    *,
    state: Optional[MutableMapping[str, Any]] = None,
    persist_state: bool = True,
    variable_key: str = VARIABLE_KEY,
) -> Dict[str, Any]:
    """
    Deterministically apply the supplied winner and optionally persist it to
    the provided scenario state.
    """
    resolved_winner = _coerce_winner(winner)

    response: Dict[str, Any] = {
        "outcome": resolved_winner,
        "vars": {variable_key: resolved_winner},
        "persisted": False,
    }

    if state is None:
        LOGGER.debug("battle.resolve winner=%s (stateless)", resolved_winner)
        return response

    working_state: MutableMapping[str, Any] = copy.deepcopy(state)
    if persist_state:
        variables = _ensure_variables(working_state)
        variables[variable_key] = resolved_winner
        response["persisted"] = True

    response["state"] = working_state
    LOGGER.debug(
        "battle.resolve winner=%s persisted=%s seed=%s",
        resolved_winner,
        response["persisted"],
        working_state.get("rng"),
    )
    return response


def _normalise_stats(
    stats: Mapping[str, Any]
) -> Tuple[List[str], List[float], Dict[str, float]]:
    competitors: List[str] = []
    weights: List[float] = []
    total = 0.0
    for key, raw_weight in stats.items():
        name = str(key).strip()
        if not name:
            continue
        try:
            weight_value = float(raw_weight)
        except Exception:
            weight_value = 0.0
        if weight_value < 0:
            raise ValueError("weight values must be non-negative")
        competitors.append(name)
        weights.append(weight_value)
        total += weight_value
    if not competitors:
        raise ValueError(
            "stats must contain at least one contender with a non-zero weight"
        )
    if total <= 0.0:
        raise ValueError("at least one contender must have a positive weight")
    normalised = {
        name: (weight / total if total else 0.0)
        for name, weight in zip(competitors, weights)
    }
    return competitors, weights, normalised


def _build_rng(
    seed: Optional[int],
    rng_state: Optional[Mapping[str, Any]],
) -> DeterministicRNG:
    if rng_state is not None:
        try:
            return DeterministicRNG.from_state(dict(rng_state))
        except Exception as exc:
            LOGGER.debug(
                "battle.simulate invalid rng state supplied (%s); falling back", exc
            )
    seed_value: Optional[int] = None
    if seed is not None:
        try:
            seed_value = int(seed)
        except Exception as exc:
            raise ValueError("seed must be an integer") from exc
    if seed_value is None:
        env_seed = os.getenv(ENV_SEED)
        if env_seed:
            try:
                seed_value = int(env_seed)
            except Exception:
                LOGGER.debug("COMFYVN_BATTLE_SEED invalid; ignoring")
    if seed_value is None:
        seed_value = secrets.randbits(32)
        LOGGER.debug(
            "battle.simulate no seed supplied; generated fallback seed=%s", seed_value
        )
    return DeterministicRNG.from_seed(seed_value)


def _choose_template_bank(
    pov: Optional[str], winner: str, contenders: Iterable[str]
) -> Tuple[str, ...]:
    if (
        pov is None
        or pov.strip().lower() == DEFAULT_POV
        or pov.strip().lower() == "narrator"
    ):
        return _NARRATOR_TEMPLATES
    pov_value = pov.strip()
    contenders_lower = {c.lower() for c in contenders}
    if pov_value.lower() == winner.lower():
        return _WINNER_POV_TEMPLATES
    if pov_value.lower() in contenders_lower:
        return _LOSER_POV_TEMPLATES
    return _NARRATOR_TEMPLATES


def _pick_opponent(
    winner: str,
    competitors: List[str],
    normalised_weights: Dict[str, float],
) -> str:
    others = [
        (name, normalised_weights.get(name, 0.0))
        for name in competitors
        if name != winner
    ]
    if not others:
        return "the opposition"
    # Highest weight opponent for deterministic narration context.
    sorted_others = sorted(others, key=lambda item: (-item[1], item[0].lower()))
    return sorted_others[0][0]


def _compose_log_entries(
    rng: DeterministicRNG,
    winner: str,
    competitors: List[str],
    *,
    rounds: int,
    pov: Optional[str],
    normalised_weights: Mapping[str, float],
) -> List[Dict[str, Any]]:
    rounds = max(1, int(rounds))
    bank = _choose_template_bank(pov, winner, competitors)
    opponent_name = _pick_opponent(winner, competitors, dict(normalised_weights))
    pov_value = pov if isinstance(pov, str) and pov.strip() else DEFAULT_POV
    log_entries: List[Dict[str, Any]] = []
    for turn in range(1, rounds + 1):
        idx = int(rng.random() * len(bank)) % len(bank)
        template = bank[idx]
        text = template.format(winner=winner, opponent=opponent_name, pov=pov_value)
        log_entries.append(
            {
                "turn": turn,
                "pov": pov_value,
                "text": text,
            }
        )
    return log_entries


def simulate(
    stats: Mapping[str, Any],
    seed: Optional[int] = None,
    *,
    rng_state: Optional[Mapping[str, Any]] = None,
    pov: Optional[str] = None,
    rounds: int = DEFAULT_ROUNDS,
) -> BattleSimulationResult:
    """
    Run a deterministic, weighted simulation returning the chosen outcome and
    a narrated log.
    """
    competitors, weights, normalised = _normalise_stats(stats)
    rng = _build_rng(seed, rng_state)
    try:
        outcome_idx = rng.weighted_index(weights)
    except RNGError as exc:
        raise ValueError(str(exc)) from exc

    winner = competitors[outcome_idx]
    log_entries = _compose_log_entries(
        rng,
        winner,
        competitors,
        rounds=max(1, rounds),
        pov=pov or DEFAULT_POV,
        normalised_weights=normalised,
    )

    LOGGER.debug(
        "battle.simulate winner=%s seed=%s weights=%s rounds=%s pov=%s",
        winner,
        rng.seed,
        normalised,
        rounds,
        pov or DEFAULT_POV,
    )
    return BattleSimulationResult(
        outcome=winner,
        seed=rng.seed,
        weights=normalised,
        log=log_entries,
        rng_state=rng.to_state(),
    )
