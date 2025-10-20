"""Heuristics for recommending compute providers for importer workloads."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional

from comfyvn.core.gpu_manager import GPUManager

LOGGER = logging.getLogger(__name__)


SERVICE_HINTS: Dict[str, Dict[str, Any]] = {
    "runpod": {"min_vram": 12, "cost_hint": "$0.46/hr", "notes": "Serverless pods with hourly billing."},
    "vast.ai": {"min_vram": 16, "cost_hint": "market", "notes": "Marketplace — consider queue delay."},
    "lambda": {"min_vram": 24, "cost_hint": "$1.10/hr", "notes": "Good for long-running CG batches."},
    "aws": {"min_vram": 16, "cost_hint": "$0.80+/hr", "notes": "EC2 g- instances; mind egress fees."},
    "azure": {"min_vram": 16, "cost_hint": "$1.00+/hr", "notes": "NV-series VMs; requires quota."},
    "paperspace": {"min_vram": 24, "cost_hint": "$0.78/hr", "notes": "Persistent volumes available."},
    "lan": {"min_vram": 8, "cost_hint": "N/A", "notes": "On-prem node (unRAID/SSH)."},
}


def _device_meets(device: Dict[str, Any], min_vram: Optional[float]) -> bool:
    if min_vram is None:
        return True
    mem_total = device.get("memory_total")
    if mem_total is None:
        return False
    mem_value = float(mem_total)
    mem_gb = mem_value / 1024 if mem_value > 256 else mem_value
    return mem_gb >= float(min_vram)


def _simplify_device(device: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": device.get("id"),
        "name": device.get("name"),
        "kind": device.get("kind"),
        "memory_total": device.get("memory_total"),
        "source": device.get("source"),
    }


def advise(
    gpu_manager: GPUManager,
    *,
    workload: Optional[Dict[str, Any]] = None,
    prefer_remote: bool = False,
    hardware_override: bool = False,
) -> Dict[str, Any]:
    """Return a recommendation for where a job should run."""

    workload = workload or {}
    requirements = workload.get("requirements") or {}
    min_vram = requirements.get("min_vram_gb") or requirements.get("min_vram")
    workload_type = requirements.get("type") or workload.get("type")

    devices = gpu_manager.list_all(refresh=True)
    local_candidates = [d for d in devices if d.get("kind") in {"gpu", "cpu"}]
    remote_candidates = [d for d in devices if d.get("kind") == "remote"]

    best_local = None
    for device in local_candidates:
        if device.get("kind") == "cpu":
            continue
        if _device_meets(device, min_vram):
            if best_local is None or (device.get("memory_total") or 0) > (best_local.get("memory_total") or 0):
                best_local = device

    # Determine remote suggestion
    provider_registry = gpu_manager.registry
    remote_providers = provider_registry.list() if provider_registry else []
    recommended_remote = None
    for entry in remote_providers:
        if not entry.get("active", True):
            continue
        hint = SERVICE_HINTS.get(entry.get("service"))
        if min_vram and hint and hint.get("min_vram") and hint["min_vram"] < min_vram:
            # provider advertises lower VRAM than needed
            continue
        recommended_remote = {
            "id": entry.get("id"),
            "name": entry.get("name"),
            "service": entry.get("service"),
            "base_url": entry.get("base_url"),
            "cost_hint": (hint or {}).get("cost_hint"),
            "notes": (hint or {}).get("notes"),
        }
        break

    recommendation = {
        "workload": workload,
        "local_candidate": _simplify_device(best_local) if best_local else None,
        "remote_candidate": recommended_remote,
    }

    rationale: List[str] = []
    if min_vram:
        rationale.append(f"Minimum VRAM requested: {min_vram} GB")
    if best_local:
        rationale.append(
            f"Local device {best_local.get('name')} ({best_local.get('memory_total')} MiB) meets requirements"
        )
    elif not prefer_remote:
        rationale.append("No local GPU satisfied VRAM requirement; considering remote providers")

    if recommended_remote:
        rationale.append(
            f"Suggested remote provider: {recommended_remote['name']} ({recommended_remote.get('service')})"
        )
    elif prefer_remote:
        rationale.append("Remote processing requested but no active providers registered")

    recommendation["reason"] = "; ".join(rationale) if rationale else "No specific requirements provided"

    if hardware_override:
        recommendation["choice"] = "cpu"
        recommendation["override"] = "cpu"
        recommendation["fallback"] = recommended_remote
        recommendation["reason"] += "; user override requested CPU fallback"
    elif prefer_remote and recommended_remote:
        recommendation["choice"] = "remote"
    elif best_local and not prefer_remote:
        recommendation["choice"] = "local"
    elif recommended_remote:
        recommendation["choice"] = "remote"
    else:
        recommendation["choice"] = "cpu"

    LOGGER.debug("Compute advisor recommendation: %s", recommendation)
    return recommendation


__all__ = ["advise"]
