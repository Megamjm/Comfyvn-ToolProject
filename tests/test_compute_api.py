from __future__ import annotations

import sys
import types
from typing import Any

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

# Stub PySide6 so router imports succeed.
if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type("QAction", (), {})
    pyside6.QtGui = qtgui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtGui"] = qtgui

from comfyvn.server.app import create_app


class _RegistryStub:
    def __init__(self) -> None:
        self._providers = [
            {
                "id": "runpod",
                "name": "RunPod",
                "kind": "remote",
                "service": "runpod",
                "base_url": "https://api.runpod.io/v2/",
                "meta": {
                    "min_vram_gb": 12,
                    "policy_hints": {
                        "tts": "Remote GPU recommended for TTS workloads."
                    },
                },
                "active": True,
            }
        ]

    def list(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._providers]


class _GPUManagerStub:
    def __init__(self) -> None:
        self.registry = _RegistryStub()
        self._devices = [
            {
                "id": "cuda:0",
                "name": "Stub GPU",
                "kind": "gpu",
                "memory_total": 24576,
                "source": "stub",
            },
            {
                "id": "cpu",
                "name": "CPU",
                "kind": "cpu",
                "memory_total": None,
                "source": "stub",
            },
        ]
        self._policy = {"mode": "auto"}

    def list_all(self, refresh: bool = False):
        return list(self._devices)

    def select_device(
        self, *, prefer: str | None = None, requirements: dict | None = None
    ):
        if prefer == "cpu":
            return {
                "id": "cpu",
                "device": "cpu",
                "policy": "manual",
                "reason": "preferred",
            }
        return {"id": "cuda:0", "device": "cuda:0", "policy": "auto", "reason": "auto"}

    def get_policy(self):
        return dict(self._policy)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    from comfyvn.server.modules import compute_api

    compute_api.GPU_MANAGER = _GPUManagerStub()  # type: ignore[assignment]
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_compute_advise_get_local_choice(client: TestClient):
    resp = client.get("/compute/advise", params={"task": "img", "size": "1024mb"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["target"] in {"gpu", "remote", "cpu"}
    assert isinstance(data["rationale"], str)
    assert data["choice"] in {"gpu", "remote", "cpu", "local"}


def test_compute_advise_get_prefer_remote(client: TestClient):
    resp = client.get(
        "/compute/advise", params={"task": "tts", "prefer_remote": "true"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["target"] in {"remote", "cpu"}
    assert isinstance(data["rationale"], str)


def test_compute_advise_cpu_override(client: TestClient):
    resp = client.get(
        "/compute/advise", params={"task": "img", "hardware_override": "true"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["target"] == "cpu"
    assert "cpu" in data["rationale"].lower()
