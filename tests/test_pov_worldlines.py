from __future__ import annotations

import sys
import types
from typing import Dict

import pytest
from fastapi.testclient import TestClient

if (
    "comfyvn.battle.engine" not in sys.modules
):  # pragma: no cover - test shim for missing battle module
    _stub = types.ModuleType("comfyvn.battle.engine")

    class _BattleSimulationResult:  # minimal placeholder for imports
        pass

    _stub.BattleSimulationResult = _BattleSimulationResult

    def _noop(*_args, **_kwargs):
        return {}

    _stub.resolve = _noop
    _stub.simulate = _noop
    sys.modules["comfyvn.battle.engine"] = _stub

from comfyvn.app import create_app
from comfyvn.config import feature_flags
from comfyvn.pov.manager import POVManager
from comfyvn.pov.timeline_worlds import diff_worlds as diff_worlds_fn
from comfyvn.pov.timeline_worlds import merge_worlds as merge_worlds_fn
from comfyvn.pov.worldlines import WORLDLINES, WorldlineRegistry


@pytest.fixture(autouse=True)
def reset_worldlines() -> None:
    WORLDLINES.reset()
    yield
    WORLDLINES.reset()


@pytest.fixture(autouse=True)
def enable_worldline_flags(monkeypatch) -> None:
    original = feature_flags.is_enabled

    def _patched(name: str, **kwargs: object) -> bool:
        if name in {"enable_worldlines", "enable_timeline_overlay"}:
            return True
        return original(name, **kwargs)

    monkeypatch.setattr(feature_flags, "is_enabled", _patched)
    feature_flags.refresh_cache()
    yield
    feature_flags.refresh_cache()


def test_worldline_registry_roundtrip() -> None:
    manager = POVManager()
    registry = WorldlineRegistry(manager)

    world, created, snapshot = registry.create_or_update(
        "canon",
        label="Canon Route",
        pov="narrator",
        root_node="start",
        set_active=True,
    )
    assert created is True
    assert snapshot and snapshot["pov"] == "narrator"
    assert registry.active_snapshot()["id"] == "canon"

    registry.create_or_update(
        "alt",
        label="Alt Route",
        pov="alice",
        root_node="branch_a",
        metadata={"nodes": ["n1"], "choices": {"alice": {"n1": {"selection": "go"}}}},
    )
    world_b, pov_snapshot = registry.switch("alt")
    assert world_b.pov == "alice"
    assert pov_snapshot["pov"] == "alice"

    payloads = registry.list_payloads()
    assert len(payloads) == 2
    assert any(item["active"] for item in payloads)


def test_diff_worlds_masking_and_full_map() -> None:
    registry = WorldlineRegistry(POVManager())
    registry.create_or_update(
        "canon",
        label="Canon",
        metadata={
            "nodes": ["n1", "n2"],
            "choices": {"narrator": {"n1": {"selection": "stay"}}},
        },
    )
    registry.create_or_update(
        "alt",
        label="Alt",
        pov="alice",
        metadata={
            "nodes": ["n1", "n3"],
            "choices": {
                "alice": {"n3": {"selection": "fight"}},
                "narrator": {"n1": {"selection": "stay"}},
            },
        },
    )

    masked = diff_worlds_fn("canon", "alt", registry=registry)
    assert masked["nodes"]["only_in_a"] == ["n2"]
    assert masked["nodes"]["only_in_b"] == ["n3"]
    # Masking defaults to the world's POV ("narrator" for canon, "alice" for alt)
    assert "narrator" in masked["choices"]["a"]
    assert "alice" in masked["choices"]["b"]
    assert "narrator" not in masked["choices"]["b"]  # masked by POV

    full = diff_worlds_fn("canon", "alt", registry=registry, mask_by_pov=False)
    assert "narrator" in full["choices"]["b"]
    assert "alice" in full["choices"]["b"]


