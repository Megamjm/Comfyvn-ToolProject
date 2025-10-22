from __future__ import annotations

import sys
import types

import pytest
from fastapi.testclient import TestClient

if (
    "comfyvn.battle.engine" not in sys.modules
):  # pragma: no cover - test shim for missing battle module
    _stub = types.ModuleType("comfyvn.battle.engine")

    class _BattleSimulationResult:  # minimal placeholder to satisfy imports
        pass

    _stub.BattleSimulationResult = _BattleSimulationResult

    def _noop_resolve(*_args, **_kwargs):
        return {}

    def _noop_simulate(*_args, **_kwargs):
        return {}

    _stub.resolve = _noop_resolve
    _stub.simulate = _noop_simulate
    sys.modules["comfyvn.battle.engine"] = _stub

import comfyvn.battle as _battle_pkg  # type: ignore

if not hasattr(_battle_pkg, "plan"):  # pragma: no cover - shim battle planner

    def _dummy_plan(payload):
        return {"steps": [], "input": dict(payload)}

    _battle_pkg.plan = _dummy_plan  # type: ignore[attr-defined]

from comfyvn.config import feature_flags
from comfyvn.core import modder_hooks
from comfyvn.server.app import create_app
from comfyvn.weather import WEATHER_PLANNER


@pytest.fixture(autouse=True)
def _reset_weather_planner():
    WEATHER_PLANNER.clear()
    yield
    WEATHER_PLANNER.clear()


@pytest.fixture(autouse=True)
def _enable_weather_flag(monkeypatch):
    original_is_enabled = feature_flags.is_enabled

    def _patched(name: str, *, default=None, refresh: bool = False):
        if name == "enable_weather_planner":
            return True
        return original_is_enabled(name, default=default, refresh=refresh)

    monkeypatch.setattr(feature_flags, "is_enabled", _patched)
    feature_flags.refresh_cache()
    yield
    feature_flags.refresh_cache()


@pytest.fixture
def _capture_weather_events():
    events: list[tuple[str, dict]] = []

    def _listener(event: str, payload: dict):
        events.append((event, payload))

    modder_hooks.register_listener(_listener, events=("on_weather_plan",))
    try:
        yield events
    finally:
        modder_hooks.unregister_listener(_listener, events=("on_weather_plan",))


def test_weather_state_route_updates_plan(_capture_weather_events):
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/weather/state")
        assert resp.status_code == 200
        baseline = resp.json()
        assert baseline["state"]["weather"] == "clear"
        assert baseline["meta"]["version"] == 0

        resp_rain = client.post("/api/weather/state", json={"weather": "rain"})
        assert resp_rain.status_code == 200
        rain = resp_rain.json()
        assert rain["state"]["weather"] == "rain"
        assert rain["particles"]["type"] == "rain"
        assert rain["meta"]["version"] == 1

        resp_alias = client.post(
            "/api/weather/state",
            json={"time_of_day": "sunrise"},
        )
        assert resp_alias.status_code == 200
        alias = resp_alias.json()
        assert alias["state"]["time_of_day"] == "dawn"
        assert alias["state"]["weather"] == "rain"
        assert alias["meta"]["version"] == 2

    events = _capture_weather_events
    assert events, "Expected at least one modder hook event"
    assert any(
        evt == "on_weather_plan" and payload["state"]["weather"] == "rain"
        for evt, payload in events
    )
    triggers = [payload.get("trigger") for _, payload in events]
    assert "api.weather.state.post" in triggers


def test_weather_route_reports_warnings_for_invalid_values():
    app = create_app()
    with TestClient(app) as client:
        resp = client.post("/api/weather/state", json={"weather": "volcanic"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"]["weather"] == "clear"
        warnings = data["meta"]["warnings"]
        assert any("weather" in entry for entry in warnings)
