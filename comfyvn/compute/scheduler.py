from __future__ import annotations

"""Job scheduler with local/remote queues, cost estimation, and telemetry."""

import heapq
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

from comfyvn.compute.providers import ProviderRegistry, load_seed_from_config

_HISTORY_LIMIT = 200
_DEFAULT_PROVIDER_PATH = Path("config/compute_providers.json")


def _now_ts() -> float:
    return time.time()


def _iso(ts: float | None) -> Optional[str]:
    if ts is None:
        return None
    return (
        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


class JobScheduler:
    """Thread-safe scheduler for local and remote compute queues."""

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        *,
        history_limit: int = _HISTORY_LIMIT,
    ) -> None:
        self.registry = registry
        self.history_limit = max(1, int(history_limit))
        self._lock = threading.RLock()
        self._queues: Dict[str, List[Tuple[int, int, str]]] = {
            "local": [],
            "remote": [],
        }
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._active: set[str] = set()
        self._history: Deque[Dict[str, Any]] = deque(maxlen=self.history_limit)
        self._seq = 0

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------
    def enqueue(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(spec, dict):
            raise TypeError("job spec must be a dictionary")

        job_id = str(spec.get("id") or uuid.uuid4().hex[:12])
        queue = str(spec.get("queue") or spec.get("target") or "local").lower()
        queue = (
            queue
            if queue in self._queues
            else ("remote" if queue == "remote" else "local")
        )
        priority = int(spec.get("priority") or 0)
        sticky = bool(spec.get("sticky_device") or spec.get("sticky"))
        device_hint = spec.get("device_id") or spec.get("sticky_device_id")
        provider_id = spec.get("provider_id")
        payload = spec.get("payload") if isinstance(spec.get("payload"), dict) else {}
        if provider_id is None:
            provider_id = payload.get("provider_id")
        if provider_id is None and queue == "local":
            provider_id = "local"

        submitted = _now_ts()
        job: Dict[str, Any] = {
            "id": job_id,
            "name": spec.get("name") or spec.get("title") or job_id,
            "queue": queue,
            "priority": priority,
            "sticky": sticky,
            "sticky_device_id": device_hint if device_hint else None,
            "device_id": device_hint if device_hint else None,
            "provider_id": provider_id,
            "payload": payload,
            "status": "queued",
            "attempt": 0,
            "runs": [],
            "created_ts": submitted,
            "updated_ts": submitted,
            "created_at": _iso(submitted),
            "updated_at": _iso(submitted),
            "duration_sec": None,
            "bytes_tx": spec.get("bytes_tx"),
            "bytes_rx": spec.get("bytes_rx"),
            "vram_gb": spec.get("vram_gb"),
            "cost_estimate": None,
            "meta": spec.get("meta") if isinstance(spec.get("meta"), dict) else {},
        }

        with self._lock:
            if queue not in self._queues:
                self._queues[queue] = []
            self._jobs[job_id] = job
            self._seq += 1
            entry = (-priority, self._seq, job_id)
            heapq.heappush(self._queues[queue], entry)
        return dict(job)

    def claim(
        self,
        queue: str = "local",
        *,
        worker_id: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        queue = str(queue or "local").lower()
        now = _now_ts()
        with self._lock:
            heap = self._queues.get(queue)
            if not heap:
                return None
            while heap:
                _, _, job_id = heapq.heappop(heap)
                job = self._jobs.get(job_id)
                if not job or job.get("status") != "queued":
                    continue
                job["status"] = "running"
                job["attempt"] = int(job.get("attempt") or 0) + 1
                job["worker_id"] = worker_id
                job["started_ts"] = now
                job["started_at"] = _iso(now)
                job["updated_ts"] = now
                job["updated_at"] = _iso(now)
                if job.get("sticky"):
                    sticky_id = job.get("sticky_device_id")
                    if sticky_id:
                        job["device_id"] = sticky_id
                    elif device_id:
                        job["sticky_device_id"] = device_id
                        job["device_id"] = device_id
                elif device_id:
                    job["device_id"] = device_id

                run_entry = {
                    "attempt": job["attempt"],
                    "device_id": job.get("device_id"),
                    "worker_id": worker_id,
                    "started_at": job.get("started_at"),
                }
                job.setdefault("runs", []).append(run_entry)
                self._active.add(job_id)
                return dict(job)
        return None

    def requeue(self, job_id: str, *, priority: Optional[int] = None) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"job '{job_id}' not found")
            if job.get("status") == "queued":
                return dict(job)
            queue = job.get("queue") or "local"
            priority_value = (
                int(priority) if priority is not None else int(job.get("priority") or 0)
            )
            job["status"] = "queued"
            job["priority"] = priority_value
            job["updated_ts"] = _now_ts()
            job["updated_at"] = _iso(job["updated_ts"])
            job.pop("started_ts", None)
            job.pop("started_at", None)
            self._seq += 1
            entry = (-priority_value, self._seq, job_id)
            if queue not in self._queues:
                self._queues[queue] = []
            heapq.heappush(self._queues[queue], entry)
            self._active.discard(job_id)
            return dict(job)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def complete(
        self,
        job_id: str,
        *,
        status: str = "succeeded",
        bytes_tx: Optional[int] = None,
        bytes_rx: Optional[int] = None,
        vram_gb: Optional[float] = None,
        cost_override: Optional[float] = None,
        duration_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"job '{job_id}' not found")
            now = _now_ts()
            start = job.get("started_ts") or job.get("created_ts") or now
            duration = (
                _safe_float(duration_sec)
                if duration_sec is not None
                else max(0.0, now - _safe_float(start))
            )

            job["status"] = status or "succeeded"
            job["completed_ts"] = now
            job["completed_at"] = _iso(now)
            job["updated_ts"] = now
            job["updated_at"] = _iso(now)
            job["duration_sec"] = round(duration, 3)

            if bytes_tx is not None:
                job["bytes_tx"] = int(bytes_tx)
            elif job.get("bytes_tx") is None:
                job["bytes_tx"] = 0
            if bytes_rx is not None:
                job["bytes_rx"] = int(bytes_rx)
            elif job.get("bytes_rx") is None:
                job["bytes_rx"] = 0
            if vram_gb is not None:
                job["vram_gb"] = _safe_float(vram_gb)

            if cost_override is not None:
                job["cost_estimate"] = round(_safe_float(cost_override), 4)
            else:
                job["cost_estimate"] = self._estimate_cost(job)

            self._active.discard(job_id)
            self._history.appendleft(dict(job))
            return dict(job)

    def fail(self, job_id: str, error: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"job '{job_id}' not found")
            now = _now_ts()
            job["status"] = "failed"
            job["error"] = error
            job["completed_ts"] = now
            job["completed_at"] = _iso(now)
            job["updated_ts"] = now
            job["updated_at"] = _iso(now)
            job["duration_sec"] = job.get("duration_sec") or max(
                0.0, now - _safe_float(job.get("started_ts") or job.get("created_ts"))
            )
            job["cost_estimate"] = job.get("cost_estimate") or self._estimate_cost(job)
            self._active.discard(job_id)
            self._history.appendleft(dict(job))
            return dict(job)

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------
    def state(self) -> Dict[str, Any]:
        with self._lock:
            queues: Dict[str, List[Dict[str, Any]]] = {}
            for name, heap in self._queues.items():
                ordered = sorted(heap)
                items: List[Dict[str, Any]] = []
                for _, _, job_id in ordered:
                    job = self._jobs.get(job_id)
                    if not job:
                        continue
                    items.append(self._public_view(job))
                queues[name] = items

            active = [
                self._public_view(self._jobs[jid])
                for jid in self._active
                if jid in self._jobs
            ]
            completed = [self._public_view(job) for job in list(self._history)]
            return {"queues": queues, "active": active, "completed": completed}

    def board(self, limit: int = 100) -> Dict[str, Any]:
        now = _now_ts()
        with self._lock:
            segments: List[Dict[str, Any]] = []
            for jid in self._active:
                job = self._jobs.get(jid)
                if job:
                    segments.append(self._segment_view(job, default_end=now))
            for job in list(self._history)[:limit]:
                segments.append(self._segment_view(job, default_end=now))
        segments.sort(key=lambda item: (item.get("queue"), item.get("start")))
        return {"jobs": segments, "generated_at": _iso(now)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _public_view(self, job: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": job.get("id"),
            "name": job.get("name"),
            "queue": job.get("queue"),
            "priority": job.get("priority"),
            "status": job.get("status"),
            "sticky": job.get("sticky"),
            "device_id": job.get("device_id"),
            "sticky_device_id": job.get("sticky_device_id"),
            "provider_id": job.get("provider_id"),
            "created_at": job.get("created_at"),
            "started_at": job.get("started_at"),
            "updated_at": job.get("updated_at"),
            "completed_at": job.get("completed_at"),
            "duration_sec": job.get("duration_sec"),
            "bytes_tx": job.get("bytes_tx"),
            "bytes_rx": job.get("bytes_rx"),
            "vram_gb": job.get("vram_gb"),
            "cost_estimate": job.get("cost_estimate"),
            "attempt": job.get("attempt"),
            "runs": list(job.get("runs") or []),
        }

    def _segment_view(
        self, job: Dict[str, Any], *, default_end: float
    ) -> Dict[str, Any]:
        start = _safe_float(
            job.get("started_ts") or job.get("created_ts") or default_end
        )
        end = _safe_float(job.get("completed_ts") or default_end)
        if end < start:
            end = start
        return {
            "id": job.get("id"),
            "name": job.get("name"),
            "queue": job.get("queue"),
            "device": job.get("device_id") or job.get("sticky_device_id"),
            "status": job.get("status"),
            "priority": job.get("priority"),
            "start": start,
            "end": end,
            "duration_sec": job.get("duration_sec") or max(0.0, end - start),
            "cost_estimate": job.get("cost_estimate"),
            "bytes_tx": job.get("bytes_tx"),
            "bytes_rx": job.get("bytes_rx"),
            "vram_gb": job.get("vram_gb"),
            "provider_id": job.get("provider_id"),
        }

    def _estimate_cost(self, job: Dict[str, Any]) -> float:
        provider_meta: Dict[str, Any] = {}
        provider_id = job.get("provider_id")
        if provider_id and self.registry:
            try:
                entry = self.registry.get(provider_id) or {}
                provider_meta = entry.get("meta") or {}
            except Exception:
                provider_meta = {}

        duration = job.get("duration_sec")
        if duration is None:
            start = job.get("started_ts") or job.get("created_ts")
            end = job.get("completed_ts")
            if start and end:
                duration = max(0.0, _safe_float(end) - _safe_float(start))
            else:
                duration = 0.0

        base_rate = _safe_float(
            provider_meta.get(
                "cost_per_minute",
                0.05 if (job.get("queue") == "remote") else 0.0,
            )
        )
        minutes = max(0.0, _safe_float(duration) / 60.0)
        base_cost = minutes * base_rate

        bytes_tx = float(job.get("bytes_tx") or 0)
        bytes_rx = float(job.get("bytes_rx") or 0)
        egress_rate = _safe_float(provider_meta.get("egress_cost_per_gb"), 0.0)
        ingress_rate = _safe_float(
            provider_meta.get("ingress_cost_per_gb"), egress_rate
        )
        gb_tx = bytes_tx / (1024**3)
        gb_rx = bytes_rx / (1024**3)
        transfer_cost = gb_tx * egress_rate + gb_rx * ingress_rate

        vram_cost_rate = _safe_float(provider_meta.get("vram_cost_per_gb_minute"), 0.0)
        vram_gb = _safe_float(
            job.get("vram_gb") or provider_meta.get("default_vram_gb", 0.0)
        )
        vram_cost = minutes * vram_gb * vram_cost_rate

        total = base_cost + transfer_cost + vram_cost
        return round(total, 4)


def _build_registry() -> ProviderRegistry:
    try:
        return ProviderRegistry(
            storage_path=_DEFAULT_PROVIDER_PATH,
            seed=load_seed_from_config(),
        )
    except Exception:
        return ProviderRegistry()


DEFAULT_SCHEDULER = JobScheduler(registry=_build_registry())


def get_scheduler() -> JobScheduler:
    return DEFAULT_SCHEDULER
