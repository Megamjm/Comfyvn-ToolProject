from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from comfyvn.core import compute_scheduler


class _RegistryStub:
    def __init__(self) -> None:
        self._providers: Dict[str, Dict[str, Any]] = {
            "runpod": {
                "id": "runpod",
                "name": "RunPod",
                "service": "runpod",
                "base_url": "https://api.runpod.io/v2/",
                "meta": {"min_vram_gb": 16},
            },
            "local": {
                "id": "local",
                "name": "Local GPU",
                "service": "comfyui",
                "base_url": "http://127.0.0.1:8188",
                "meta": {},
            },
        }

    def get(self, provider_id: str) -> Optional[Dict[str, Any]]:
        entry = self._providers.get(provider_id)
        return dict(entry) if entry else None


class _GPUManagerStub:
    def __init__(self) -> None:
        self.registry = _RegistryStub()
        self._devices = [
            {
                "id": "cuda:0",
                "name": "Stub GPU",
                "kind": "gpu",
                "memory_total": 24576,
                "available": True,
                "source": "stub",
            },
            {
                "id": "remote:runpod",
                "name": "RunPod",
                "kind": "remote",
                "available": True,
                "meta": {"priority": 10},
                "last_health": {"ok": True},
            },
            {"id": "cpu", "name": "CPU", "kind": "cpu", "available": True},
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
                "kind": "cpu",
            }
        if prefer == "remote:runpod":
            return {
                "id": "remote:runpod",
                "device": "remote:runpod",
                "policy": "auto",
                "reason": "preferred",
                "kind": "remote",
                "provider_id": "runpod",
            }
        return {
            "id": "cuda:0",
            "device": "cuda:0",
            "policy": "auto",
            "reason": "auto",
            "kind": "gpu",
            "memory_total": 24576,
        }


@pytest.fixture()
def gpu_manager_stub(monkeypatch: pytest.MonkeyPatch) -> _GPUManagerStub:
    stub = _GPUManagerStub()
    monkeypatch.setattr(compute_scheduler, "GPU_MANAGER", stub)
    monkeypatch.setattr(compute_scheduler, "REGISTRY", stub.registry)
    return stub


def test_choose_device_prefers_local_gpu(
    monkeypatch: pytest.MonkeyPatch, gpu_manager_stub: _GPUManagerStub
):
    def fake_advise(
        manager, workload=None, prefer_remote=False, hardware_override=False
    ):
        return {
            "choice": "gpu",
            "reason": "Local GPU available",
            "remote_candidate": None,
            "analysis": {},
            "job_summary": {},
        }

    monkeypatch.setattr(compute_scheduler, "compute_advise", fake_advise)
    decision = compute_scheduler.choose_device({"requirements": {"min_vram_gb": 12}})
    assert decision["choice"] == "gpu"
    assert decision["selection"]["device"] == "cuda:0"
    assert "Local GPU" in decision["reason"]


def test_choose_device_prefers_remote_when_requested(
    monkeypatch: pytest.MonkeyPatch, gpu_manager_stub: _GPUManagerStub
):
    def fake_advise(
        manager, workload=None, prefer_remote=False, hardware_override=False
    ):
        return {
            "choice": "remote",
            "reason": "Queue depth high",
            "remote_candidate": {"id": "runpod", "name": "RunPod"},
            "analysis": {},
            "job_summary": {},
        }

    monkeypatch.setattr(compute_scheduler, "compute_advise", fake_advise)
    decision = compute_scheduler.choose_device(
        {"requirements": {"min_vram_gb": 24}},
        context={"prefer_remote": True},
    )
    assert decision["choice"] == "remote"
    assert decision["selection"]["device"] == "remote:runpod"
    assert decision["remote_provider"]["id"] == "runpod"
    assert "RunPod" in decision["reason"]
