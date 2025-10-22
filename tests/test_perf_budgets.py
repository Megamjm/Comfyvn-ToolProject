from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest

from comfyvn.perf.budgets import BudgetManager


class MetricsProbe:
    def __init__(self) -> None:
        self.data: Dict[str, Any] = {
            "ok": True,
            "cpu": 40.0,
            "mem_used_mb": 512.0,
            "mem_total_mb": 4096.0,
            "gpus": [{"mem_used": 128.0, "mem_total": 8192.0}],
            "first_gpu": {"mem_used": 128.0, "mem_total": 8192.0},
        }

    def __call__(self) -> Dict[str, Any]:
        return dict(self.data)

    def set(self, **kwargs: Any) -> None:
        self.data.update(kwargs)


def _ensure_transition(
    transitions: List[Dict[str, Any]], job_id: str, expected: str
) -> None:
    match = next((item for item in transitions if item["job"]["id"] == job_id), None)
    assert match, f"No transition entry for job {job_id}"
    assert match["queue_state"] == expected


def test_budget_manager_delays_and_releases_jobs():
    metrics = MetricsProbe()
    manager = BudgetManager(metrics_provider=metrics)
    manager.configure(
        max_cpu_percent=80.0,
        max_running_jobs=1,
        max_queue_depth=4,
        evaluation_interval=0.0,
    )

    result = manager.register_job("job-1", kind="render", payload={})
    assert result["queue_state"] == "queued"
    manager.mark_started("job-1")

    metrics.set(cpu=78.0)
    result = manager.register_job(
        "job-2", kind="render", payload={"perf": {"cpu_percent": 10.0}}
    )
    assert result["queue_state"] == "delayed"
    manager.refresh_queue()

    metrics.set(cpu=40.0)
    manager.mark_finished("job-1")
    transitions = manager.refresh_queue()
    _ensure_transition(transitions, "job-2", "queued")

    manager.mark_started("job-2")
    finished = manager.mark_finished("job-2")
    assert finished is not None
    assert finished.status == "complete"


def test_lazy_asset_trimming_invokes_unload_handler():
    metrics = MetricsProbe()
    evicted: List[str] = []

    def on_unload(payload: Dict[str, Any]) -> None:
        evicted.append(payload["asset_id"])

    manager = BudgetManager(metrics_provider=metrics)
    manager.configure(max_mem_mb=600, lazy_asset_target_mb=32)
    manager.register_asset(
        "asset-1",
        size_mb=128.0,
        metadata={"path": "foo/bar"},
        unload_callback=on_unload,
    )
    manager.touch_asset("asset-1")

    metrics.set(mem_used_mb=900.0)
    manager.refresh_queue()  # triggers lazy trim

    assert "asset-1" in evicted
