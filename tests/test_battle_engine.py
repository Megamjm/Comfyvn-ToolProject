from __future__ import annotations

import pytest

from comfyvn.battle import engine


def test_resolve_updates_state_when_persisting() -> None:
    state = {"variables": {"hp": 10}}

    result = engine.resolve("team_a", state=state, persist_state=True)

    assert result["outcome"] == "team_a"
    assert result["persisted"] is True
    assert result["state"]["variables"]["battle_outcome"] == "team_a"
    # Original state must remain untouched for callers that reuse it.
    assert "battle_outcome" not in state["variables"]


def test_resolve_stateless_returns_minimal_payload() -> None:
    result = engine.resolve("team_b")
    assert result == {
        "outcome": "team_b",
        "vars": {"battle_outcome": "team_b"},
        "persisted": False,
    }


def test_simulate_is_deterministic_with_seed() -> None:
    stats = {"team_a": 60, "team_b": 40}
    first = engine.simulate(stats, seed=1234, rounds=2, pov="narrator")
    second = engine.simulate(stats, seed=1234, rounds=2, pov="narrator")

    assert first.outcome == second.outcome
    assert first.log == second.log
    assert first.weights == second.weights
    assert first.seed == second.seed


def test_simulate_advances_rng_when_state_supplied() -> None:
    stats = {"hero": 70, "villain": 30}
    initial = engine.simulate(stats, seed=55)
    follow_up = engine.simulate(stats, rng_state=initial.rng_state)

    assert follow_up.rng_state["uses"] > initial.rng_state["uses"]


def test_simulate_rejects_invalid_weights() -> None:
    with pytest.raises(ValueError):
        engine.simulate({"team_a": 0, "team_b": 0})
