from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from comfyvn.app import create_app
from comfyvn.config import feature_flags
from comfyvn.pov.worldlines import WORLDLINES


@pytest.fixture(autouse=True)
def reset_worldlines() -> None:
    WORLDLINES.reset()
    yield
    WORLDLINES.reset()


def _enable_diffmerge_flag(monkeypatch) -> None:
    original = feature_flags.is_enabled

    def _patched(name: str, **kwargs: Any) -> bool:
        if name == "enable_diffmerge_tools":
            return True
        return original(name, **kwargs)

    monkeypatch.setattr(feature_flags, "is_enabled", _patched)
    feature_flags.refresh_cache()


def test_diffmerge_routes_require_flag() -> None:
    app = create_app()
    with TestClient(app) as client:
        resp = client.post("/api/diffmerge/scene", json={"source": "a", "target": "b"})
        assert resp.status_code == 403


def test_scene_diff_and_merge_preview(monkeypatch) -> None:
    _enable_diffmerge_flag(monkeypatch)
    app = create_app()
    with TestClient(app) as client:
        WORLDLINES.create_or_update(
            "canon",
            label="Canon",
            pov="narrator",
            metadata={
                "nodes": ["n1", "n2"],
                "choices": {"narrator": {"n1": {"selection": "stay"}}},
            },
            set_active=True,
        )
        WORLDLINES.create_or_update(
            "branch",
            label="Branch",
            pov="alice",
            metadata={
                "nodes": ["n1", "n3"],
                "choices": {"alice": {"n3": {"selection": "fight"}}},
            },
        )

        diff_resp = client.post(
            "/api/diffmerge/scene",
            json={"source": "branch", "target": "canon", "mask_pov": True},
        )
        assert diff_resp.status_code == 200, diff_resp.text
        payload = diff_resp.json()
        assert payload["node_changes"]["added"] == ["n3"]
        assert payload["node_changes"]["removed"] == ["n2"]
        assert payload["choice_changes"]["changed"] == []

        preview = client.post(
            "/api/diffmerge/worldlines/merge",
            json={"source": "branch", "target": "canon", "apply": False},
        )
        assert preview.status_code == 200
        preview_payload = preview.json()
        assert preview_payload["ok"] is True
        assert preview_payload["target"]["id"] == "canon"
        preview_nodes = preview_payload["target_preview"]["metadata"]["nodes"]
        assert "n3" in preview_nodes

        graph = client.post(
            "/api/diffmerge/worldlines/graph",
            json={"target": "canon", "worlds": ["branch"]},
        )
        assert graph.status_code == 200
        graph_payload = graph.json()
        assert graph_payload["graph"]["nodes"], "graph nodes missing"
        fast_map: Dict[str, Any] = graph_payload.get("fast_forward") or {}
        assert "branch" in fast_map


def test_merge_conflict(monkeypatch) -> None:
    _enable_diffmerge_flag(monkeypatch)
    app = create_app()
    with TestClient(app) as client:
        WORLDLINES.create_or_update(
            "base",
            metadata={
                "nodes": ["n1"],
                "choices": {"narrator": {"n1": {"selection": "stay"}}},
            },
            set_active=True,
        )
        WORLDLINES.create_or_update(
            "conflict",
            metadata={
                "nodes": ["n1"],
                "choices": {"narrator": {"n1": {"selection": "leave"}}},
            },
        )

        resp = client.post(
            "/api/diffmerge/worldlines/merge",
            json={"source": "conflict", "target": "base", "apply": True},
        )
        assert resp.status_code == 409
        detail = resp.json()
        conflicts = detail.get("conflicts") or detail.get("detail", {}).get("conflicts")
        assert conflicts, "conflicts should be reported"
