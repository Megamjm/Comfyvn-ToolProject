from __future__ import annotations

"""Tiny compute advisor heuristics for routing jobs."""

from typing import Any, Dict, Tuple


def _infer_pixels(job: Dict[str, Any]) -> int:
    if not isinstance(job, dict):
        return 512 * 512
    if "pixels" in job:
        try:
            return max(1, int(job["pixels"]))
        except (TypeError, ValueError):
            pass
    width = job.get("width")
    height = job.get("height")
    try:
        if width and height:
            return max(1, int(width) * int(height))
    except (TypeError, ValueError):
        return 512 * 512
    return 512 * 512


def _infer_vram(job: Dict[str, Any]) -> float:
    for key in ("vram_gb", "min_vram_gb", "required_vram_gb"):
        value = job.get(key)
        try:
            if value is not None:
                return max(0.0, float(value))
        except (TypeError, ValueError):
            continue
    return 0.0


def _collect_details(
    job: Dict[str, Any],
    ctx: Dict[str, Any],
    *,
    decision: str,
    reason: str,
    pixels: int,
    vram_required: float,
) -> Dict[str, Any]:
    """Assemble a debug payload describing the advisor inputs and thresholds."""

    thresholds = {
        "tiny_pixels": 512 * 512,
        "large_pixels": 4096 * 4096,
        "queue_remote_soft": 3,
        "queue_cpu_saturation": 5,
        "vram_slack_gb": 0.5,
    }
    hints: Dict[str, Any] = {
        "job": {
            "priority": job.get("priority"),
            "sticky": bool(job.get("sticky") or job.get("sticky_device")),
            "preferred_device": job.get("device_id") or job.get("target_device"),
            "pixels": pixels,
            "vram_requested_gb": vram_required or None,
            "payload_keys": sorted(job.keys()),
        },
        "context": {
            "has_gpu": bool(ctx.get("has_gpu")),
            "local_queue_depth": int(ctx.get("local_queue_depth") or 0),
            "local_vram_gb": float(ctx.get("local_vram_gb") or 0.0),
            "remote_available": bool(ctx.get("remote_available")),
            "remote_queue_depth": int(ctx.get("remote_queue_depth") or 0),
            "notes": ctx.get("notes"),
        },
        "decision": {
            "choice": decision,
            "reason": reason,
        },
        "thresholds": thresholds,
    }
    return hints


def choose_device(
    job: Dict[str, Any],
    ctx: Dict[str, Any],
    *,
    return_details: bool = False,
) -> Tuple[str, str] | Tuple[str, str, Dict[str, Any]]:
    """
    Return ('cpu'|'gpu'|'remote', reason[, details]).

    Set ``return_details=True`` to receive a third dictionary entry with advisor
    inputs, derived values, and thresholds for debugging or telemetry.
    """

    job = job or {}
    ctx = ctx or {}

    size = _infer_pixels(job)
    vram_required = _infer_vram(job)
    has_gpu = bool(ctx.get("has_gpu", False))
    queue_depth = int(ctx.get("local_queue_depth") or 0)
    local_vram = float(ctx.get("local_vram_gb") or 0.0)
    remote_available = bool(ctx.get("remote_available", False))
    remote_queue_depth = int(ctx.get("remote_queue_depth") or 0)

    decision: str
    reason: str

    if not has_gpu:
        decision, reason = "cpu", "no GPU detected on this host"
    elif vram_required and local_vram and vram_required > local_vram + 0.5:
        decision = "remote" if remote_available else "cpu"
        reason = "job requires more VRAM than local GPU provides"
    elif size >= 4096 * 4096:
        if remote_available:
            decision, reason = "remote", "large render; remote GPU suggested"
        else:
            decision, reason = "gpu", "large job but remote providers unavailable"
    elif size <= 512 * 512:
        decision, reason = "cpu", "job is tiny; CPU is sufficient"
    elif queue_depth >= 3 and remote_available:
        decision, reason = "remote", "local GPU queue is busy"
    elif queue_depth >= 5:
        decision, reason = (
            "cpu",
            "local queue saturated; remote unavailable, fallback to CPU",
        )
    elif remote_queue_depth and remote_queue_depth >= 8 and queue_depth < 3:
        decision, reason = "gpu", "remote queue saturated; favor local GPU"
    else:
        decision, reason = "gpu", "local GPU available and queue is light"

    if not return_details:
        return decision, reason

    details = _collect_details(
        job,
        ctx,
        decision=decision,
        reason=reason,
        pixels=size,
        vram_required=vram_required,
    )
    return decision, reason, details
