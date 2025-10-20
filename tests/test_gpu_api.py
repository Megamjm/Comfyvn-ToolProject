from __future__ import annotations

import sys
import types
from typing import Any

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


class _RegistryStub:
    def __init__(self, providers: list[dict[str, Any]] | None = None) -> None:
        self._providers = providers or []

    def list(self) -> list[dict[str, Any]]:
        return list(self._providers)


class _GPUManagerStub:
    def __init__(self) -> None:
        self._devices = [
            {"id": "cuda:0", "name": "Stub GPU", "kind": "gpu", "memory_total": 12288, "source": "stub"},
            {"id": "cpu", "name": "CPU", "kind": "cpu", "memory_total": None, "source": "stub"},
        ]
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
        if prefer == "cpu":
            return {"id": "cpu", "kind": "cpu"}
        # Pick first GPU that meets simple VRAM requirement if provided
        min_vram = None
        if requirements:
            min_vram = requirements.get("min_vram_gb") or requirements.get("min_vram")
        for d in self._devices:
            if d["kind"] == "gpu":
                if min_vram is None:
                    return d
                mem = d.get("memory_total") or 0
                mem_gb = mem / 1024 if mem > 256 else mem
                if mem_gb >= float(min_vram):
                    return d
        return {"id": "cpu", "kind": "cpu"}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    # Monkeypatch the module-level GPU_MANAGER used by the API router
    from comfyvn.server.modules import gpu_api

    gpu_api.GPU_MANAGER = _GPUManagerStub()  # type: ignore
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_gpu_list_and_policy(client: TestClient):
    resp = client.get("/api/gpu/list")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert any(d["kind"] == "gpu" for d in payload["devices"])  # has at least one GPU
    assert payload["policy"]["mode"] in {"auto", "local", "remote", "cpu"}


def test_gpu_advise_local_candidate(client: TestClient):
    # Request a workload that fits the stub GPU; expect 'local' or a local candidate present
    resp = client.post(
        "/api/gpu/advise",
        json={"workload": {"requirements": {"min_vram_gb": 8, "type": "voice_synthesis"}}},
    )
    assert resp.status_code == 200, resp.text
    advice = resp.json()["advice"]
    assert advice["local_candidate"] is not None
    assert advice["choice"] in {"local", "remote", "cpu"}  # choice depends on prefer_remote flag


def test_gpu_select_device(client: TestClient):
    resp = client.post(
        "/api/gpu/select",
        json={"requirements": {"min_vram_gb": 12}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["choice"]["kind"] in {"gpu", "cpu"}

