from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from comfyvn.collab import CRDTOperation
from comfyvn.server.app import app
from comfyvn.server.core import storage
from comfyvn.server.core.collab import HUB, get_room


def _set_scene_root(tmp_path: Path) -> None:
    storage._ROOT = tmp_path / "scenes"
    storage._ROOT.mkdir(parents=True, exist_ok=True)
    storage._LOCKS.clear()


def _op(op_id: str, actor: str, clock: int, kind: str, payload: dict) -> CRDTOperation:
    return CRDTOperation(
        op_id=op_id,
        actor=actor,
        clock=clock,
        kind=kind,
        payload=payload,
    )


@pytest.fixture
def api_client(tmp_path):
    _set_scene_root(tmp_path)
    client = TestClient(app)
    try:
        yield client
    finally:
        HUB.discard_empty()


def test_collab_health_endpoint(api_client: TestClient) -> None:
    response = api_client.get("/api/collab/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "stats" in payload and "feature_flags" in payload


def test_collab_presence_snapshot_history(api_client: TestClient, tmp_path) -> None:
    _set_scene_root(tmp_path)

    async def prepare() -> None:
        room = await get_room("demo_scene")
        op_title = _op(
            "client:1",
            "client",
            1,
            "scene.field.set",
            {"field": "title", "value": "Demo Scene"},
        )
        op_node = _op(
            "client:2",
            "client",
            2,
            "graph.node.upsert",
            {"node": {"id": "intro", "text": "Hello"}},
        )
        room.apply_operations("client", [op_title, op_node])
        await room.flush()

    asyncio.run(prepare())

    presence = api_client.get("/api/collab/presence/demo_scene")
    assert presence.status_code == 200
    presence_payload = presence.json()
    assert presence_payload["ok"] is True
    assert presence_payload["presence"]["participants"] == []

    snapshot = api_client.get("/api/collab/snapshot/demo_scene")
    assert snapshot.status_code == 200
    scene = snapshot.json()["snapshot"]
    assert scene["title"] == "Demo Scene"
    assert any(node["id"] == "intro" for node in scene["nodes"])

    history = api_client.get("/api/collab/history/demo_scene?since=0")
    assert history.status_code == 200
    history_payload = history.json()
    assert history_payload["ok"] is True
    assert len(history_payload["history"]) >= 1

    flush = api_client.post("/api/collab/flush")
    assert flush.status_code == 200
    assert flush.json()["ok"] is True

    HUB.discard_empty()