def test_merge_worlds_conflict_and_fast_forward() -> None:
    registry = WorldlineRegistry(POVManager())
    registry.create_or_update(
        "base",
        metadata={
            "nodes": ["n1"],
            "choices": {"narrator": {"n1": {"selection": "stay"}}},
        },
    )
    registry.create_or_update(
        "branch",
        pov="alice",
        metadata={"nodes": ["n1", "n2"], "choices": {"alice": {"n2": "attack"}}},
    )
    success = merge_worlds_fn("branch", "base", registry=registry)
    assert success["ok"] is True
    assert success["fast_forward"] is False
    assert success["added_nodes"] == ["n2"]
    target_meta: Dict[str, object] = success["target"]["metadata"]
    assert "n2" in target_meta["nodes"]  # type: ignore[index]

    registry.create_or_update(
        "conflict",
        metadata={
            "nodes": ["n1"],
            "choices": {"narrator": {"n1": {"selection": "leave"}}},
        },
    )
    conflict = merge_worlds_fn("conflict", "base", registry=registry)
    assert conflict["ok"] is False
    assert conflict["conflicts"][0]["node"] == "n1"


def test_pov_worlds_api_flow() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/pov/diff" in paths
    assert "/api/pov/merge" in paths
    with TestClient(app) as client:
        WORLDLINES.reset()

        resp = client.post(
            "/api/pov/worlds",
            json={
                "id": "canon",
                "label": "Canon Route",
                "pov": "narrator",
                "root_node": "start",
                "metadata": {
                    "nodes": ["n1"],
                    "choices": {"narrator": {"n1": {"selection": "stay"}}},
                },
                "activate": True,
            },
        )
        assert resp.status_code == 200, resp.json()
        payload = resp.json()
        assert payload["world"]["id"] == "canon"
        pov_snapshot = payload.get("pov")
        if pov_snapshot:
            assert pov_snapshot.get("pov") == "narrator"

        status = client.get("/api/pov/get").json()
        assert status["world"]["id"] == "canon"

        resp = client.post(
            "/api/pov/worlds",
            json={
                "id": "branch",
                "label": "Branch Route",
                "pov": "alice",
                "root_node": "branch_a",
                "metadata": {
                    "nodes": ["n1", "n2"],
                    "choices": {"alice": {"n2": {"selection": "attack"}}},
                },
            },
        )
        assert resp.status_code == 200, resp.json()
        branch_payload = resp.json()
        assert branch_payload["world"]["id"] == "branch"

        worlds_payload = client.get("/api/pov/worlds").json()
        assert {item["id"] for item in worlds_payload["items"]} == {"canon", "branch"}

        diff = client.post(
            "/api/pov/diff", json={"source": "branch", "target": "canon"}
        )
        assert diff.status_code == 200, diff.text
        diff_payload = diff.json()
        assert diff_payload["nodes"]["only_in_a"] == ["n2"]

        merge = client.post(
            "/api/pov/merge", json={"source": "branch", "target": "canon"}
        )
        assert merge.status_code == 200
        merge_payload = merge.json()
        assert merge_payload["ok"] is True
        assert merge_payload["fast_forward"] is False

        worlds_listing = client.get("/api/pov/worlds").json()
        assert worlds_listing["active"]["id"] == "canon"
        assert any(
            "n2" in item["metadata"].get("nodes", [])
            for item in worlds_listing["items"]
        )

        # Conflict: narrator branch diverges
        client.post(
            "/api/pov/worlds",
            json={
                "id": "conflict",
                "label": "Conflict Route",
                "metadata": {
                    "nodes": ["n1"],
                    "choices": {"narrator": {"n1": {"selection": "leave"}}},
                },
            },
        )
        conflict_resp = client.post(
            "/api/pov/merge", json={"source": "conflict", "target": "canon"}
        )
        assert conflict_resp.status_code == 409
        detail = conflict_resp.json()
        conflicts = detail.get("conflicts")
        if conflicts is None:
            conflicts = detail.get("detail", {}).get("conflicts", [])
        assert conflicts and conflicts[0]["node"] == "n1"
