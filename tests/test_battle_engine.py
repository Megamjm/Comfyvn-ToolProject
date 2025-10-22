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
    assert result["editor_prompt"] == engine.EDITOR_PROMPT
    assert result["formula"] == engine.FORMULA_V0


def test_resolve_stateless_returns_minimal_payload() -> None:
    result = engine.resolve("team_b")
    assert result["outcome"] == "team_b"
    assert result["vars"] == {"battle_outcome": "team_b"}
    assert result["persisted"] is False
    assert result["editor_prompt"] == engine.EDITOR_PROMPT
    assert result["formula"] == engine.FORMULA_V0


def test_resolve_with_stats_emits_seeded_narration() -> None:
    result = engine.resolve(
        "team_a",
        stats={
            "team_a": {"base": 5, "str": 3},
            "team_b": {"base": 5, "str": 2},
        },
        seed=99,
        pov="narrator",
    )
    assert "log" in result and len(result["log"]) == 1
    assert result["seed"] == 99
    assert "narration" in result
    assert "team_a" in result["narration"]


def test_simulate_is_deterministic_with_seed() -> None:
    stats = {"team_a": 60, "team_b": 40}
    first = engine.simulate(stats, seed=1234, rounds=2, pov="narrator")
    second = engine.simulate(stats, seed=1234, rounds=2, pov="narrator")

    assert first.outcome == second.outcome
    assert first.log == second.log
    assert first.weights == second.weights
    assert first.seed == second.seed
    assert first.breakdown == second.breakdown


def test_simulate_advances_rng_when_state_supplied() -> None:
    stats = {"hero": 70, "villain": 30}
    initial = engine.simulate(stats, seed=55)
    follow_up = engine.simulate(stats, rng_state=initial.rng_state)

    assert follow_up.rng_state["uses"] > initial.rng_state["uses"]


def test_simulate_rejects_invalid_stats() -> None:
    with pytest.raises(ValueError):
        engine.simulate({})


def test_simulate_formula_roll_breakdown_matches_expected_fields() -> None:
    result = engine.simulate(
        {
            "alpha": {
                "base": 10,
                "str": 2,
                "agi": 4,
                "weapon_tier": 1,
                "status_mod": 0.5,
            },
            "beta": {
                "base": 8,
                "str": 3,
                "agi": 1,
                "weapon_tier": 2,
                "status_mod": -0.5,
            },
        },
        seed=7,
        rounds=1,
    )
    assert result.breakdown, "Expected breakdown entries"
    for entry in result.breakdown:
        assert {
            "base",
            "strength",
            "agility",
            "weapon_tier",
            "status_mod",
            "rng",
        } <= entry.components.keys()
        total_components = sum(entry.components.values())
        assert abs(total_components - entry.total) < 1e-6
