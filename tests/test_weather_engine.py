from __future__ import annotations

import pytest

from comfyvn.weather import WEATHER_PLANNER
from comfyvn.weather.engine import DEFAULT_STATE, WeatherPlanStore, compile_plan


@pytest.fixture(autouse=True)
def _reset_weather_planner():
    WEATHER_PLANNER.clear()
    yield
    WEATHER_PLANNER.clear()


def test_compile_plan_defaults():
    plan = compile_plan({})
    assert plan["state"] == DEFAULT_STATE

    layers = plan["scene"]["background_layers"]
    assert layers[0]["role"] == "base"
    assert layers[1]["role"] == "weather"
    assert plan["scene"]["light_rig"]["exposure"] == pytest.approx(0.05)
    assert plan["particles"] is None
    assert plan["meta"]["warnings"] == []
    assert len(plan["meta"]["hash"]) == 12


def test_compile_plan_with_aliases_and_particles():
    payload = {
        "time_of_day": "sunset",
        "weather": "stormy",
        "ambience": "dramatic",
    }
    plan = compile_plan(payload)
    assert plan["state"]["time_of_day"] == "dusk"
    assert plan["state"]["weather"] == "storm"
    assert plan["state"]["ambience"] == "tense"

    light_rig = plan["scene"]["light_rig"]
    # Exposure should dip for storms but stay within the clamped bounds.
    assert light_rig["exposure"] <= -0.1
    assert 2500 <= light_rig["temperature"] <= 6500

    particles = plan["particles"]
    assert particles is not None
    assert particles["type"] == "rain"
    assert particles["intensity"] > 0.7

    sfx = plan["sfx"]
    assert "storm" in sfx["tags"]
    assert sfx["gain_db"] >= -8.0
    assert "one_shots" in sfx
    assert plan["meta"]["warnings"] == []


def test_compile_plan_reports_warnings_for_unknown_values():
    plan = compile_plan({"time_of_day": "??", "weather": 123})
    assert plan["state"]["time_of_day"] == DEFAULT_STATE["time_of_day"]
    assert plan["state"]["weather"] == DEFAULT_STATE["weather"]
    warnings = plan["meta"]["warnings"]
    assert any("time_of_day" in msg for msg in warnings)
    assert any("weather" in msg for msg in warnings)


def test_plan_store_tracks_versions():
    store = WeatherPlanStore()
    baseline = store.snapshot()
    assert baseline["meta"]["version"] == 0

    updated = store.update({"weather": "rain"})
    assert updated["state"]["weather"] == "rain"
    assert updated["meta"]["version"] == 1

    current_state = dict(updated["state"])
    current_state["time_of_day"] = "night"
    again = store.update(current_state)
    assert again["state"]["weather"] == "rain"
    assert again["state"]["time_of_day"] == "night"
    assert again["meta"]["version"] == 2

    store.clear()
    reset = store.snapshot()
    assert reset["state"] == DEFAULT_STATE
    assert reset["meta"]["version"] == 0
