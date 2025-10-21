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


def choose_device(job: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[str, str]:
    """Return ('cpu'|'gpu'|'remote', reason). Super cheap heuristic."""

    size = _infer_pixels(job or {})
    vram_required = _infer_vram(job or {})
    has_gpu = bool(ctx.get("has_gpu", False))
    queue_depth = int(ctx.get("local_queue_depth") or 0)
    local_vram = float(ctx.get("local_vram_gb") or 0.0)
    remote_available = bool(ctx.get("remote_available", False))

    if not has_gpu:
        return "cpu", "no GPU detected on this host"

    if vram_required and local_vram and vram_required > local_vram + 0.5:
        return (
            "remote" if remote_available else "cpu",
            "job requires more VRAM than local GPU provides",
        )

    if size >= 4096 * 4096:
        if remote_available:
            return "remote", "large render; remote GPU suggested"
        return "gpu", "large job but remote providers unavailable"

    if size <= 512 * 512:
        return "cpu", "job is tiny; CPU is sufficient"

    if queue_depth >= 3 and remote_available:
        return "remote", "local GPU queue is busy"

    if queue_depth >= 5:
        return "cpu", "local queue saturated; remote unavailable, fallback to CPU"

    return "gpu", "local GPU available and queue is light"
