from __future__ import annotations

import io
import json
import sys
import types
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

# Provide a minimal PySide6 stub so dynamic router imports do not fail in tests.
if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type("QAction", (), {})
    pyside6.QtGui = qtgui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtGui"] = qtgui


from comfyvn.server.app import create_app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_TOKEN", "testtoken")
    app = create_app()
    with TestClient(app) as c:
        yield c


def _make_demo_package(path: Path) -> Path:
    pkg = path / "demo.cvnpack"
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps({"name": "demo", "licenses": []}))
        z.writestr(
            "scenes/intro.json",
            json.dumps({"id": "intro", "title": "Intro", "nodes": []}),
        )
        z.writestr(
            "characters/alice.json", json.dumps({"id": "alice", "name": "Alice"})
        )
        z.writestr("assets/readme.txt", b"hello")
    return pkg


def _make_manga_archive(path: Path) -> Path:
    archive = path / "manga.cbz"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("page1.png", b"fake")
        z.writestr("page1.txt", "Alice: Hello!\nBob: Hi Alice.")
        z.writestr("page2.png", b"fake")
    return archive


def test_vn_import_blocking_and_jobs_status(client: TestClient, tmp_path: Path):
    package = _make_demo_package(tmp_path)
    resp = client.post(
        "/vn/import",
        json={"path": str(package), "blocking": True, "overwrite": True},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["ok"] is True
    job_id = payload["job"]["id"]
    summary = payload["import"]
    assert summary["adapter"] in {"generic", "renpy", "lightvn"}
    assert "intro" in summary.get("scenes", [])
    assert payload.get("logs_path")
    assert Path(payload["logs_path"]).exists()
    assert summary.get("preview_path")
    assert Path(summary["preview_path"]).exists()

    # Poll generic jobs/status API
    status = client.get(f"/jobs/status/{job_id}")
    assert status.status_code == 200, status.text
    job = status.json()["job"]
    assert job["status"] in {"done", "error"}

    # VN-specific status endpoint should also work
    vn_status = client.get(f"/vn/import/{job_id}")
    assert vn_status.status_code == 200
    assert vn_status.json()["ok"] is True

    # Unified import status endpoint
    unified = client.get(f"/imports/status/{job_id}")
    assert unified.status_code == 200
    status_payload = unified.json()["job"]
    assert status_payload["kind"] == "vn"
    assert status_payload.get("logs_path") == payload["logs_path"]
    assert status_payload.get("percent") >= 100.0
    listing = client.get("/imports/status")
    assert listing.status_code == 200
    jobs = listing.json().get("jobs", [])
    assert any(
        entry.get("job_id") == job_id or entry.get("job_id") == str(job_id)
        for entry in jobs
    )


def test_vn_import_bad_input_returns_400(client: TestClient):
    r = client.post("/vn/import", json={})
    assert r.status_code == 400


def test_roleplay_import_bad_input_returns_400(client: TestClient):
    # Missing both text and lines -> HTTP 400
    r = client.post("/roleplay/import", json={})
    assert r.status_code in {400, 422}


def test_roleplay_import_log_stream_present(client: TestClient):
    body = {
        "text": "Alice: Hello!\nBob: Hi Alice.",
        "title": "Importer E2E",
        "world": "test-world",
    }
    r = client.post("/roleplay/import", json=body)
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    # Log endpoint returns plain text
    log = client.get(f"/roleplay/imports/{job_id}/log")
    assert log.status_code == 200
    assert "scene_id=" in log.text or "[ok]" in log.text or "[queued]" in log.text
    status = client.get(f"/roleplay/imports/status/{job_id}")
    assert status.status_code == 200
    unified = client.get(f"/imports/status/{job_id}")
    assert unified.status_code == 200
    assert unified.json()["job"]["kind"] == "roleplay"


def test_manga_import_blocking(client: TestClient, tmp_path: Path, monkeypatch):
    archive = _make_manga_archive(tmp_path)
    data_root = tmp_path / "manga_data"
    monkeypatch.setenv("COMFYVN_DATA_ROOT", str(data_root))

    resp = client.post(
        "/manga/import",
        json={"path": str(archive), "blocking": True, "translation": False},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["ok"] is True
    job_id = payload["job"]["id"]
    assert payload.get("logs_path")
    assert Path(payload["logs_path"]).exists()
    summary = payload["import"]
    assert summary["scenes"]
    assert summary["assets"]
    assert summary["summary_path"]
    assert Path(summary["summary_path"]).exists()
    assert summary.get("preview_path")
    assert Path(summary["preview_path"]).exists()
    status = client.get(f"/manga/import/{job_id}")
    assert status.status_code == 200
    unified = client.get(f"/imports/status/{job_id}")
    assert unified.status_code == 200
    assert unified.json()["job"]["kind"] == "manga"
    history = client.get("/manga/imports/history")
    assert history.status_code == 200
    imports = history.json()["imports"]
    assert any(item.get("import_id") == summary["import_id"] for item in imports)
