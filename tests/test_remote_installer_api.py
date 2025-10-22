from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

# Stub PySide6 so FastAPI routes importing Qt helpers do not fail in CI.
if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type("QAction", (), {})
    pyside6.QtGui = qtgui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtGui"] = qtgui

from comfyvn.server.app import create_app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    status_root = tmp_path / "status"
    log_root = tmp_path / "logs"
    monkeypatch.setenv("COMFYVN_REMOTE_INSTALL_STATUS_ROOT", str(status_root))
    monkeypatch.setenv("COMFYVN_REMOTE_INSTALL_LOG_ROOT", str(log_root))
    monkeypatch.setattr(
        "comfyvn.server.routes.remote_orchestrator.is_enabled",
        lambda name, **_: True,
    )
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_remote_install_idempotent(client: TestClient):
    payload = {"host": "gpu.example.com", "modules": ["comfyui"]}

    resp = client.post("/api/remote/install", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["ok"] is True
    assert data["status"] == "installed"
    assert data["installed"] == ["comfyui"]
    assert "plan" in data and data["plan"][0]["action"] == "install"

    status_file = Path(data["status_path"])
    log_file = Path(data["log_path"])

    assert status_file.exists()
    assert log_file.exists()
    status_info = _read_json(status_file)
    assert status_info["modules"]["comfyui"]["state"] == "installed"

    # Re-run should be a no-op.
    resp2 = client.post("/api/remote/install", json=payload)
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["status"] == "noop"
    assert data2["installed"] == []
    assert "comfyui" in data2["skipped"]
    assert data2["plan"][0]["action"] == "noop"

    log_lines = log_file.read_text(encoding="utf-8").splitlines()
    assert any("install begin" in line for line in log_lines)
    assert any("no-op" in line for line in log_lines)


def test_remote_install_dry_run(client: TestClient):
    payload = {"host": "dry-run.local", "modules": ["ollama"], "dry_run": True}
    resp = client.post("/api/remote/install", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "dry_run"
    assert data["plan"][0]["module"] == "ollama"
    assert data["plan"][0]["action"] == "install"

    status_path = Path(data["status_path"])
    assert not status_path.exists()
