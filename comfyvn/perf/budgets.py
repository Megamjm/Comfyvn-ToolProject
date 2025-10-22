from __future__ import annotations

"""
Budget orchestration for CPU/VRAM constrained workloads.

The ``BudgetManager`` keeps track of the in-flight job queue, evaluates
resource pressure (CPU, RAM, VRAM), coordinates lazy asset unloads, and emits
modder-friendly hook envelopes whenever the state changes.  The implementation
is deliberately side-effect light so it can run in both the FastAPI process and
offline tooling (tests, workers) without requiring Redis or GUI dependencies.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    Iterable,
    List,
    MutableMapping,
    Optional,
    Tuple,
)

try:  # FastAPI server metric helper; optional when running in isolation.
    from comfyvn.server.system_metrics import collect_system_metrics as _collect_metrics
except Exception:  # pragma: no cover - defensive fallback
    _collect_metrics = None  # type: ignore

try:
    from comfyvn.core import modder_hooks
except Exception:  # pragma: no cover - defensive fallback
    modder_hooks = None  # type: ignore

try:  # psutil is optional; guard import for environments without it.
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None  # type: ignore

LOGGER = logging.getLogger(__name__)


# --------------------------------------------------------------------------- Data
@dataclass
class BudgetLimits:
    """Upper bounds for runtime resource usage."""

    max_cpu_percent: float = 85.0
    max_mem_mb: int = 0  # 0 → unlimited
    max_vram_mb: int = 0  # 0 → unlimited
    max_running_jobs: int = 3
    max_queue_depth: int = 128
    lazy_asset_target_mb: int = 512
    evaluation_interval: float = 2.0


@dataclass
class ResourceRequirements:
    """Estimated resource footprint for a queued job."""

    cpu_percent: float = 0.0
    ram_mb: float = 0.0
    vram_mb: float = 0.0

    @classmethod
    def from_payload(
        cls, payload: MutableMapping[str, Any] | None
    ) -> "ResourceRequirements":
        data = (
            (payload or {}).get("perf") if isinstance(payload, MutableMapping) else None
        )
        if not isinstance(data, MutableMapping):
            return cls()
        cpu = float(data.get("cpu_percent", 0.0) or 0.0)
        ram = float(data.get("ram_mb", data.get("memory_mb", 0.0)) or 0.0)
        vram = float(data.get("vram_mb", data.get("gpu_mem_mb", 0.0)) or 0.0)
        return cls(
            cpu_percent=max(cpu, 0.0), ram_mb=max(ram, 0.0), vram_mb=max(vram, 0.0)
        )


@dataclass
class JobRecord:
    job_id: str
    kind: str
    payload: Dict[str, Any]
    requirements: ResourceRequirements = field(default_factory=ResourceRequirements)
    status: str = "queued"  # queued | delayed | running | complete | canceled | error
    submitted_at: float = field(default_factory=time.time)
    last_transition: float = field(default_factory=time.time)
    reason: Optional[str] = None

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "id": self.job_id,
            "type": self.kind,
            "status": self.status,
            "reason": self.reason,
            "submitted_at": self.submitted_at,
            "last_transition": self.last_transition,
            "requirements": {
                "cpu_percent": self.requirements.cpu_percent,
                "ram_mb": self.requirements.ram_mb,
                "vram_mb": self.requirements.vram_mb,
            },
        }


@dataclass
class AssetHandle:
    asset_id: str
    size_mb: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    unload_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    loaded: bool = True
    last_used: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_used = time.time()


# ----------------------------------------------------------------------- Utilities
def _fallback_collect_metrics() -> Dict[str, Any]:
    if psutil is None:  # pragma: no cover - minimal fallback
        return {
            "ok": False,
            "cpu": 0.0,
            "mem": 0.0,
            "mem_used_mb": 0,
            "mem_total_mb": 0,
            "gpus": [],
            "first_gpu": None,
            "timestamp": time.time(),
        }

    cpu_percent = float(psutil.cpu_percent(interval=0.05))
    mem_info = psutil.virtual_memory()
    metrics: Dict[str, Any] = {
        "ok": True,
        "cpu": round(cpu_percent, 2),
        "mem": round(float(mem_info.percent), 2),
        "mem_used_mb": int(mem_info.used // (1024 * 1024)),
        "mem_total_mb": int(mem_info.total // (1024 * 1024)),
        "gpus": [],
        "first_gpu": None,
        "timestamp": time.time(),
    }
    return metrics


def _default_metrics_provider() -> Dict[str, Any]:
    if _collect_metrics:
        try:
            return _collect_metrics()
        except Exception:  # pragma: no cover - defensive fallback
            LOGGER.warning(
                "collect_system_metrics failed; falling back to psutil", exc_info=True
            )
    return _fallback_collect_metrics()


# -------------------------------------------------------------------- BudgetManager
class BudgetManager:
    """Coordinates CPU/VRAM budgets, job queue gating, and lazy asset trimming."""

    def __init__(
        self,
        *,
        metrics_provider: Callable[[], Dict[str, Any]] | None = None,
    ) -> None:
        self._limits = BudgetLimits()
        self._metrics_provider = metrics_provider or _default_metrics_provider
        self._lock = threading.RLock()
        self._jobs: Dict[str, JobRecord] = {}
        self._queued: Deque[str] = deque()
        self._delayed: Deque[str] = deque()
        self._running: Dict[str, JobRecord] = {}
        self._assets: Dict[str, AssetHandle] = {}
        self._api_asset_unload: Optional[Callable[[Dict[str, Any]], None]] = None
        self._last_eval: float = 0.0

    # ----------------------------------------------------------------- Configuration
    def configure(self, **kwargs: Any) -> BudgetLimits:
        limits = dict(self._limits.__dict__)
        limits.update({k: v for k, v in kwargs.items() if k in limits})
        self._limits = BudgetLimits(**limits)
        LOGGER.info("BudgetManager limits updated: %s", self._limits)
        self._emit_budget_event("limits.updated", {"limits": self._limits.__dict__})
        return self._limits

    def limits(self) -> BudgetLimits:
        return self._limits

    def set_api_asset_unload_handler(
        self, handler: Optional[Callable[[Dict[str, Any]], None]]
    ) -> None:
        """Install a handler invoked when API-registered assets are lazily unloaded."""
        self._api_asset_unload = handler

    # --------------------------------------------------------------------- Job Queue
    def register_job(
        self,
        job_id: str,
        *,
        kind: str,
        payload: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Register a job submission and evaluate whether it can run immediately."""
        payload = dict(payload or {})
        requirements = ResourceRequirements.from_payload(payload)

        with self._lock:
            if job_id in self._jobs:
                record = self._jobs[job_id]
                record.payload.update(payload)
                record.requirements = requirements
                LOGGER.debug("Updated existing job %s", job_id)
            else:
                record = JobRecord(
                    job_id=job_id, kind=kind, payload=payload, requirements=requirements
                )
                self._jobs[job_id] = record

            metrics = self._metrics_provider()
            queue_state, reason = self._evaluate_job(record, metrics)
            record.status = queue_state
            record.reason = reason
            record.last_transition = time.time()

            if queue_state == "queued":
                self._queued.append(record.job_id)
            else:
                self._delayed.append(record.job_id)

            state = self._snapshot_locked(metrics)

        self._emit_budget_event(
            "job.registered",
            {
                "job": record.to_public_dict(),
                "queue_state": queue_state,
                "reason": reason,
                "metrics": state["metrics"],
            },
        )
        return {
            "queue_state": queue_state,
            "reason": reason,
            "metrics": state["metrics"],
            "limits": state["limits"],
        }

    def mark_started(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            record = self._jobs.get(job_id)
            if not record:
                return None
            if record.status not in {"queued", "delayed"}:
                return record
            try:
                self._queued.remove(job_id)
            except ValueError:
                try:
                    self._delayed.remove(job_id)
                except ValueError:
                    pass
            record.status = "running"
            record.last_transition = time.time()
            self._running[job_id] = record
            LOGGER.debug("Job %s marked running", job_id)
        self._emit_budget_event("job.started", {"job": record.to_public_dict()})
        return record

    def mark_finished(
        self, job_id: str, *, status: str = "complete", reason: Optional[str] = None
    ) -> Optional[JobRecord]:
        with self._lock:
            record = self._jobs.get(job_id)
            if not record:
                return None
            record.status = status
            record.reason = reason
            record.last_transition = time.time()
            self._running.pop(job_id, None)
            try:
                self._queued.remove(job_id)
            except ValueError:
                pass
            try:
                self._delayed.remove(job_id)
            except ValueError:
                pass
            LOGGER.debug("Job %s finished (status=%s)", job_id, status)
            metrics = self._metrics_provider()
            state = self._snapshot_locked(metrics)
        self._emit_budget_event(
            "job.finished",
            {
                "job": record.to_public_dict(),
                "metrics": state["metrics"],
                "status": status,
            },
        )
        return record

    def refresh_queue(self) -> List[Dict[str, Any]]:
        """
        Re-evaluate delayed jobs against current metrics, returning transition envelopes.

        Returns a list of ``{"job": <JobRecord>, "queue_state": "...", "reason": "..."}``.
        """
        transitions: List[Dict[str, Any]] = []
        with self._lock:
            now = time.time()
            if (
                now - self._last_eval < self._limits.evaluation_interval
                and self._delayed
            ):
                # Skip tight polling; callers can force explicit evaluation by calling
                # ``refresh_queue`` again after the interval.
                return transitions
            self._last_eval = now

            metrics = self._metrics_provider()
            self._maybe_trim_assets(metrics)

            pending_ids = list(self._delayed)
            for job_id in pending_ids:
                record = self._jobs.get(job_id)
                if not record:
                    try:
                        self._delayed.remove(job_id)
                    except ValueError:
                        pass
                    continue
                queue_state, reason = self._evaluate_job(record, metrics)
                record.status = queue_state
                record.reason = reason
                record.last_transition = time.time()
                if queue_state == "queued":
                    try:
                        self._delayed.remove(job_id)
                    except ValueError:
                        pass
                    self._queued.append(job_id)
                transitions.append(
                    {
                        "job": record.to_public_dict(),
                        "queue_state": queue_state,
                        "reason": reason,
                    }
                )

            state = self._snapshot_locked(metrics)

        if transitions:
            self._emit_budget_event(
                "queue.refreshed",
                {
                    "transitions": transitions,
                    "metrics": state["metrics"],
                },
            )
        return transitions

    # --------------------------------------------------------------------- Snapshot
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            metrics = self._metrics_provider()
            self._maybe_trim_assets(metrics)
            return self._snapshot_locked(metrics)

    def _snapshot_locked(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        jobs_state = [record.to_public_dict() for record in self._jobs.values()]
        assets_state = [
            {
                "asset_id": handle.asset_id,
                "size_mb": handle.size_mb,
                "loaded": handle.loaded,
                "last_used": handle.last_used,
                "metadata": handle.metadata,
            }
            for handle in self._assets.values()
        ]
        snapshot = {
            "limits": self._limits.__dict__,
            "metrics": metrics,
            "jobs": jobs_state,
            "queued_ids": list(self._queued),
            "delayed_ids": list(self._delayed),
            "running_ids": list(self._running.keys()),
            "assets": assets_state,
        }
        return snapshot

    def health(self) -> Dict[str, Any]:
        """Return a lightweight health summary without the full job payload."""
        with self._lock:
            metrics = self._metrics_provider()
            health = {
                "limits": self._limits.__dict__,
                "queue": {
                    "queued": len(self._queued),
                    "delayed": len(self._delayed),
                    "running": len(self._running),
                    "seen_jobs": len(self._jobs),
                },
                "assets": {
                    "registered": len(self._assets),
                    "loaded": sum(
                        1 for handle in self._assets.values() if handle.loaded
                    ),
                },
                "last_evaluation": self._last_eval,
                "metrics": metrics,
            }
        return health

    # ------------------------------------------------------------------ Asset Hooks
    def register_asset(
        self,
        asset_id: str,
        *,
        size_mb: float,
        metadata: Optional[Dict[str, Any]] = None,
        unload_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AssetHandle:
        handle = AssetHandle(
            asset_id=asset_id,
            size_mb=max(size_mb, 0.0),
            metadata=dict(metadata or {}),
            unload_callback=unload_callback,
        )
        with self._lock:
            self._assets[asset_id] = handle
        LOGGER.debug("Registered lazy asset %s (size=%.2fMB)", asset_id, handle.size_mb)
        self._emit_budget_event(
            "asset.registered",
            {
                "asset": {
                    "asset_id": asset_id,
                    "size_mb": handle.size_mb,
                    "metadata": handle.metadata,
                }
            },
        )
        return handle

    def touch_asset(self, asset_id: str) -> Optional[AssetHandle]:
        with self._lock:
            handle = self._assets.get(asset_id)
            if not handle:
                return None
            handle.touch()
            handle.loaded = True
        LOGGER.debug("Asset %s marked as used", asset_id)
        return handle

    def evict_lazy_assets(self, *, target_mb: float) -> List[Dict[str, Any]]:
        """Evict least-recently-used assets until ``target_mb`` has been freed."""
        freed_mb = 0.0
        events: List[Dict[str, Any]] = []
        with self._lock:
            handles = sorted(
                (h for h in self._assets.values() if h.loaded),
                key=lambda h: h.last_used,
            )
            for handle in handles:
                if freed_mb >= target_mb:
                    break
                handler = handle.unload_callback or self._api_asset_unload
                payload = {
                    "asset_id": handle.asset_id,
                    "metadata": dict(handle.metadata),
                }
                try:
                    if handler:
                        handler(payload)
                except Exception:  # pragma: no cover - defensive
                    LOGGER.warning(
                        "Lazy asset unload failed for %s",
                        handle.asset_id,
                        exc_info=True,
                    )
                handle.loaded = False
                freed_mb += handle.size_mb
                events.append({"asset_id": handle.asset_id, "size_mb": handle.size_mb})
            if freed_mb > 0:
                LOGGER.info(
                    "Evicted %.2fMB worth of assets (%d items)", freed_mb, len(events)
                )
        if events:
            self._emit_budget_event(
                "asset.evicted", {"assets": events, "freed_mb": freed_mb}
            )
        return events

    # ---------------------------------------------------------------- Internal Ops
    def _evaluate_job(
        self, record: JobRecord, metrics: Dict[str, Any]
    ) -> Tuple[str, Optional[str]]:
        if record.status == "running":
            return "running", record.reason

        limits = self._limits
        depth = len(self._queued) + len(self._delayed) + len(self._running)
        if limits.max_queue_depth and depth >= limits.max_queue_depth:
            return "delayed", "queue capacity reached"

        running_count = len(self._running)
        if limits.max_running_jobs and running_count >= limits.max_running_jobs:
            return "delayed", "job cap reached"

        cpu_budget = limits.max_cpu_percent
        mem_budget = limits.max_mem_mb
        vram_budget = limits.max_vram_mb

        cpu_usage = float(metrics.get("cpu") or 0.0)
        mem_used = float(metrics.get("mem_used_mb") or 0.0)
        gpus = metrics.get("gpus") or []
        first_gpu = metrics.get("first_gpu") or (gpus[0] if gpus else None)
        vram_used = float((first_gpu or {}).get("mem_used") or 0.0)

        req = record.requirements
        if cpu_budget and cpu_usage + req.cpu_percent > cpu_budget:
            return "delayed", f"cpu {cpu_usage:.1f}%/{cpu_budget:.1f}%"
        if mem_budget and mem_used + req.ram_mb > mem_budget:
            return "delayed", f"ram {mem_used + req.ram_mb:.0f}MB/{mem_budget}MB"
        if vram_budget and vram_used + req.vram_mb > vram_budget:
            return "delayed", f"vram {vram_used + req.vram_mb:.0f}MB/{vram_budget}MB"

        return "queued", None

    def _maybe_trim_assets(self, metrics: Dict[str, Any]) -> None:
        limits = self._limits
        if not limits.lazy_asset_target_mb:
            return
        mem_budget = limits.max_mem_mb
        vram_budget = limits.max_vram_mb
        mem_used = float(metrics.get("mem_used_mb") or 0.0)
        gpus = metrics.get("gpus") or []
        first_gpu = metrics.get("first_gpu") or (gpus[0] if gpus else None)
        vram_used = float((first_gpu or {}).get("mem_used") or 0.0)

        target = 0.0
        if mem_budget and mem_used > mem_budget:
            target = max(target, mem_used - mem_budget + limits.lazy_asset_target_mb)
        if vram_budget and vram_used > vram_budget:
            target = max(target, vram_used - vram_budget + limits.lazy_asset_target_mb)
        if target > 0.0:
            self.evict_lazy_assets(target_mb=target)

    def _emit_budget_event(self, trigger: str, payload: Dict[str, Any]) -> None:
        if modder_hooks is None:
            return
        try:
            modder_hooks.emit(
                "on_perf_budget_state",
                {
                    "trigger": trigger,
                    "payload": payload,
                    "timestamp": time.time(),
                },
            )
        except Exception:  # pragma: no cover - defensive
            LOGGER.warning(
                "Failed to emit modder hook for trigger %s", trigger, exc_info=True
            )


budget_manager = BudgetManager()

__all__ = [
    "AssetHandle",
    "BudgetLimits",
    "BudgetManager",
    "JobRecord",
    "ResourceRequirements",
    "budget_manager",
]
