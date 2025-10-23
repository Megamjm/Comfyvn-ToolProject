from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type("QAction", (), {})
    pyside6.QtGui = qtgui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtGui"] = qtgui

from comfyvn.app import create_app
from comfyvn.core.settings_manager import SettingsManager
from comfyvn.server.modules import settings_api


def test_settings_save_deep_merge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_path = tmp_path / "config.json"
    db_path = tmp_path / "settings.db"
    manager = SettingsManager(path=config_path, db_path=db_path)
    manager.save(
        {
            "ui": {"menu_sort_mode": "load_order", "theme": "dark"},
            "developer": {"verbose": False, "toasts": True},
            "server": {"local_port": 8001, "auto_start": True},
        }
    )
    monkeypatch.setattr(settings_api, "_settings", manager, raising=False)
    monkeypatch.setattr(
        settings_api,
        "write_runtime_authority",
        lambda host, port: str(tmp_path / f"runtime_state_{port}.json"),
        raising=False,
    )
    monkeypatch.setattr(
        settings_api.ports_config,
        "get_config",
        lambda: {"host": "127.0.0.1", "ports": [8001, 8000], "public_base": None},
        raising=False,
    )
    monkeypatch.setattr(
        settings_api.ports_config,
        "set_config",
        lambda host, ports, public_base: {
            "host": host,
            "ports": list(ports),
            "public_base": public_base,
        },
        raising=False,
    )
    monkeypatch.setattr(
        settings_api.ports_config,
        "record_runtime_state",
        lambda **_kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        settings_api,
        "find_open_port",
        lambda host, start: start,
        raising=False,
    )

    authority = types.SimpleNamespace(
        host="127.0.0.1", port=8001, base_url="http://127.0.0.1:8001"
    )
    monkeypatch.setattr(
        settings_api,
        "current_authority",
        lambda refresh=False: authority,
        raising=False,
    )

    app = create_app()
    with TestClient(app) as client:
        resp = client.post(
            "/system/settings", json={"ui": {"menu_sort_mode": "alphabetical"}}
        )
        assert resp.status_code == 200, resp.text
        saved = manager.load()
        assert saved["ui"]["menu_sort_mode"] == "alphabetical"
        assert saved["ui"]["theme"] == "dark"

        resp = client.post("/system/settings", json={"server": {"local_port": 9002}})
        assert resp.status_code == 200, resp.text
        saved = manager.load()
        assert saved["server"]["local_port"] == 9002
        assert saved["server"]["auto_start"] is True


def test_settings_save_updates_runtime_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config_path = tmp_path / "config.json"
    db_path = tmp_path / "settings.db"
    manager = SettingsManager(path=config_path, db_path=db_path)
    manager.save(
        {
            "server": {
                "local_port": 8001,
                "host": "0.0.0.0",
                "base_url": "http://0.0.0.0:8001",
            }
        }
    )
    monkeypatch.setattr(settings_api, "_settings", manager, raising=False)

    captured: dict[str, object] = {}

    def fake_write_runtime(host: str, port: int) -> str:
        captured["host"] = host
        captured["port"] = port
        return str(tmp_path / "runtime_state.json")

    def fake_find(host: str, start: int) -> int:
        calls = captured.setdefault("find_calls", [])
        if isinstance(calls, list):
            calls.append((host, start))
        return 8100

    authority = types.SimpleNamespace(
        host="127.0.0.1", port=8001, base_url="http://127.0.0.1:8001"
    )
    monkeypatch.setattr(settings_api, "write_runtime_authority", fake_write_runtime)
    monkeypatch.setattr(settings_api, "find_open_port", fake_find)
    monkeypatch.setattr(
        settings_api.ports_config,
        "get_config",
        lambda: {"host": "0.0.0.0", "ports": [8001, 8000], "public_base": None},
        raising=False,
    )
    captured_set: dict[str, object] = {}

    def fake_set_config(host, ports, public_base):
        captured_set["host"] = host
        captured_set["ports"] = list(ports)
        captured_set["public_base"] = public_base
        return {"host": host, "ports": list(ports), "public_base": public_base}

    monkeypatch.setattr(
        settings_api.ports_config, "set_config", fake_set_config, raising=False
    )
    monkeypatch.setattr(
        settings_api.ports_config,
        "record_runtime_state",
        lambda **kwargs: captured_set.setdefault("runtime", kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        settings_api,
        "current_authority",
        lambda refresh=False: authority,
        raising=False,
    )
    monkeypatch.delenv("COMFYVN_SERVER_BASE", raising=False)
    monkeypatch.delenv("COMFYVN_BASE_URL", raising=False)
    monkeypatch.delenv("COMFYVN_SERVER_HOST", raising=False)
    monkeypatch.delenv("COMFYVN_SERVER_PORT", raising=False)

    app = create_app()
    with TestClient(app) as client:
        resp = client.post("/system/settings", json={"server": {"local_port": 8001}})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    saved = manager.load()
    assert saved["server"]["local_port"] == 8100
    assert saved["server"]["host"] == "127.0.0.1"
    assert saved["server"]["base_url"] == "http://127.0.0.1:8100"

    assert captured.get("host") == "127.0.0.1"
    assert captured.get("port") == 8100
    assert captured.get("find_calls") == [("127.0.0.1", 8001)]
    assert captured_set["host"] == "0.0.0.0"
    assert captured_set["ports"][0] == 8100
    runtime_state = captured_set["runtime"]
    assert runtime_state["host"] == "0.0.0.0"
    assert runtime_state["active_port"] == 8100

    base_env = os.environ["COMFYVN_SERVER_BASE"]
    assert base_env == "http://127.0.0.1:8100"
    assert os.environ["COMFYVN_BASE_URL"] == base_env
    assert os.environ["COMFYVN_SERVER_HOST"] == "127.0.0.1"
    assert os.environ["COMFYVN_SERVER_PORT"] == "8100"

    assert body["settings"]["server"]["local_port"] == 8100


def test_settings_schema_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_path = tmp_path / "config.json"
    db_path = tmp_path / "settings.db"
    manager = SettingsManager(path=config_path, db_path=db_path)
    monkeypatch.setattr(settings_api, "_settings", manager, raising=False)

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/system/settings/schema")
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert "schema" in payload
        assert "defaults" in payload
        assert payload["defaults"]["developer"]["verbose"] is True
