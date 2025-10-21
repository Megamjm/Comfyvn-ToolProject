from __future__ import annotations

import sys
import types
from typing import Dict

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

# Minimal PySide6 stub if real Qt is unavailable.
if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type("QAction", (), {})
    pyside6.QtGui = qtgui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtGui"] = qtgui

from comfyvn.scenario import ScenarioRuntime, ScenarioRuntimeError, validate_scenario
from comfyvn.server.app import create_app


@pytest.fixture
def sample_scenario() -> Dict[str, object]:
    return {
        "id": "demo",
        "start": "intro",
        "title": "Demo Scenario",
        "variables": {"flag": {"type": "boolean", "default": False}},
        "nodes": [
            {
                "id": "intro",
                "type": "line",
                "text": "Hello traveller.",
                "next": "decision",
            },
            {
                "id": "decision",
                "type": "choice",
                "prompt": "What do you do?",
                "choices": [
                    {
                        "id": "opt_a",
                        "text": "Take the left path",
                        "next": "set_flag",
                        "weight": 1.0,
                    },
                    {
                        "id": "opt_b",
                        "text": "Head right",
                        "next": "ending",
                        "weight": 1.0,
                        "set": {"flag": "turned-right"},
                    },
                ],
            },
            {
                "id": "set_flag",
                "type": "set",
                "assign": {"flag": True},
                "next": "ending",
            },
            {
                "id": "ending",
                "type": "end",
                "result": "done",
            },
        ],
    }


def test_validate_scenario_ok(sample_scenario):
    result = validate_scenario(sample_scenario)
    assert result["ok"] is True
    assert "schema" in result


def test_validate_scenario_missing_reference(sample_scenario):
    broken = dict(sample_scenario)
    broken["nodes"] = list(sample_scenario["nodes"])
    broken["nodes"][0] = dict(broken["nodes"][0])
    broken["nodes"][0]["next"] = "missing"
    result = validate_scenario(broken)
    assert result["ok"] is False
    assert result["errors"]


def test_runtime_walk_with_explicit_choice(sample_scenario):
    rt = ScenarioRuntime(sample_scenario, seed=17)
    first = rt.step()
    assert first.event.type == "line"
    second = rt.step(choice_id="opt_b")
    assert second.event.type == "choice"
    assert second.event.data["choice"]["id"] == "opt_b"
    final = rt.step()
    assert final.done is True
    assert final.event.type == "end"
    assert final.state.variables["flag"] == "turned-right"


def test_runtime_deterministic_choice(sample_scenario):
    rt1 = ScenarioRuntime(sample_scenario, seed=5)
    rt2 = ScenarioRuntime(sample_scenario, seed="5")
    assert rt1.step().event.type == "line"
    assert rt2.step().event.type == "line"
    choice_one = rt1.step().event.data["choice"]["id"]
    choice_two = rt2.step().event.data["choice"]["id"]
    assert choice_one == choice_two


def test_runtime_raises_when_no_options(sample_scenario):
    scenario = dict(sample_scenario)
    scenario["nodes"] = list(sample_scenario["nodes"])
    scenario["nodes"][1] = dict(scenario["nodes"][1])
    scenario["nodes"][1]["choices"] = []
    rt = ScenarioRuntime(scenario)
    rt.step()  # consume intro
    with pytest.raises(ScenarioRuntimeError):
        rt.step()


def test_api_validate_and_step(sample_scenario):
    client = TestClient(create_app())
    resp = client.post("/scenario-runtime/validate", json={"scenario": sample_scenario})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    step_one = client.post(
        "/scenario-runtime/step", json={"scenario": sample_scenario, "seed": 3}
    )
    assert step_one.status_code == 200
    data1 = step_one.json()
    assert data1["event"]["type"] == "line"

    payload_choice = {
        "scenario": sample_scenario,
        "state": data1["state"],
        "choice_id": "opt_a",
    }
    step_two = client.post("/scenario-runtime/step", json=payload_choice)
    assert step_two.status_code == 200
    data2 = step_two.json()
    assert data2["event"]["type"] == "choice"
    assert data2["event"]["data"]["choice"]["id"] == "opt_a"

    payload_set = {"scenario": sample_scenario, "state": data2["state"]}
    step_three = client.post("/scenario-runtime/step", json=payload_set)
    assert step_three.status_code == 200
    data3 = step_three.json()
    assert data3["event"]["type"] == "set"

    payload_end = {"scenario": sample_scenario, "state": data3["state"]}
    step_four = client.post("/scenario-runtime/step", json=payload_end)
    assert step_four.status_code == 200
    data4 = step_four.json()
    assert data4["done"] is True
    assert data4["event"]["type"] == "end"
