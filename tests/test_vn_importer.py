import importlib.util
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


HTTPX_AVAILABLE = importlib.util.find_spec("httpx") is not None


@pytest.fixture(autouse=True)
def _stub_reindex(monkeypatch):
    import comfyvn.server.core.vn_importer as importer

    class _IndexerStub:
        def reindex(self):
            return {"ok": True}

    monkeypatch.setattr(importer, "indexer", _IndexerStub(), raising=False)


@pytest.fixture(autouse=True)
def _stub_task_registry(monkeypatch):
    class _Task:
        def __init__(self, task_id: str, kind: str, meta: dict):
            self.id = task_id
            self.kind = kind
            self.status = "queued"
            self.progress = 0.0
            self.message = ""
            self.meta = meta

    class _Registry:
        def __init__(self):
            self._tasks: dict[str, _Task] = {}
            self._counter = 0

        def register(self, kind: str, payload: dict, *, message: str = "", meta: dict | None = None):
            self._counter += 1
            task_id = f"job-{self._counter}"
            task_meta = dict(meta or {})
            task_meta.setdefault("payload", payload)
            task = _Task(task_id, kind, task_meta)
            task.message = message
            self._tasks[task_id] = task
            return task_id

        def update(self, task_id: str, **updates):
            task = self._tasks.get(task_id)
            if not task:
                return
            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)

        def get(self, task_id: str):
            return self._tasks.get(task_id)

        def list(self):
            return list(self._tasks.values())

    registry = _Registry()
    monkeypatch.setattr("comfyvn.server.modules.vn_import_api.task_registry", registry, raising=False)
    monkeypatch.setattr("comfyvn.core.task_registry.task_registry", registry, raising=False)


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


def _build_renpy_package(tmp_path: Path) -> Path:
    manifest = {
        "id": "renpy-demo",
        "title": "RenPy Demo",
        "engine": "RenPy",
    }
    package_path = tmp_path / "renpy.cvnpack"
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("game/script.rpy", "label start:\n    return")
        archive.writestr("scenes/start.json", json.dumps({"scene_id": "start", "lines": []}))
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
    assert summary["adapter"] == "generic"
    assert summary["summary_path"]

    assert (data_root / "scenes" / "demo_scene.json").exists()
    assert (data_root / "characters" / "hero.json").exists()
    assert (data_root / "timelines" / "main.json").exists()
    assert (data_root / "assets" / "backgrounds" / "bg1.png").exists()
    assert (data_root / "imports" / "vn").exists()
    assert Path(summary["summary_path"]).exists()


def test_import_vn_adapter_detection(tmp_path: Path):
    package_path = _build_renpy_package(tmp_path)
    data_root = tmp_path / "renpy_data"

    summary = import_vn_package(package_path, data_root=data_root)

    assert summary["adapter"] == "renpy"
    assert (data_root / "scenes" / "start.json").exists()


@pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
def test_import_vn_api_blocking(tmp_path: Path, monkeypatch):
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
    assert summary["adapter"] == "generic"
    assert Path(summary["summary_path"]).exists()
    assert (data_root / "scenes" / "demo_scene.json").exists()

    status = client.get(f"/vn/import/{payload['job']['id']}")
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload["job"]["status"] == "done"
    assert status_payload["summary"]["scenes"] == ["demo_scene"]
    assert status_payload["summary"]["adapter"] == "generic"


@pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
def test_import_vn_api_job(tmp_path: Path, monkeypatch):
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
    assert summary["adapter"] in {"generic", "renpy"}
    assert (data_root / "scenes" / "demo_scene.json").exists()

    detail = client.get(f"/vn/import/{job_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["job"]["status"] in {"done", "error"}
    if detail_payload["summary"]:
        assert detail_payload["summary"]["scenes"] == ["demo_scene"]
        assert "adapter" in detail_payload["summary"]


@pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
def test_import_history_endpoint(tmp_path: Path, monkeypatch):
    data_root = tmp_path / "history"
    monkeypatch.setenv("COMFYVN_DATA_ROOT", str(data_root))

    from fastapi.testclient import TestClient
    from comfyvn.server.app import create_app

    client = TestClient(create_app())

    pkg1 = _build_sample_package(tmp_path)
    pkg2 = _build_renpy_package(tmp_path)

    for pkg in (pkg1, pkg2):
        resp = client.post("/vn/import", json={"path": str(pkg), "blocking": True})
        assert resp.status_code == 200

    history = client.get("/vn/imports/history", params={"limit": 5})
    assert history.status_code == 200
    data = history.json()
    assert data["ok"] is True
    imports = data["imports"]
    assert len(imports) >= 2
    adapters = {item.get("adapter") for item in imports}
    assert "renpy" in adapters
    assert "generic" in adapters
