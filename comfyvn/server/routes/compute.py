from __future__ import annotations

"""Compute device routes: local GPU snapshot, provider registry, advisor."""

import platform
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Request

from comfyvn.compute.advisor import choose_device
from comfyvn.compute.providers import get_default_registry
from comfyvn.compute.scheduler import get_scheduler
from comfyvn.config import feature_flags
from comfyvn.server.system_metrics import collect_system_metrics

router = APIRouter(prefix="/api", tags=["Compute"])

_REGISTRY = get_default_registry()
_SCHEDULER = get_scheduler()
FEATURE_FLAG = "enable_compute"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "debug"}
    return False


def _feature_context() -> Dict[str, Any]:
    enabled = feature_flags.is_enabled(FEATURE_FLAG, default=False)
    return {"feature": FEATURE_FLAG, "enabled": enabled}


def _cpu_entry(metrics: Dict[str, Any]) -> Dict[str, Any]:
    name = platform.processor() or "CPU"
    return {
        "id": "cpu",
        "type": "cpu",
        "name": name.strip() or "CPU",
        "load": metrics.get("cpu"),
    }


def _gpu_entries(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for gpu in metrics.get("gpus", []) or []:
        mem_total = gpu.get("mem_total")
        mem_used = gpu.get("mem_used")
        entries.append(
            {
                "id": f"gpu:{gpu.get('id')}",
                "type": "gpu",
                "name": gpu.get("name") or "GPU",
                "load": gpu.get("util"),
                "mem_total_mb": mem_total,
                "mem_used_mb": mem_used,
                "temp_c": gpu.get("temp_c"),
            }
        )
    return entries


def _queue_depth(request: Request) -> int:
    manager = getattr(request.app.state, "job_manager", None)
    if manager is None:
        return 0
    if hasattr(manager, "queue_depth") and callable(manager.queue_depth):
        try:
            return int(manager.queue_depth())
        except Exception:  # pragma: no cover - defensive
            return 0
    queue = getattr(manager, "q", None)
    try:
        return len(queue) if queue is not None else 0
    except Exception:  # pragma: no cover - defensive
        return 0


def _local_vram_gb(metrics: Dict[str, Any]) -> float:
    first = (metrics.get("gpus") or [None])[0] or {}
    total_mb = first.get("mem_total")
    if not total_mb:
        return 0.0
    try:
        return round(float(total_mb) / 1024.0, 2)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 0.0


def _remote_available() -> bool:
    if not feature_flags.is_enabled(FEATURE_FLAG, default=False):
        return False
    providers = _REGISTRY.list()
    for entry in providers:
        kind = (entry.get("kind") or "").lower()
        if kind != "local":
            return True
    return False


def _build_cost_spec(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a cost payload into the scheduler preview contract."""

    if not isinstance(payload, dict):
        return {}

    job_section = payload.get("job")
    spec: Dict[str, Any]
    if isinstance(job_section, dict):
        spec = dict(job_section)
    else:
        spec = dict(payload)

    extras = payload.get("payload")
    if isinstance(extras, dict) and "payload" not in spec:
        spec["payload"] = dict(extras)

    for key in (
        "queue",
        "target",
        "provider_id",
        "duration_sec",
        "duration_seconds",
        "duration_min",
        "duration_minutes",
        "expected_duration_sec",
        "expected_duration_min",
        "eta_sec",
        "eta_minutes",
        "bytes_tx",
        "bytes_rx",
        "vram_gb",
    ):
        value = payload.get(key)
        if value is not None and key not in spec:
            spec[key] = value

    for key in (
        "job",
        "debug",
        "verbose",
        "allow_remote",
        "prefer_remote",
        "context",
    ):
        spec.pop(key, None)
    return spec


@router.get("/gpu/list")
async def gpu_list(request: Request) -> Dict[str, Any]:
    metrics = collect_system_metrics() or {}
    devices = [_cpu_entry(metrics)]
    devices.extend(_gpu_entries(metrics))
    response: Dict[str, Any] = {"devices": devices, "feature": _feature_context()}
    if _truthy(request.query_params.get("debug")):
        response["metrics"] = metrics
    return response


@router.get("/providers")
async def providers_list(request: Request) -> Dict[str, Any]:
    debug = _truthy(request.query_params.get("debug"))
    result: Dict[str, Any] = {
        "providers": _REGISTRY.list(),
        "feature": _feature_context(),
    }
    if debug:
        result["stats"] = _REGISTRY.stats()
    return result


@router.post("/providers")
async def providers_add(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    debug = _truthy(payload.get("debug"))
    provider_id = payload.get("id")
    if not provider_id:
        raise HTTPException(status_code=400, detail="missing provider id")
    try:
        record = _REGISTRY.add(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TypeError as exc:
        raise HTTPException(status_code=400, detail="invalid provider fields") from exc
    data = asdict(record)
    response: Dict[str, Any] = {
        "ok": True,
        "provider": data,
        "feature": _feature_context(),
    }
    if debug:
        response["stats"] = _REGISTRY.stats()
    return response


@router.delete("/providers/{provider_id}")
async def providers_remove(provider_id: str, request: Request) -> Dict[str, Any]:
    removed = _REGISTRY.remove(provider_id)
    if not removed:
        raise HTTPException(status_code=404, detail="provider not found")
    debug = _truthy(request.query_params.get("debug"))
    response: Dict[str, Any] = {"ok": True, "feature": _feature_context()}
    if debug:
        response["stats"] = _REGISTRY.stats()
    return response


@router.post("/compute/advise")
async def compute_advise(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    feature = _feature_context()
    debug = _truthy(payload.get("debug") or payload.get("verbose"))

    job_payload = payload.get("job")
    if isinstance(job_payload, dict):
        job = dict(job_payload)
    else:
        job = dict(payload)
    job.pop("debug", None)
    job.pop("verbose", None)
    job_context_override = job.pop("context", None)
    job.pop("job", None)
    job.pop("allow_remote", None)
    job.pop("prefer_remote", None)

    allow_remote = bool(payload.get("allow_remote") or payload.get("prefer_remote"))
    if not feature["enabled"]:
        allow_remote = False

    metrics = collect_system_metrics() or {}
    try:
        scheduler_state = _SCHEDULER.state()
    except Exception:  # pragma: no cover - defensive
        scheduler_state = {}

    remote_queue_depth = len((scheduler_state.get("queues") or {}).get("remote") or [])

    context = {
        "has_gpu": bool((metrics.get("gpus") or [])),
        "local_queue_depth": _queue_depth(request),
        "local_vram_gb": _local_vram_gb(metrics),
        "remote_available": _remote_available(),
        "remote_queue_depth": remote_queue_depth,
        "feature_enabled": feature["enabled"],
    }

    if not feature["enabled"]:
        context["remote_available"] = False

    override_ctx = payload.get("context") or job_context_override
    if isinstance(override_ctx, dict):
        context.update(override_ctx)

    if debug:
        decision, reason, details = choose_device(job, context, return_details=True)
    else:
        decision, reason = choose_device(job, context)
        details = None

    if decision == "remote":
        remote_ok = allow_remote and context.get("remote_available")
        if not remote_ok:
            fallback = "gpu" if context.get("has_gpu") else "cpu"
            if not feature["enabled"]:
                blocker = "compute feature disabled"
            elif not allow_remote:
                blocker = "remote offload disabled"
            else:
                blocker = "no remote providers configured"
            reason = f"{reason}; {blocker}"
            decision = fallback

    context_summary = {
        "has_gpu": context.get("has_gpu"),
        "local_queue_depth": context.get("local_queue_depth"),
        "remote_available": context.get("remote_available"),
        "remote_queue_depth": context.get("remote_queue_depth"),
        "local_vram_gb": context.get("local_vram_gb"),
    }

    response: Dict[str, Any] = {
        "decision": decision,
        "reason": reason,
        "feature": feature,
        "context": context_summary,
        "remote_allowed": bool(allow_remote and context.get("remote_available")),
    }

    if details is not None:
        details["context"] = context
        scheduler_summary = {
            "queues": {
                name: len(items)
                for name, items in (scheduler_state.get("queues") or {}).items()
            },
            "active": len(scheduler_state.get("active") or []),
            "completed": len(scheduler_state.get("completed") or []),
        }
        response["debug"] = {
            "advisor": details,
            "metrics": metrics,
            "registry": _REGISTRY.stats(),
            "scheduler": scheduler_summary,
            "allow_remote": allow_remote,
        }

    return response


@router.post("/compute/costs")
async def compute_costs(
    payload: Optional[Dict[str, Any]] = Body(default_factory=dict),
) -> Dict[str, Any]:
    data = payload or {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    debug = _truthy(data.get("debug") or data.get("verbose"))
    feature = _feature_context()

    cost_spec = _build_cost_spec(data)
    if not cost_spec:
        raise HTTPException(status_code=400, detail="missing job payload")

    try:
        preview = _SCHEDULER.preview_cost(cost_spec)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail="unable to compute cost preview"
        ) from exc

    if not isinstance(preview.get("notes"), list):
        preview["notes"] = []
    if not feature["enabled"] and preview["inputs"].get("queue") == "remote":
        preview["notes"].append(
            "Remote execution disabled by feature flag; treat estimate as informational."
        )

    response: Dict[str, Any] = {
        "feature": feature,
        "estimate": preview,
    }
    if debug:
        response["debug"] = {
            "registry": _REGISTRY.stats(),
            "providers": _REGISTRY.list(),
        }
    return response
