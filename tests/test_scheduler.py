from __future__ import annotations

import math

from comfyvn.compute.scheduler import JobScheduler


class _RegistryStub:
    def __init__(self) -> None:
        self._items = {
            "remote": {
                "id": "remote",
                "meta": {
                    "cost_per_minute": 0.5,
                    "egress_cost_per_gb": 0.25,
                    "vram_cost_per_gb_minute": 0.05,
                },
            },
            "local": {
                "id": "local",
                "meta": {
                    "cost_per_minute": 0.0,
                },
            },
        }

    def get(self, provider_id: str):
        return self._items.get(provider_id)


def _sched() -> JobScheduler:
    return JobScheduler(registry=_RegistryStub())


def test_priority_preemption_and_fifo() -> None:
    sched = _sched()
    sched.enqueue({"id": "job-low", "priority": 1, "queue": "local"})
    sched.enqueue({"id": "job-high", "priority": 5, "queue": "local"})
    sched.enqueue({"id": "job-low2", "priority": 1, "queue": "local"})

    first = sched.claim("local")
    assert first is not None and first["id"] == "job-high"

    second = sched.claim("local")
    assert second is not None and second["id"] == "job-low"

    third = sched.claim("local")
    assert third is not None and third["id"] == "job-low2"


def test_sticky_device_honors_hint() -> None:
    sched = _sched()
    sched.enqueue(
        {
            "id": "job-sticky",
            "queue": "remote",
            "sticky_device": True,
            "device_id": "remote:runpod-a",
        }
    )
    claimed = sched.claim("remote", device_id="remote:runpod-b")
    assert claimed is not None
    assert claimed["device_id"] == "remote:runpod-a"
    assert claimed["sticky_device_id"] == "remote:runpod-a"


def test_completion_records_cost_and_metrics() -> None:
    sched = _sched()
    sched.enqueue(
        {
            "id": "job-telemetry",
            "queue": "remote",
            "provider_id": "remote",
            "vram_gb": 12,
        }
    )
    sched.claim("remote", device_id="remote:runpod-x")
    done = sched.complete(
        "job-telemetry",
        bytes_tx=1024**3,
        bytes_rx=512**3,
        duration_sec=180,
    )
    assert math.isclose(done["duration_sec"], 180.0, rel_tol=1e-6)
    assert done["bytes_tx"] == 1024**3
    assert done["bytes_rx"] == 512**3
    assert done["vram_gb"] == 12
    assert done["cost_estimate"] is not None
    assert done["cost_estimate"] > 0

    state = sched.state()
    assert state["completed"]
    entry = state["completed"][0]
    assert entry["cost_estimate"] == done["cost_estimate"]
    assert entry["duration_sec"] == done["duration_sec"]

    board = sched.board()
    seg = next(seg for seg in board["jobs"] if seg["id"] == "job-telemetry")
    assert seg["duration_sec"] == done["duration_sec"]
