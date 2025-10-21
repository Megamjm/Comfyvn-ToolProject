from __future__ import annotations

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
    manager = SettingsManager(config_path)
    manager.save(
        {
            "ui": {"menu_sort_mode": "load_order", "theme": "dark"},
            "developer": {"verbose": False, "toasts": True},
            "server": {"local_port": 8001, "auto_start": True},
        }
    )
    monkeypatch.setattr(settings_api, "_settings", manager, raising=False)

    app = create_app()
    with TestClient(app) as client:
        resp = client.post("/settings/save", json={"ui": {"menu_sort_mode": "alphabetical"}})
        assert resp.status_code == 200, resp.text
        saved = manager.load()
        assert saved["ui"]["menu_sort_mode"] == "alphabetical"
        assert saved["ui"]["theme"] == "dark"

        resp = client.post("/settings/save", json={"server": {"local_port": 9002}})
        assert resp.status_code == 200, resp.text
        saved = manager.load()
        assert saved["server"]["local_port"] == 9002
        assert saved["server"]["auto_start"] is True
