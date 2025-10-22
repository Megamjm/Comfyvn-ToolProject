from __future__ import annotations

import copy
import logging
import os
import secrets
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from comfyvn.runner.rng import DeterministicRNG
from comfyvn.runner.scenario_runner import DEFAULT_POV

LOGGER = logging.getLogger(__name__)

ENV_SEED = "COMFYVN_BATTLE_SEED"
DEFAULT_ROUNDS = 3
VARIABLE_KEY = "battle_outcome"
EDITOR_PROMPT = "Pick winner"
FORMULA_V0 = "base + STR*1.0 + AGI*0.5 + weapon_tier*0.75 + status_mod + rng(seed)"

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
    breakdown: List["CompetitorBreakdown"]
    narration: Optional[str] = None

    def provenance(self, resolved_outcome: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "formula": FORMULA_V0,
            "seed": self.seed,
            "rng": dict(self.rng_state),
            "weights": dict(self.weights),
            "predicted_outcome": self.outcome,
        }
        if resolved_outcome is not None:
            payload["resolved_outcome"] = resolved_outcome
        return payload

    def as_dict(
        self,
        *,
        resolved_outcome: Optional[str] = None,
        include_log: bool = True,
    ) -> Dict[str, Any]:
        outcome_value = resolved_outcome if resolved_outcome else self.outcome
        payload: Dict[str, Any] = {
            "outcome": outcome_value,
            "seed": self.seed,
            "weights": dict(self.weights),
            "rng": dict(self.rng_state),
            "breakdown": [entry.as_dict() for entry in self.breakdown],
            "formula": FORMULA_V0,
            "provenance": self.provenance(outcome_value),
        }
        if include_log:
            payload["log"] = [dict(entry) for entry in self.log]
            if self.narration:
                payload["narration"] = self.narration
        else:
            payload["log"] = []
        return payload


@dataclass(slots=True)
class CompetitorBreakdown:
    name: str
    total: float
    components: Dict[str, float]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "total": round(self.total, 3),
            "components": {
                key: round(value, 3) for key, value in self.components.items()
            },
        }


def _coerce_winner(winner: Any) -> str:
    if not isinstance(winner, str):
        raise ValueError("winner must be a non-empty string")
    candidate = winner.strip()
    if not candidate:
        raise ValueError("winner must be a non-empty string")
    return candidate


def _coerce_competitor_name(name: Any) -> str:
    if isinstance(name, str):
        candidate = name.strip()
    else:
        candidate = str(name).strip()
    if not candidate:
        raise ValueError("competitor names must be non-empty strings")
    return candidate


def _coerce_float(
    value: Any, *, competitor: str, field: str, default: float = 0.0
) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except Exception as exc:
        raise ValueError(f"{competitor}.{field} must be numeric") from exc


def _iter_competitors(stats: Mapping[str, Any]) -> List[Tuple[str, Any]]:
    if not isinstance(stats, Mapping):
        raise ValueError("stats must be an object of contenders")
    entries: List[Tuple[str, Any]] = []
    seen: set[str] = set()
    for raw_name, payload in stats.items():
        name = _coerce_competitor_name(raw_name)
        key = name.lower()
        if key in seen:
            raise ValueError(f"duplicate contender '{name}'")
        seen.add(key)
        entries.append((name, payload))
    if not entries:
        raise ValueError("stats must contain at least one contender")
    return entries


def _rng_component(rng: DeterministicRNG, variance: float) -> float:
    jitter = rng.random() * 2.0 - 1.0  # [-1, 1)
    if variance <= 0:
        return 0.0
    return jitter * variance


def _competitor_breakdown(
    name: str,
    payload: Any,
    rng: DeterministicRNG,
) -> CompetitorBreakdown:
    if isinstance(payload, Mapping):
        base_raw = payload.get("base")
        str_raw = payload.get("str", payload.get("strength"))
        agi_raw = payload.get("agi", payload.get("agility"))
        weapon_raw = payload.get("weapon_tier", payload.get("weapon"))
        status_raw = payload.get("status_mod", payload.get("status"))
        variance_raw = payload.get("rng", payload.get("rng_variance", 1.0))
    else:
        base_raw = payload
        str_raw = 0.0
        agi_raw = 0.0
        weapon_raw = 0.0
        status_raw = 0.0
        variance_raw = 1.0

    base = _coerce_float(base_raw, competitor=name, field="base", default=0.0)
    strength_input = _coerce_float(str_raw, competitor=name, field="str", default=0.0)
    agility_input = _coerce_float(agi_raw, competitor=name, field="agi", default=0.0)
    weapon_input = _coerce_float(
        weapon_raw, competitor=name, field="weapon_tier", default=0.0
    )
    status_mod = _coerce_float(
        status_raw, competitor=name, field="status_mod", default=0.0
    )
    variance = max(
        0.0,
        _coerce_float(variance_raw, competitor=name, field="rng", default=1.0),
    )

    strength_bonus = strength_input * 1.0
    agility_bonus = agility_input * 0.5
    weapon_bonus = weapon_input * 0.75
    rng_bonus = _rng_component(rng, variance)

    components = {
        "base": base,
        "strength": strength_bonus,
        "agility": agility_bonus,
        "weapon_tier": weapon_bonus,
        "status_mod": status_mod,
        "rng": rng_bonus,
    }
    total = sum(components.values())
    return CompetitorBreakdown(name=name, total=total, components=components)


