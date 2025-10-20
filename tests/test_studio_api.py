from pathlib import Path

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from comfyvn.server.app import create_app


client = TestClient(create_app())


def test_open_project():
    resp = client.post("/api/studio/open_project", json={"project_id": "demo"})
    assert resp.status_code == 200
    assert resp.json()["project_id"] == "demo"


def test_open_project_requires_id():
    resp = client.post("/api/studio/open_project", json={})
    assert resp.status_code == 400


def test_switch_view():
    resp = client.post("/api/studio/switch_view", json={"view": "Timeline"})
    assert resp.status_code == 200
    assert resp.json()["view"] == "Timeline"


def test_export_bundle(tmp_path: Path):
    raw = {
        "id": "scene-test",
        "dialogue": [{"type": "line", "speaker": "Test", "text": "Hello there!"}],
    }
    out_path = tmp_path / "bundle.json"
    resp = client.post(
        "/api/studio/export_bundle",
        json={"raw": raw, "out_path": str(out_path)},
    )
    assert resp.status_code == 200
    assert resp.json()["bundle"]["path"] == str(out_path)
    assert out_path.exists()
