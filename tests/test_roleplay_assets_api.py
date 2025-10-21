from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from comfyvn.config.runtime_paths import data_dir
from comfyvn.server.app import create_app
from comfyvn.server.modules.roleplay.roleplay_api import _asset_registry
from setup.apply_phase06_rebuild import ensure_db, ensure_dirs

# Ensure required folders/tables exist before exercising APIs.
ensure_dirs()
ensure_db()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_TOKEN", "testtoken")
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_roleplay_import_persists_scene(client: TestClient):
    payload = {
        "text": "Alice: Hello there!\nBob: Hey Alice.\nNarrator: The room falls silent.",
        "title": "Importer Test",
        "world": "demo-world",
        "metadata": {"genre": "slice-of-life"},
        "blocking": True,
    }
    resp = client.post("/roleplay/import", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True

    scene = data["scene"]
    assert scene["title"] == "Importer Test"
    assert len(scene["nodes"]) == 3
    assert scene["meta"]["participants"] == ["Alice", "Bob", "Narrator"]
    advisories = data["advisory_flags"]
    assert any(
        (issue.get("detail") or {}).get("field") == "license" for issue in advisories
    )
    assert any(
        (issue.get("detail") or {}).get("field") == "safety" for issue in advisories
    )
    assert "preview_path" in data
    assert "status" in data

    asset = data["asset"]
    asset_path = (_asset_registry.ASSETS_ROOT / asset["path"]).resolve()
    assert asset_path.exists()

    log_path = Path(data["logs_path"])
    assert log_path.exists()

    status = client.get(f"/roleplay/imports/{data['job_id']}")
    assert status.status_code == 200
    status_payload = status.json()["job"]
    assert status_payload["status"] == "completed"
    assert status_payload["output"]["scene_id"] == data["scene_db_id"]
    assert status_payload["output"]["asset_uid"] == asset["uid"]
    assert status_payload["output"]["paths"]["preview"].endswith(".json")
    assert status_payload["output"]["status"]["status"] == "ready"

    status_via_preview = client.get(f"/roleplay/imports/status/{data['job_id']}")
    assert status_via_preview.status_code == 200

    list_resp = client.get("/roleplay/imports")
    assert list_resp.status_code == 200
    jobs = list_resp.json()["items"]
    assert any(job["id"] == data["job_id"] for job in jobs)

    log_resp = client.get(f"/roleplay/imports/{data['job_id']}/log")
    assert log_resp.status_code == 200
    assert "scene_id=" in log_resp.text

    preview_resp = client.get(f"/roleplay/preview/{data['scene_uid']}")
    assert preview_resp.status_code == 200
    preview_payload = preview_resp.json()
    assert preview_payload["preview"]["excerpt"]
    assert preview_payload["status"]["status"] in {"ready", "stale"}


def test_roleplay_import_async_background(client: TestClient):
    payload = {
        "text": "Alice: Testing asyncio.\nBob: Background job run!",
        "title": "Async Import",
        "world": "async-world",
        "metadata": {"genre": "demo"},
    }
    resp = client.post("/roleplay/import", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "queued"
    queued_log_path = Path(data["logs_path"])
    assert queued_log_path.exists()
    job_id = data["job_id"]

    for _ in range(50):
        status_resp = client.get(f"/roleplay/imports/{job_id}")
        assert status_resp.status_code == 200
        job_payload = status_resp.json()["job"]
        if job_payload["status"] == "completed":
            output = job_payload["output"]
            assert output["scene_id"]
            assert "preview" in output["paths"]
            break
        if job_payload["status"] == "failed":
            pytest.fail(f"roleplay import failed: {job_payload['output']}")
        time.sleep(0.02)
    else:
        pytest.fail("roleplay import did not complete in time")

    status_endpoint_resp = client.get(f"/roleplay/imports/status/{job_id}")
    assert status_endpoint_resp.status_code == 200

    preview_resp = client.get(f"/roleplay/preview/{output['scene_uid']}")
    assert preview_resp.status_code == 200
    preview_json = preview_resp.json()
    assert preview_json["preview"]["excerpt"]
    assert preview_json["status"]["status"] in {"ready", "stale"}


def _auth_headers() -> dict[str, str]:
    token = os.environ.get("API_TOKEN", "testtoken")
    return {"Authorization": f"Bearer {token}"}


def test_assets_upload_and_delete(client: TestClient, tmp_path: Path):
    headers = _auth_headers()
    upload_resp = client.post(
        "/assets/upload",
        headers=headers,
        files={"file": ("hello.txt", b"hi there", "text/plain")},
        data={"asset_type": "documents", "metadata": json.dumps({"license": "cc0"})},
    )
    assert upload_resp.status_code == 200, upload_resp.text
    uploaded = upload_resp.json()["asset"]

    list_resp = client.get("/assets/")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert any(item["uid"] == uploaded["uid"] for item in items)

    detail_resp = client.get(f"/assets/{uploaded['uid']}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["asset"]["meta"]["license"] == "cc0"

    download_resp = client.get(f"/assets/{uploaded['uid']}/download")
    assert download_resp.status_code == 200
    assert download_resp.content == b"hi there"

    delete_resp = client.delete(f"/assets/{uploaded['uid']}", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["trashed"] is True

    missing_resp = client.get(f"/assets/{uploaded['uid']}")
    assert missing_resp.status_code == 404
