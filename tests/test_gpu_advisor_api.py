from __future__ import annotations

import sys
import types
from typing import Any

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient


# Minimal PySide6 stub
if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type("QAction", (), {})
    pyside6.QtGui = qtgui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtGui"] = qtgui


from comfyvn.server.app import create_app


class _RegistryStub:
    def __init__(self, providers: list[dict[str, Any]] | None = None) -> None:
        self._providers = providers or []

    def list(self) -> list[dict[str, Any]]:
        return list(self._providers)


class _GPUManagerStub:
    def __init__(self, devices: list[dict[str, Any]] | None = None) -> None:
        self._devices = devices or []
        self._policy = {"mode": "auto", "device": None}
        self.registry = _RegistryStub(
            [
                {
                    "id": "runpod",
                    "name": "RunPod",
                    "service": "runpod",
                    "base_url": "https://api.runpod.io/v2/",
                }
            ]
        )

    def list_all(self, refresh: bool = False):
        return list(self._devices)

    def get_policy(self):
        return dict(self._policy)

    def set_policy(self, mode: str, *, device: str | None = None):
        assert mode in {"auto", "local", "remote", "cpu"}
        self._policy = {"mode": mode, "device": device}
        return self.get_policy()

    def select_device(self, *, prefer: str | None = None, requirements: dict | None = None):
        return {"id": "cpu", "kind": "cpu"}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    from comfyvn.server.modules import gpu_api

    # Start with no local devices for deterministic advice expectations
    gpu_api.GPU_MANAGER = _GPUManagerStub(devices=[])  # type: ignore
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_gpu_advise_prefer_remote_and_local_paths(client: TestClient):
    # With no local devices, prefer_remote True should lean remote/cpu with rationale
    r1 = client.post("/api/gpu/advise", json={"prefer_remote": True, "workload": {"requirements": {"min_vram_gb": 16}}})
    assert r1.status_code == 200, r1.text
    advice1 = r1.json()["advice"]
    assert advice1["choice"] in {"remote", "cpu"}
    assert advice1.get("reason")

    # With a local device injected, prefer_remote False should surface local candidate
    from comfyvn.server.modules import gpu_api

    stub = gpu_api.GPU_MANAGER  # type: ignore
    stub._devices = [
        {"id": "cuda:0", "name": "Stub GPU", "kind": "gpu", "memory_total": 16384, "source": "stub"}
    ]
    r2 = client.post("/api/gpu/advise", json={"prefer_remote": False, "workload": {"requirements": {"min_vram_gb": 8}}})
    assert r2.status_code == 200
    advice2 = r2.json()["advice"]
    assert advice2["choice"] in {"local", "remote", "cpu"}
    assert advice2.get("local_candidate") is not None


def test_gpu_advise_hardware_override_cpu(client: TestClient):
    r = client.post("/api/gpu/advise", json={"hardware_override": True, "workload": {"requirements": {"min_vram_gb": 1}}})
    assert r.status_code == 200
    advice = r.json()["advice"]
    assert advice["choice"] == "cpu"
    assert advice.get("override") in {"cpu", None}

