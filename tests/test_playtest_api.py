from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from comfyvn.qa.playtest import HeadlessPlaytestRunner
from comfyvn.server.routes import playtest as playtest_routes


def test_playtest_api_run(tmp_path, sample_playtest_scene, monkeypatch):
    original_is_enabled = playtest_routes.feature_flags.is_enabled
    monkeypatch.setattr(
        playtest_routes.feature_flags,
        "is_enabled",
        lambda name, **kwargs: (
            True
            if name == "enable_playtest_harness"
            else original_is_enabled(name, **kwargs)
        ),
    )
    monkeypatch.setattr(
        playtest_routes,
        "_RUNNER",
        HeadlessPlaytestRunner(log_dir=tmp_path),
    )
    app = FastAPI()
    app.include_router(playtest_routes.router)

    client = TestClient(app)
    response = client.post(
        "/api/playtest/run",
        json={"scene": sample_playtest_scene, "seed": 3, "persist": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["digest"] == data["trace"]["digest"]
    assert data["trace"]["meta"]["scene_id"] == sample_playtest_scene["id"]
    assert data["persisted"] is False
    assert data["dry_run"] is True
    assert data["trace"]["provenance"]["digest"] == data["digest"]
    assert "log_path" not in data
