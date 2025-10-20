from __future__ import annotations

import sys
import types

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient


# Minimal PySide6 stub for modules that import QAction
if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type("QAction", (), {})
    pyside6.QtGui = qtgui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtGui"] = qtgui


from comfyvn.server.app import create_app


def test_replay_auto_deterministic():
    client = TestClient(create_app())
    branches = [
        ["a", "b", "c"],
        ["x", "y"],
        ["k1", "k2", "k3"],
    ]

    seed_choice = 1
    r1 = client.post("/replay/auto", json={"branches": branches, "seed_choice": seed_choice})
    r2 = client.post("/replay/auto", json={"branches": branches, "seed_choice": seed_choice})
    assert r1.status_code == 200 and r2.status_code == 200
    p1 = r1.json()["path"]
    p2 = r2.json()["path"]
    assert p1 == p2  # same seed -> same path

    r3 = client.post("/replay/auto", json={"branches": branches, "seed_choice": 0})
    assert r3.status_code == 200
    assert r3.json()["path"] != p1  # different seed -> different path

