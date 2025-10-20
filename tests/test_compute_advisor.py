from __future__ import annotations

from pathlib import Path

from comfyvn.core.gpu_manager import GPUManager
from comfyvn.core.compute_advisor import advise


def _dummy_manager(tmp_path: Path) -> GPUManager:
    manager = GPUManager(config_path=tmp_path / "gpu_policy.json")
    manager.registry.register(
        {
            "id": "runpod",
            "name": "RunPod",
            "kind": "remote",
            "service": "runpod",
            "base_url": "https://api.runpod.io/v2/",
        }
    )
    return manager


def test_compute_advise_local(tmp_path):
    manager = _dummy_manager(tmp_path)
    # Inject fake local GPU entry
    manager._devices = [
        {
            "id": "cuda:0",
            "name": "Test GPU",
            "kind": "gpu",
            "memory_total": 16384,
            "source": "mock",
        }
    ]
    manager.list_all = lambda refresh=False: list(manager._devices)  # type: ignore
    advice = advise(
        manager,
        workload={"requirements": {"min_vram_gb": 8, "type": "voice_synthesis"}},
    )
    assert advice["choice"] == "local"
    assert advice["local_candidate"] is not None


def test_compute_advise_remote(tmp_path):
    manager = _dummy_manager(tmp_path)
    manager._devices = []
    manager.list_all = lambda refresh=False: list(manager._devices)  # type: ignore
    advice = advise(
        manager,
        workload={"requirements": {"min_vram_gb": 20}},
        prefer_remote=True,
    )
    assert advice["choice"] in {"remote", "cpu"}
    assert advice["reason"]


def test_compute_advise_hardware_override(tmp_path):
    manager = _dummy_manager(tmp_path)
    manager._devices = []
    manager.list_all = lambda refresh=False: list(manager._devices)  # type: ignore
    advice = advise(
        manager,
        workload={"requirements": {"min_vram_gb": 10}},
        hardware_override=True,
    )
    assert advice["choice"] == "cpu"
    assert advice.get("override") == "cpu"
