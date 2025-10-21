from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Dict

import pytest
from fastapi.testclient import TestClient

from comfyvn.runner import ScenarioRunner
from comfyvn.server.app import create_app


@pytest.fixture()
def savepoints_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from comfyvn.runtime import savepoints

    root = tmp_path / "saves"
    monkeypatch.setattr(savepoints, "SAVE_DIR", root, raising=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture()
def savepoint_client(savepoints_dir: Path) -> TestClient:
    app = create_app()
    with TestClient(app) as client:
        yield client


def test_savepoint_runtime_roundtrip(savepoints_dir: Path):
    from comfyvn.runtime import savepoints

    payload: Dict[str, object] = {
        "vars": {"score": 42, "chapter": 3},
        "node_pointer": "node-3",
        "seed": 987654321,
        "note": "checkpoint",
    }

    savepoint = savepoints.save_slot("Slot One!", payload)
    assert savepoint.slot == "slot-one"
    assert savepoint.vars == payload["vars"]
    assert savepoint.node_pointer == payload["node_pointer"]
    assert savepoint.seed == payload["seed"]
    assert savepoints_dir.joinpath("slot-one.json").exists()

    loaded = savepoints.load_slot("slot-one")
    assert loaded.vars == payload["vars"]
    assert loaded.node_pointer == payload["node_pointer"]
    assert loaded.seed == payload["seed"]
    assert loaded.extras["note"] == "checkpoint"

    listed = savepoints.list_slots()
    assert [entry.slot for entry in listed] == ["slot-one"]
    summary = listed[0].summary()
    assert summary["slot"] == "slot-one"
    assert isinstance(summary["size_bytes"], int)
    assert summary["size_bytes"] > 0


def test_savepoint_api_roundtrip(savepoint_client: TestClient, savepoints_dir: Path):
    payload = {
        "vars": {"hp": 10, "inventory": ["key", "potion"]},
        "node_pointer": "intro",
        "seed": 12345,
        "metadata": {"difficulty": "normal"},
    }

    resp = savepoint_client.post("/api/save/slot-alpha", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["save"]["slot"] == "slot-alpha"
    assert data["save"]["vars"] == payload["vars"]
    assert data["save"]["node_pointer"] == payload["node_pointer"]
    assert data["save"]["seed"] == payload["seed"]
    assert data["save"]["metadata"] == payload["metadata"]

    resp = savepoint_client.get("/api/save/slot-alpha")
    assert resp.status_code == 200, resp.text
    loaded = resp.json()
    assert loaded["save"]["vars"] == payload["vars"]
    assert loaded["save"]["node_pointer"] == payload["node_pointer"]
    assert loaded["save"]["seed"] == payload["seed"]
    assert loaded["save"]["metadata"] == payload["metadata"]

    listing = savepoint_client.get("/api/save/list")
    assert listing.status_code == 200, listing.text
    items = listing.json()["slots"]
    assert len(items) == 1
    assert items[0]["slot"] == "slot-alpha"
    assert (
        items[0]["size_bytes"]
        == savepoints_dir.joinpath("slot-alpha.json").stat().st_size
    )

    missing = savepoint_client.get("/api/save/unknown")
    assert missing.status_code == 404

    bad_payload = {"vars": {"hp": 5}, "node_pointer": "intro"}
    err = savepoint_client.post("/api/save/slot-beta", json=bad_payload)
    assert err.status_code == 400


def test_runner_resume_consistent_after_save(savepoint_client: TestClient):
    scene = {
        "id": "demo-scene",
        "start": "start",
        "nodes": [
            {
                "id": "start",
                "type": "dialogue",
                "text": "Opening narration.",
                "choices": [
                    {
                        "id": "branch_left",
                        "label": "Left",
                        "target": "left_path",
                        "weight": 1.0,
                    },
                    {
                        "id": "branch_right",
                        "label": "Right",
                        "target": "right_path",
                        "weight": 3.0,
                    },
                ],
            },
            {
                "id": "left_path",
                "type": "dialogue",
                "text": "You went left.",
                "actions": [{"type": "set", "key": "flags.left", "value": True}],
                "choices": [
                    {"id": "finish_left", "label": "Finish", "target": "ending"}
                ],
            },
            {
                "id": "right_path",
                "type": "dialogue",
                "text": "You went right.",
                "actions": [{"type": "set", "key": "flags.right", "value": True}],
                "choices": [
                    {"id": "finish_right", "label": "Finish", "target": "ending"}
                ],
            },
            {
                "id": "ending",
                "type": "dialogue",
                "text": "Journey complete.",
                "end": True,
            },
        ],
    }

    runner = ScenarioRunner(scene)
    initial_state = runner.initial_state(seed=17)
    baseline_state = deepcopy(initial_state)
    expected_next_state = runner.step(baseline_state)

    payload = {
        "vars": deepcopy(initial_state["variables"]),
        "node_pointer": initial_state["current_node"],
        "seed": deepcopy(initial_state["rng"]),
        "history": deepcopy(initial_state.get("history", [])),
        "finished": initial_state.get("finished", False),
    }

    resp = savepoint_client.post("/api/save/demo-slot", json=payload)
    assert resp.status_code == 200, resp.text

    loaded = savepoint_client.get("/api/save/demo-slot")
    assert loaded.status_code == 200, loaded.text
    saved = loaded.json()["save"]

    resume_state = {
        "scene_id": scene["id"],
        "current_node": saved["node_pointer"],
        "variables": deepcopy(saved["vars"]),
        "rng": deepcopy(saved["seed"]),
        "history": deepcopy(saved.get("history", [])),
        "finished": saved.get("finished", False),
    }

    fresh_runner = ScenarioRunner(scene)
    resumed_state = fresh_runner.step(resume_state)

    assert resumed_state == expected_next_state
