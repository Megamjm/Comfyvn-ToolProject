import json
import sys
import time
import types
import zipfile
from pathlib import Path

import pytest


def _install_pyside_stubs() -> None:
    if "PySide6" in sys.modules:
        return
    pyside = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")

    class _DummyAction:  # minimal placeholder for QAction usage during imports
        pass

    qtgui.QAction = _DummyAction
    pyside.QtGui = qtgui
    sys.modules["PySide6"] = pyside
    sys.modules["PySide6.QtGui"] = qtgui


_install_pyside_stubs()

from comfyvn.server.core.vn_importer import import_vn_package


def _build_sample_package(tmp_path: Path) -> Path:
    manifest = {
        "id": "demo-project",
        "title": "Demo Project",
        "licenses": [{"name": "CC-BY", "scope": "backgrounds"}],
    }
    scene = {"scene_id": "demo_scene", "title": "Demo", "lines": []}
    character = {"character_id": "hero", "name": "Hero"}
    timeline = {"timeline_id": "main", "scenes": ["demo_scene"]}

    package_path = tmp_path / "demo.cvnpack"
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("scenes/demo_scene.json", json.dumps(scene))
        archive.writestr("characters/hero.json", json.dumps(character))
        archive.writestr("timelines/main.json", json.dumps(timeline))
        archive.writestr("assets/backgrounds/bg1.png", b"fake-png")
        archive.writestr("licenses/NOTICE.txt", "Licensed assets")
    return package_path


def test_import_vn_package(tmp_path: Path):
    package_path = _build_sample_package(tmp_path)
    data_root = tmp_path / "data_root"

    summary = import_vn_package(package_path, data_root=data_root)

    assert summary["scenes"] == ["demo_scene"]
    assert summary["characters"] == ["hero"]
    assert summary["timelines"] == ["main"]
    assert summary["assets"] == ["backgrounds/bg1.png"]
    assert summary["manifest"]["id"] == "demo-project"
    assert summary["licenses"] == [{"name": "CC-BY", "scope": "backgrounds"}]
    assert summary["summary_path"]

    assert (data_root / "scenes" / "demo_scene.json").exists()
    assert (data_root / "characters" / "hero.json").exists()
    assert (data_root / "timelines" / "main.json").exists()
    assert (data_root / "assets" / "backgrounds" / "bg1.png").exists()
    assert (data_root / "imports" / "vn").exists()
    assert Path(summary["summary_path"]).exists()


def test_import_vn_api_blocking(tmp_path: Path, monkeypatch):
    pytest.importorskip("httpx")
    package_path = _build_sample_package(tmp_path)
    data_root = tmp_path / "api_data"
    monkeypatch.setenv("COMFYVN_DATA_ROOT", str(data_root))

    from fastapi.testclient import TestClient
    from comfyvn.server.app import create_app

    client = TestClient(create_app())

    response = client.post("/vn/import", json={"path": str(package_path), "blocking": True})
    assert response.status_code == 200

    payload = response.json()
    assert payload["ok"] is True
    summary = payload["import"]
    assert summary["scenes"] == ["demo_scene"]
    assert summary["characters"] == ["hero"]
    assert Path(summary["summary_path"]).exists()
    assert (data_root / "scenes" / "demo_scene.json").exists()

    status = client.get(f"/vn/import/{payload['job']['id']}")
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload["job"]["status"] == "done"
    assert status_payload["summary"]["scenes"] == ["demo_scene"]


def test_import_vn_api_job(tmp_path: Path, monkeypatch):
    pytest.importorskip("httpx")
    package_path = _build_sample_package(tmp_path)
    data_root = tmp_path / "async_data"
    monkeypatch.setenv("COMFYVN_DATA_ROOT", str(data_root))

    from fastapi.testclient import TestClient
    from comfyvn.server.app import create_app

    client = TestClient(create_app())

    response = client.post("/vn/import", json={"path": str(package_path)})
    assert response.status_code == 200

    payload = response.json()
    assert payload["ok"] is True
    job = payload["job"]
    job_id = job["id"]
    assert job_id

    summary = None
    for _ in range(20):
        status = client.get(f"/jobs/status/{job_id}")
        if status.status_code != 200:
            time.sleep(0.05)
            continue
        job_payload = status.json()["job"]
        if job_payload["status"] == "done":
            summary = (job_payload.get("meta") or {}).get("result")
            break
        if job_payload["status"] == "error":
            error_message = job_payload.get("message") or job_payload.get("meta", {}).get("error")
            pytest.fail(f"job errored: {error_message}")
        time.sleep(0.05)

    assert summary is not None
    assert summary["scenes"] == ["demo_scene"]
    assert (data_root / "scenes" / "demo_scene.json").exists()

    detail = client.get(f"/vn/import/{job_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["job"]["status"] in {"done", "error"}
    if detail_payload["summary"]:
        assert detail_payload["summary"]["scenes"] == ["demo_scene"]
