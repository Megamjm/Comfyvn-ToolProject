from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest
from fastapi.testclient import TestClient

from comfyvn.battle import engine
from comfyvn.config import feature_flags
from comfyvn.core import modder_hooks
from comfyvn.server.app import create_app


def _capture(
    event_list: List[Tuple[str, Dict[str, Any]]], event: str, payload: Dict[str, Any]
) -> None:
    event_list.append((event, payload))


@pytest.fixture(autouse=True)
def _enable_battle_sim_flag(monkeypatch):
    original_is_enabled = feature_flags.is_enabled

    def _patched(name: str, *, default=None, refresh: bool = False):
        if name == "enable_battle_sim":
            return True
        return original_is_enabled(name, default=default, refresh=refresh)

    monkeypatch.setattr(feature_flags, "is_enabled", _patched)
    feature_flags.refresh_cache()
    try:
        yield
    finally:
        feature_flags.refresh_cache()


def test_battle_simulate_route_returns_log_and_hook() -> None:
    events: List[Tuple[str, Dict[str, Any]]] = []
    listener = lambda event, payload: _capture(events, event, payload)  # noqa: E731
    modder_hooks.register_listener(listener, events=["on_battle_simulated"])
    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/api/battle/simulate",
                json={
                    "stats": {"team_a": 70, "team_b": 30},
                    "seed": 42,
                    "rounds": 2,
                    "scene_id": "demo_scene",
                    "node_id": "battle-1",
                    "pov": "narrator",
                },
            )
    finally:
        modder_hooks.unregister_listener(listener, events=["on_battle_simulated"])

    assert response.status_code == 200
    payload = response.json()

    assert payload["outcome"] in {"team_a", "team_b"}
    assert isinstance(payload["seed"], int)
    assert payload["persisted"] is False
    assert len(payload["log"]) == 2
    assert payload["context"]["scene_id"] == "demo_scene"
    assert payload["formula"] == engine.FORMULA_V0
    assert payload["breakdown"]
    assert all("components" in entry for entry in payload["breakdown"])

    assert events, "Expected on_battle_simulated hook"
    hook_event, hook_payload = events[0]
    assert hook_event == "on_battle_simulated"
    assert hook_payload["outcome"] == payload["outcome"]
    assert hook_payload["scene_id"] == "demo_scene"
    assert hook_payload["log"]
    assert hook_payload["breakdown"]
    assert hook_payload["formula"] == engine.FORMULA_V0


def test_battle_resolve_updates_state_and_emits_hook() -> None:
    events: List[Tuple[str, Dict[str, Any]]] = []
    listener = lambda event, payload: _capture(events, event, payload)  # noqa: E731
    modder_hooks.register_listener(listener, events=["on_battle_resolved"])
    state = {"variables": {"hp": 10}}
    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/api/battle/resolve",
                json={
                    "winner": "team_a",
                    "state": state,
                    "scene_id": "demo_scene",
                    "node_id": "battle-1",
                    "pov": "narrator",
                    "stats": {"team_a": {"base": 4}, "team_b": {"base": 4}},
                    "seed": 17,
                },
            )
    finally:
        modder_hooks.unregister_listener(listener, events=["on_battle_resolved"])

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"] == "team_a"
    assert payload["persisted"] is True
    assert payload["state"]["variables"]["battle_outcome"] == "team_a"
    assert "battle_outcome" not in state["variables"]
    assert payload["context"]["node_id"] == "battle-1"
    assert payload["editor_prompt"] == engine.EDITOR_PROMPT
    assert payload["formula"] == engine.FORMULA_V0
    assert "log" in payload and len(payload["log"]) == 1
    assert payload["seed"] == 17

    assert events, "Expected on_battle_resolved hook"
    hook_event, hook_payload = events[0]
    assert hook_event == "on_battle_resolved"
    assert hook_payload["outcome"] == "team_a"
    assert hook_payload["scene_id"] == "demo_scene"
    assert hook_payload["persisted"] is True
    assert hook_payload["editor_prompt"] == engine.EDITOR_PROMPT
    assert hook_payload["formula"] == engine.FORMULA_V0
    assert hook_payload["log"]
    assert hook_payload["seed"] == 17