def _compute_breakdowns(
    stats: Mapping[str, Any],
    rng: DeterministicRNG,
) -> Tuple[List[str], List[CompetitorBreakdown]]:
    entries = _iter_competitors(stats)
    breakdowns: List[CompetitorBreakdown] = []
    competitors: List[str] = []
    for name, payload in entries:
        competitors.append(name)
        breakdowns.append(_competitor_breakdown(name, payload, rng))
    return competitors, breakdowns


def _normalise_totals(
    breakdowns: Iterable[CompetitorBreakdown],
) -> Dict[str, float]:
    breakdown_list = list(breakdowns)
    totals = [entry.total for entry in breakdown_list]
    if not totals:
        raise ValueError("stats must contain at least one contender")
    min_total = min(totals)
    adjusted: List[Tuple[str, float]] = []
    for entry in breakdown_list:
        score = entry.total - min_total + 1.0
        if score <= 0:
            score = 1e-6
        adjusted.append((entry.name, score))
    total_sum = sum(value for _, value in adjusted)
    if total_sum <= 0.0:
        raise ValueError("unable to normalise contender totals")
    return {name: value / total_sum for name, value in adjusted}


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
    stats: Optional[Mapping[str, Any]] = None,
    seed: Optional[int] = None,
    pov: Optional[str] = None,
    rounds: int = 1,
    narrate: bool = True,
) -> Dict[str, Any]:
    """
    Deterministically apply the supplied winner and optionally persist it to
    the provided scenario state.
    """
    resolved_winner = _coerce_winner(winner)
    try:
        rounds_value = max(1, int(rounds))
    except Exception as exc:
        raise ValueError("rounds must be an integer") from exc

    response: Dict[str, Any] = {
        "outcome": resolved_winner,
        "vars": {variable_key: resolved_winner},
        "persisted": False,
        "editor_prompt": EDITOR_PROMPT,
        "formula": FORMULA_V0,
    }

    analysis: Optional[BattleSimulationResult] = None
    if stats:
        try:
            analysis = _prepare_simulation(
                stats,
                seed,
                None,
                pov=pov,
                rounds=rounds_value,
                narrate=narrate,
            )
        except ValueError as exc:
            LOGGER.debug("battle.resolve stats ignored: %s", exc)
        else:
            response["seed"] = analysis.seed
            response["rng"] = dict(analysis.rng_state)
            response["weights"] = dict(analysis.weights)
            response["breakdown"] = [entry.as_dict() for entry in analysis.breakdown]
            response["predicted_outcome"] = analysis.outcome
            response["provenance"] = analysis.provenance(resolved_winner)
            if analysis.log:
                response["log"] = [dict(entry) for entry in analysis.log]
            if analysis.narration:
                response["narration"] = analysis.narration

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
        "battle.resolve winner=%s persisted=%s seed=%s predicted=%s",
        resolved_winner,
        response["persisted"],
        working_state.get("rng"),
        analysis.outcome if analysis else "n/a",
    )
    return response


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


def _prepare_simulation(
    stats: Mapping[str, Any],
    seed: Optional[int],
    rng_state: Optional[Mapping[str, Any]],
    *,
    pov: Optional[str],
    rounds: int,
    narrate: bool,
) -> BattleSimulationResult:
    rng = _build_rng(seed, rng_state)
    competitors, breakdown = _compute_breakdowns(stats, rng)
    normalised = _normalise_totals(breakdown)
    ranked = sorted(
        breakdown,
        key=lambda entry: (-entry.total, entry.name.lower()),
    )
    winner = ranked[0].name
    rng_snapshot = rng.to_state()
    log_entries: List[Dict[str, Any]] = []
    narration: Optional[str] = None
    if narrate:
        log_rng = DeterministicRNG.from_state(dict(rng_snapshot))
        log_entries = _compose_log_entries(
            log_rng,
            winner,
            competitors,
            rounds=max(1, rounds),
            pov=pov or DEFAULT_POV,
            normalised_weights=normalised,
        )
        if log_entries:
            narration = log_entries[0]["text"]

    LOGGER.debug(
        "battle.sim.core winner=%s seed=%s rounds=%s pov=%s narrate=%s breakdown=%s",
        winner,
        rng.seed,
        rounds,
        pov or DEFAULT_POV,
        narrate,
        {entry.name: round(entry.total, 3) for entry in breakdown},
    )
    return BattleSimulationResult(
        outcome=winner,
        seed=rng.seed,
        weights=normalised,
        log=log_entries,
        rng_state=rng_snapshot,
        breakdown=breakdown,
        narration=narration,
    )


def simulate(
    stats: Mapping[str, Any],
    seed: Optional[int] = None,
    *,
    rng_state: Optional[Mapping[str, Any]] = None,
    pov: Optional[str] = None,
    rounds: int = DEFAULT_ROUNDS,
    narrate: bool = True,
) -> BattleSimulationResult:
    """
    Run a deterministic, weighted simulation returning the chosen outcome and,
    optionally, a narrated log.
    """
    result = _prepare_simulation(
        stats,
        seed,
        rng_state,
        pov=pov,
        rounds=rounds,
        narrate=narrate,
    )
    return result
