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

    def preview_cost(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return an advisory cost breakdown for the provided job specification.

        The response includes numeric components and human-readable hints so
        contributors can understand how totals were derived. Estimates are
        non-binding and rely on provider metadata when available.
        """

        if not isinstance(spec, dict):
            raise TypeError("job spec must be a dictionary")

        payload = spec.get("payload") if isinstance(spec.get("payload"), dict) else {}

        def _find(*names: str) -> Any:
            for name in names:
                if name in spec and spec[name] is not None:
                    return spec[name]
                if payload and name in payload and payload[name] is not None:
                    return payload[name]
            return None

        queue = str(_find("queue", "target") or "local").lower()
        provider_id = _find("provider_id")
        if provider_id is None and queue == "local":
            provider_id = "local"

        duration_raw = _find(
            "duration_sec",
            "duration_seconds",
            "eta_sec",
            "expected_duration_sec",
        )
        if duration_raw is None:
            minutes_raw = _find(
                "duration_min",
                "duration_minutes",
                "eta_minutes",
                "expected_duration_min",
            )
            if minutes_raw is not None:
                try:
                    duration_raw = float(minutes_raw) * 60.0
                except (TypeError, ValueError):
                    duration_raw = None

        duration_sec = max(0.0, _safe_float(duration_raw, 0.0))
        bytes_tx = max(
            0.0, _safe_float(_find("bytes_tx", "upload_bytes", "input_bytes"), 0.0)
        )
        bytes_rx = max(
            0.0, _safe_float(_find("bytes_rx", "download_bytes", "output_bytes"), 0.0)
        )
        vram_gb = max(
            0.0,
            _safe_float(_find("vram_gb", "required_vram_gb", "min_vram_gb"), 0.0),
        )

        job_view = {
            "queue": queue,
            "provider_id": provider_id,
            "duration_sec": duration_sec,
            "bytes_tx": int(bytes_tx),
            "bytes_rx": int(bytes_rx),
            "vram_gb": vram_gb,
        }

        provider_entry = self._resolve_provider(provider_id)
        provider_meta = (provider_entry.get("meta") or {}) if provider_entry else {}
        components = self._cost_components(job_view, provider_meta)
        hints = self._cost_hint_strings(job_view, components, provider_entry)

        breakdown = {
            "duration_minutes": round(float(components["minutes"]), 3),
            "base_rate_per_minute": round(float(components["base_rate_per_minute"]), 4),
            "base_cost": round(float(components["base_cost"]), 4),
            "gb_tx": round(float(components["gb_tx"]), 6),
            "gb_rx": round(float(components["gb_rx"]), 6),
            "egress_rate_per_gb": round(float(components["egress_rate_per_gb"]), 4),
            "ingress_rate_per_gb": round(float(components["ingress_rate_per_gb"]), 4),
            "transfer_cost": round(float(components["transfer_cost"]), 4),
            "vram_gb": round(float(components["vram_gb"]), 3),
            "vram_rate_per_gb_minute": round(
                float(components["vram_rate_per_gb_minute"]), 4
            ),
            "vram_cost": round(float(components["vram_cost"]), 4),
        }

        notes = ["Advisory estimate only; no billing occurs through ComfyVN."]
        if provider_entry is None and provider_id:
            notes.append(
                f"Provider '{provider_id}' not found in registry; using defaults."
            )
        elif provider_entry and not (provider_entry.get("meta") or {}):
            notes.append("Provider metadata missing; using neutral defaults.")

        return {
            "provider": self._public_provider_info(provider_entry, provider_id, queue),
            "estimate": round(float(components["total"]), 4),
            "currency": components["currency"],
            "breakdown": breakdown,
            "hints": hints,
            "notes": notes,
            "inputs": job_view,
        }

    # ------------------------------------------------------------------
    # Cost helpers
    # ------------------------------------------------------------------
    def _resolve_provider(self, provider_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not provider_id or self.registry is None:
            return None
        try:
            entry = self.registry.get(provider_id)
        except Exception:
            return None
        return entry or None

    @staticmethod
    def _cost_components(
        job: Dict[str, Any],
        provider_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        queue = str(job.get("queue") or "local").lower()
        duration_sec = max(0.0, _safe_float(job.get("duration_sec"), 0.0))
        minutes = max(0.0, duration_sec / 60.0)

        default_rate = 0.05 if queue == "remote" else 0.0
        base_rate = _safe_float(provider_meta.get("cost_per_minute"), default_rate)
        base_cost = max(0.0, minutes * base_rate)

        bytes_tx = max(0.0, _safe_float(job.get("bytes_tx"), 0.0))
        bytes_rx = max(0.0, _safe_float(job.get("bytes_rx"), 0.0))
        gb_tx = bytes_tx / float(1024**3)
        gb_rx = bytes_rx / float(1024**3)

        egress_rate = _safe_float(provider_meta.get("egress_cost_per_gb"), 0.0)
        ingress_rate = _safe_float(
            provider_meta.get("ingress_cost_per_gb"), egress_rate
        )
        transfer_cost = max(0.0, gb_tx * egress_rate + gb_rx * ingress_rate)

        vram_rate = _safe_float(provider_meta.get("vram_cost_per_gb_minute"), 0.0)
        default_vram = _safe_float(provider_meta.get("default_vram_gb"), 0.0)
        vram_gb = max(
            0.0,
            _safe_float(job.get("vram_gb"), default_vram),
        )
        vram_cost = max(0.0, minutes * vram_gb * vram_rate)

        total = base_cost + transfer_cost + vram_cost
        currency = str(provider_meta.get("currency") or "USD").upper()

        return {
            "queue": queue,
            "minutes": minutes,
            "base_rate_per_minute": base_rate,
            "base_cost": base_cost,
            "bytes_tx": bytes_tx,
            "bytes_rx": bytes_rx,
            "gb_tx": gb_tx,
            "gb_rx": gb_rx,
            "egress_rate_per_gb": egress_rate,
            "ingress_rate_per_gb": ingress_rate,
            "transfer_cost": transfer_cost,
            "vram_gb": vram_gb,
            "vram_rate_per_gb_minute": vram_rate,
            "vram_cost": vram_cost,
            "total": total,
            "currency": currency,
        }

    def _cost_hint_strings(
        self,
        job: Dict[str, Any],
        components: Dict[str, Any],
        provider_entry: Optional[Dict[str, Any]],
    ) -> List[str]:
        hints: List[str] = []

        provider_meta = provider_entry.get("meta") if provider_entry else {}
        provider_id = job.get("provider_id")
        provider_kind = provider_entry.get("kind") if provider_entry else None
        provider_label = None

        if isinstance(provider_meta, dict):
            provider_label = (
                provider_meta.get("label")
                or provider_meta.get("name")
                or provider_meta.get("title")
            )

        if provider_label is None and provider_entry:
            provider_label = provider_entry.get("id")
        if provider_label is None and provider_id:
            provider_label = provider_id
        if provider_label is None:
            provider_label = "unspecified"

        queue = components.get("queue")
        hints.append(
            f"Provider {provider_label} ({provider_kind or queue}) - estimates in {components['currency']}."
        )

        minutes = float(components["minutes"])
        base_rate = float(components["base_rate_per_minute"])
        base_cost = float(components["base_cost"])

        if minutes > 0 and base_rate > 0:
            hints.append(
                f"Base: {minutes:.2f} min @ {base_rate:.3f} {components['currency']}/min ~= {base_cost:.2f} {components['currency']}"
            )
        elif minutes <= 0:
            hints.append(
                "Base: duration not supplied; treating as zero-minute workload."
            )
        else:
            hints.append(
                "Base: provider metadata missing rate; defaulted to zero cost."
            )

        transfer_cost = float(components["transfer_cost"])
        gb_tx = float(components["gb_tx"])
        gb_rx = float(components["gb_rx"])
        if transfer_cost > 0 or gb_tx > 0 or gb_rx > 0:
            hints.append(
                f"Transfer: {gb_tx:.3f} GB out / {gb_rx:.3f} GB in ~= {transfer_cost:.2f} {components['currency']} (egress {float(components['egress_rate_per_gb']):.3f})."
            )

        vram_cost = float(components["vram_cost"])
        vram_gb = float(components["vram_gb"])
        vram_rate = float(components["vram_rate_per_gb_minute"])
        if vram_cost > 0:
            hints.append(
                f"VRAM surcharge: {vram_gb:.2f} GB @ {vram_rate:.3f} per GB-min ~= {vram_cost:.2f} {components['currency']}."
            )
        elif vram_gb > 0 and vram_rate == 0:
            hints.append("VRAM surcharge: provider does not bill for VRAM usage.")

        if float(components["total"]) == 0:
            hints.append(
                "Total cost rounded to 0; ensure provider metadata is populated for accurate previews."
            )

        return hints

    @staticmethod
    def _public_provider_info(
        provider_entry: Optional[Dict[str, Any]],
        provider_id: Optional[str],
        queue: str,
    ) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "id": provider_id or ("local" if queue == "local" else None),
            "kind": None,
            "base": None,
            "label": None,
        }
        if provider_entry:
            info["id"] = provider_entry.get("id") or info["id"]
            info["kind"] = provider_entry.get("kind")
            info["base"] = provider_entry.get("base")
            meta = provider_entry.get("meta") or {}
            if isinstance(meta, dict):
                info["label"] = (
                    meta.get("label")
                    or meta.get("name")
                    or meta.get("title")
                    or info["id"]
                )
                info["pricing_url"] = meta.get("pricing_url")
                info["notes"] = meta.get("notes")
        if info.get("label") is None and info.get("id"):
            info["label"] = info["id"]
        info["queue"] = queue
        return info

    def _estimate_cost(self, job: Dict[str, Any]) -> float:
        provider_entry = self._resolve_provider(job.get("provider_id"))
        provider_meta = (provider_entry.get("meta") or {}) if provider_entry else {}

        duration = job.get("duration_sec")
        if duration is None:
            start = job.get("started_ts") or job.get("created_ts")
            end = job.get("completed_ts")
            if start and end:
                duration = max(0.0, _safe_float(end) - _safe_float(start))
            else:
                duration = 0.0

        job_view = dict(job)
        job_view["duration_sec"] = duration

        components = self._cost_components(job_view, provider_meta)
        return round(float(components["total"]), 4)


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
