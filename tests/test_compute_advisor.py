from __future__ import annotations

from pathlib import Path

from comfyvn.core.compute_advisor import advise
from comfyvn.core.gpu_manager import GPUManager
from comfyvn.core.settings_manager import SettingsManager


def _dummy_manager(tmp_path: Path) -> GPUManager:
    settings = SettingsManager(
        path=tmp_path / "settings.json", db_path=tmp_path / "settings.db"
    )
    manager = GPUManager(
        config_path=tmp_path / "gpu_policy.json",
        settings_manager=settings,
    )
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
    assert advice["analysis"]["workload_type"] == "voice_synthesis"
    assert advice["job_summary"]["choice"] == "local"


def test_compute_advise_remote(tmp_path):
    manager = _dummy_manager(tmp_path)
    manager.registry.register(
        {
            "id": "lambda",
            "name": "Lambda Labs",
            "kind": "remote",
            "service": "lambda",
            "base_url": "https://cloud.lambdalabs.com/api/v1/",
        }
    )
    manager._devices = []
    manager.list_all = lambda refresh=False: list(manager._devices)  # type: ignore
    advice = advise(
        manager,
        workload={
            "requirements": {"min_vram_gb": 24, "type": "cg_batch"},
            "assets": [{"size_mb": 2500}],
            "estimate": {"duration_minutes": 180},
        },
        prefer_remote=True,
    )
    assert advice["choice"] == "remote"
    assert advice["remote_candidate"]
    assert advice["remote_candidate"]["id"] == "lambda"
    assert advice["remote_candidate"]["policy_hint"]
    assert advice["estimated_cost"]
    assert advice["analysis"]["total_asset_mb"] > 0
    assert advice["job_summary"]["estimated_cost"] == advice["estimated_cost"]


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
    assert advice["job_summary"]["choice"] == "cpu"
