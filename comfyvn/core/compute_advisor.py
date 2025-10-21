"""Heuristics for recommending compute providers for importer workloads."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from comfyvn.core.gpu_manager import GPUManager

LOGGER = logging.getLogger(__name__)


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


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _asset_size_mb(asset: Dict[str, Any]) -> float:
    if not isinstance(asset, dict):
        return 0.0
    if "size_mb" in asset:
        return _coerce_float(asset.get("size_mb")) or 0.0
    if "size_bytes" in asset:
        size_bytes = _coerce_float(asset.get("size_bytes"))
        if size_bytes is not None:
            return size_bytes / (1024 * 1024)
    if "size_kb" in asset:
        size_kb = _coerce_float(asset.get("size_kb"))
        if size_kb is not None:
            return size_kb / 1024
    return 0.0


def _collect_assets(workload: Dict[str, Any]) -> List[Dict[str, Any]]:
    assets: List[Dict[str, Any]] = []
    raw_assets = workload.get("assets")
    if isinstance(raw_assets, list):
        assets.extend([asset for asset in raw_assets if isinstance(asset, dict)])
    asset_summary = workload.get("asset_summary")
    if isinstance(asset_summary, dict):
        items = asset_summary.get("items") or asset_summary.get("assets")
        if isinstance(items, list):
            assets.extend([asset for asset in items if isinstance(asset, dict)])
    return assets


def _collect_workflows(workload: Dict[str, Any]) -> List[Dict[str, Any]]:
    workflows: List[Dict[str, Any]] = []
    raw = workload.get("workflows")
    if isinstance(raw, list):
        workflows.extend([wf for wf in raw if isinstance(wf, dict)])
    comfy = workload.get("comfyui") or {}
    comfy_list = comfy.get("workflows") or comfy.get("cached_workflows")
    if isinstance(comfy_list, list):
        workflows.extend([wf for wf in comfy_list if isinstance(wf, dict)])
    return workflows


def _analyze_workload(workload: Dict[str, Any]) -> Dict[str, Any]:
    requirements = workload.get("requirements") or {}
    workload_type_raw = requirements.get("type") or workload.get("type")
    workload_type = (workload_type_raw or "").lower() or None

    assets = _collect_assets(workload)
    asset_sizes = [_asset_size_mb(asset) for asset in assets]
    total_asset_mb = sum(asset_sizes)
    largest_asset_mb = max(asset_sizes) if asset_sizes else 0.0

    workflows = _collect_workflows(workload)
    cached = sum(
        1 for wf in workflows if wf.get("cached") or wf.get("status") == "cached"
    )
    uncached = sum(
        1 for wf in workflows if not (wf.get("cached") or wf.get("status") == "cached")
    )
    requires_persistent_storage = any(
        wf.get("persist_outputs") or wf.get("requires_persistent_storage")
        for wf in workflows
    )
    if total_asset_mb > 2048:
        requires_persistent_storage = True

    expected_runtime_minutes = (
        _coerce_float(requirements.get("estimated_minutes"))
        or _coerce_float(workload.get("estimated_minutes"))
        or _coerce_float((workload.get("estimate") or {}).get("duration_minutes"))
        or 30.0
    )
    batch_hours = expected_runtime_minutes / 60.0
    burst_mode = expected_runtime_minutes <= 20.0

    min_vram_req = _coerce_float(
        requirements.get("min_vram_gb") or requirements.get("min_vram")
    )
    inferred_min_vram = None
    if workload_type in {"cg_batch", "cg", "render", "animation"}:
        inferred_min_vram = 24 if largest_asset_mb > 1024 else 16
    elif workload_type in {"voice_synthesis", "tts"}:
        inferred_min_vram = 12
    elif workload_type in {"translation"}:
        inferred_min_vram = 8 if largest_asset_mb <= 512 else 12

    if inferred_min_vram is None:
        if largest_asset_mb > 2048:
            inferred_min_vram = 24
        elif largest_asset_mb > 1024:
            inferred_min_vram = 16
        elif largest_asset_mb > 512:
            inferred_min_vram = 12
        elif largest_asset_mb > 256:
            inferred_min_vram = 8

    min_vram_gb = min_vram_req or inferred_min_vram

    pipeline = workload.get("pipeline") or {}
    translation = pipeline.get("translation") or workload.get("translation") or {}
    translation_gpu = bool(translation.get("requires_gpu"))
    if translation_gpu and (not min_vram_gb or min_vram_gb < 12):
        min_vram_gb = 12

    requires_gpu = bool(workload.get("requires_gpu"))
    if min_vram_gb and min_vram_gb >= 8:
        requires_gpu = True
    if translation_gpu:
        requires_gpu = True

    budget = workload.get("budget") or {}
    limit_usd = _coerce_float(budget.get("limit_usd"))
    budget_mode = (budget.get("mode") or "").lower()
    if budget_mode in {"frugal", "cost_saver"} or (
        limit_usd is not None and limit_usd <= 5
    ):
        cost_sensitivity = "high"
    elif budget_mode in {"premium", "speed"}:
        cost_sensitivity = "low"
    else:
        cost_sensitivity = "medium"

    if workload.get("cache", {}).get("requires_persistent"):
        requires_persistent_storage = True

    return {
        "workload_type": workload_type,
        "assets": assets,
        "total_asset_mb": total_asset_mb,
        "largest_asset_mb": largest_asset_mb,
        "requires_gpu": requires_gpu,
        "requires_persistent_storage": requires_persistent_storage,
        "expected_runtime_minutes": expected_runtime_minutes,
        "burst_mode": burst_mode,
        "batch_hours": batch_hours,
        "min_vram_gb": min_vram_gb,
        "inferred_min_vram_gb": inferred_min_vram,
        "cached_workflows": cached,
        "uncached_workflows": uncached,
        "has_cached_workflows": cached > 0,
        "pipeline_translation_gpu": translation_gpu,
        "cost_sensitivity": cost_sensitivity,
        "budget_limit_usd": limit_usd,
    }


def _score_remote_provider(
    entry: Dict[str, Any],
    *,
    min_vram: Optional[float],
    analysis: Dict[str, Any],
) -> tuple[float, Optional[str]]:
    meta = entry.get("meta") or {}
    provider_min_vram = _coerce_float(meta.get("min_vram_gb"))
    if min_vram and provider_min_vram and provider_min_vram < min_vram:
        return float("-inf"), None

    hints = meta.get("policy_hints") or {}
    workload_type = analysis.get("workload_type")
    hint_for_workload = (
        hints.get(workload_type) if isinstance(hints, dict) and workload_type else None
    )

    cost_info = meta.get("cost") or {}
    hourly_cost = _coerce_float(cost_info.get("hourly_usd"))
    cost_tier = _coerce_float(meta.get("cost_tier"))

    score = 0.0

    if hourly_cost is not None:
        score += max(0.0, 10.0 - hourly_cost * 5.0)
    if cost_tier is not None:
        score += max(0.0, 6.0 - cost_tier * 2.0)

    if provider_min_vram is not None:
        if min_vram:
            score += max(provider_min_vram - min_vram, 0.0) * 0.5
        else:
            score += provider_min_vram * 0.1

    if analysis.get("burst_mode"):
        if meta.get("supports_short_burst"):
            score += 2.0
        else:
            score -= 1.0

    if analysis.get("batch_hours", 0.0) >= 4.0:
        if meta.get("supports_long_running"):
            score += 2.5
        else:
            score -= 2.0

    if analysis.get("requires_persistent_storage"):
        if meta.get("supports_persistent_storage"):
            score += 2.0
        else:
            score -= 3.0

    if analysis.get("total_asset_mb", 0.0) > 2048.0:
        if meta.get("supports_large_assets"):
            score += 2.0
        else:
            score -= 2.5

    preferred = set(meta.get("preferred_workloads") or [])
    if workload_type and workload_type in preferred:
        score += 3.5

    if hint_for_workload:
        score += 1.0

    cost_sensitivity = analysis.get("cost_sensitivity")
    if cost_sensitivity == "high":
        if hourly_cost is not None:
            score -= hourly_cost
        if cost_tier is not None:
            score -= cost_tier * 0.5
    elif cost_sensitivity == "low":
        if provider_min_vram is not None:
            score += provider_min_vram * 0.1

    budget_limit = analysis.get("budget_limit_usd")
    if budget_limit and hourly_cost is not None:
        expected_runtime_minutes = analysis.get("expected_runtime_minutes", 30.0)
        estimate = hourly_cost * (expected_runtime_minutes / 60.0)
        if estimate > budget_limit:
            score -= (estimate - budget_limit) * 2.0

    availability = entry.get("last_health") or {}
    if availability and availability.get("ok") is False:
        score -= 5.0

    return score, hint_for_workload


def _select_remote_provider(
    remote_providers: Iterable[Dict[str, Any]],
    *,
    min_vram: Optional[float],
    analysis: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], Optional[str], Optional[float]]:
    best_entry: Optional[Dict[str, Any]] = None
    best_hint: Optional[str] = None
    best_score = float("-inf")
    for entry in remote_providers:
        if entry.get("id") == "local" or entry.get("kind") != "remote":
            continue
        if not entry.get("active", True):
            continue
        score, hint = _score_remote_provider(
            entry, min_vram=min_vram, analysis=analysis
        )
        if score > best_score:
            best_score = score
            best_entry = entry
            best_hint = hint
    return best_entry, best_hint, (best_score if best_entry else None)


def _estimate_cost(meta: Dict[str, Any], minutes: float) -> Optional[float]:
    cost_info = meta.get("cost") or {}
    hourly_cost = _coerce_float(cost_info.get("hourly_usd"))
    if hourly_cost is None:
        return None
    return round(hourly_cost * (minutes / 60.0), 2)


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
    min_vram = _coerce_float(
        requirements.get("min_vram_gb") or requirements.get("min_vram")
    )

    analysis = _analyze_workload(workload)
    if min_vram is None:
        min_vram = analysis.get("min_vram_gb")
    else:
        analysis["min_vram_gb"] = min_vram

    devices = gpu_manager.list_all(refresh=True)
    local_candidates = [d for d in devices if d.get("kind") in {"gpu", "cpu"}]
    remote_candidates = [d for d in devices if d.get("kind") == "remote"]

    best_local = None
    for device in local_candidates:
        if device.get("kind") == "cpu":
            continue
        if _device_meets(device, min_vram):
            if best_local is None or (device.get("memory_total") or 0) > (
                best_local.get("memory_total") or 0
            ):
                best_local = device

    # Determine remote suggestion
    provider_registry = gpu_manager.registry
    remote_providers = provider_registry.list() if provider_registry else []
    recommended_entry, policy_hint, score = _select_remote_provider(
        remote_providers,
        min_vram=min_vram,
        analysis=analysis,
    )

    recommended_remote = None
    estimated_cost = None
    if recommended_entry:
        meta = recommended_entry.get("meta") or {}
        estimated_cost = _estimate_cost(
            meta, analysis.get("expected_runtime_minutes", 30.0)
        )
        cost_info = meta.get("cost") or {}
        recommended_remote = {
            "id": recommended_entry.get("id"),
            "name": recommended_entry.get("name"),
            "service": recommended_entry.get("service"),
            "base_url": recommended_entry.get("base_url"),
            "meta": meta,
            "cost": cost_info,
            "cost_estimate": estimated_cost,
            "cost_estimate_str": (
                f"${estimated_cost:.2f}" if estimated_cost is not None else None
            ),
            "policy_hint": policy_hint,
            "score": score,
        }
        analysis["recommended_remote_id"] = recommended_entry.get("id")
        if score is not None:
            analysis["recommended_remote_score"] = score

    recommendation = {
        "workload": workload,
        "local_candidate": _simplify_device(best_local) if best_local else None,
        "remote_candidate": recommended_remote,
        "analysis": analysis,
    }

    rationale: List[str] = []
    workload_type = analysis.get("workload_type")
    if workload_type:
        rationale.append(f"Workload classified as '{workload_type}'")
    if min_vram:
        rationale.append(f"Minimum VRAM requested: {min_vram} GB")
    if analysis.get("total_asset_mb"):
        total_mb = analysis["total_asset_mb"]
        largest_mb = analysis.get("largest_asset_mb") or 0.0
        rationale.append(
            f"Importer assets ~{total_mb:.0f} MB total (largest {largest_mb:.0f} MB)"
        )
    if analysis.get("expected_runtime_minutes"):
        rationale.append(
            f"Estimated runtime {analysis['expected_runtime_minutes']:.0f} minutes"
        )
    if best_local:
        rationale.append(
            f"Local device {best_local.get('name')} ({best_local.get('memory_total')} MiB) meets requirements"
        )
    elif not prefer_remote:
        rationale.append(
            "No local GPU satisfied VRAM requirement; considering remote providers"
        )

    if recommended_remote:
        provider_line = f"Suggested remote provider: {recommended_remote['name']} ({recommended_remote.get('service')})"
        if recommended_remote.get("cost_estimate_str"):
            provider_line += f" ~{recommended_remote['cost_estimate_str']} per job"
        rationale.append(provider_line)
        if recommended_remote.get("policy_hint"):
            rationale.append(recommended_remote["policy_hint"])
    elif prefer_remote:
        rationale.append(
            "Remote processing requested but no active providers registered"
        )

    recommendation["reason"] = (
        "; ".join(rationale) if rationale else "No specific requirements provided"
    )

    if hardware_override:
        recommendation["choice"] = "cpu"
        recommendation["override"] = "cpu"
        recommendation["fallback"] = recommended_remote
        recommendation["reason"] += "; user override requested CPU fallback"
    elif prefer_remote and recommended_remote:
        recommendation["choice"] = "remote"
    elif best_local:
        recommendation["choice"] = "local"
    elif recommended_remote:
        recommendation["choice"] = "remote"
    else:
        recommendation["choice"] = "cpu"

    if estimated_cost is not None:
        recommendation["estimated_cost"] = f"${estimated_cost:.2f}"
    else:
        recommendation["estimated_cost"] = None

    recommendation["job_summary"] = {
        "recommended_provider": (
            recommended_remote.get("id") if recommended_remote else None
        ),
        "choice": recommendation["choice"],
        "estimated_cost": recommendation.get("estimated_cost"),
        "policy_hint": (
            recommended_remote.get("policy_hint") if recommended_remote else None
        ),
        "min_vram_gb": analysis.get("min_vram_gb"),
        "asset_total_mb": analysis.get("total_asset_mb"),
    }

    LOGGER.debug("Compute advisor recommendation: %s", recommendation)
    return recommendation


__all__ = ["advise"]
