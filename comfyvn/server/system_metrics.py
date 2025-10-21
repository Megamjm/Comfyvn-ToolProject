from __future__ import annotations

"""System metrics helpers shared by server endpoints and GUI clients."""

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _safe_import_psutil():
    try:
        import psutil  # type: ignore
    except Exception as exc:  # pragma: no cover - defensive guard
        return None, exc
    return psutil, None


def _collect_gpu_metrics() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []

    # Prefer NVML when present to avoid spawning subprocesses on every call.
    try:
        import pynvml  # type: ignore
    except Exception:
        pynvml = None  # type: ignore

    if pynvml is not None:
        try:
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            for idx in range(count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
                name = pynvml.nvmlDeviceGetName(handle).decode(
                    "utf-8", errors="replace"
                )
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                temp = pynvml.nvmlDeviceGetTemperature(
                    handle, pynvml.NVML_TEMPERATURE_GPU
                )
                entries.append(
                    {
                        "id": idx,
                        "name": name,
                        "util": int(getattr(util, "gpu", 0)),
                        "mem_used": int(mem.used // (1024 * 1024)),
                        "mem_total": int(mem.total // (1024 * 1024)),
                        "temp_c": int(temp),
                    }
                )
        except Exception:
            entries.clear()
        finally:
            try:
                pynvml.nvmlShutdown()
            except Exception:  # pragma: no cover - shutdown best effort
                pass

    if entries:
        return entries

    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return entries

    query_args = [
        nvidia_smi,
        "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(
            query_args,
            capture_output=True,
            text=True,
            check=True,
            timeout=0.6,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return entries

    for line in result.stdout.splitlines():
        parts = [segment.strip() for segment in line.split(",")]
        if len(parts) != 6:
            continue
        idx, name, util, mem_used, mem_total, temp = parts
        try:
            entries.append(
                {
                    "id": int(idx),
                    "name": name,
                    "util": int(float(util)),
                    "mem_used": int(float(mem_used)),
                    "mem_total": int(float(mem_total)),
                    "temp_c": int(float(temp)),
                }
            )
        except (TypeError, ValueError):
            continue
    return entries


def collect_system_metrics() -> Dict[str, Any]:
    """Return a lightweight snapshot of CPU, RAM, and (first) GPU state."""

    psutil, exc = _safe_import_psutil()
    if psutil is None:
        return {
            "ok": False,
            "error": f"psutil unavailable: {exc}",
            "cpu": None,
            "mem": None,
            "disk": None,
            "gpus": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    cpu_percent = float(psutil.cpu_percent(interval=0.05))
    mem_info = psutil.virtual_memory()
    disk_info = psutil.disk_usage(Path("."))

    metrics: Dict[str, Any] = {
        "ok": True,
        "cpu": round(cpu_percent, 2),
        "mem": round(float(mem_info.percent), 2),
        "mem_used_mb": int(mem_info.used // (1024 * 1024)),
        "mem_total_mb": int(mem_info.total // (1024 * 1024)),
        "disk": round(float(disk_info.percent), 2),
        "disk_used_gb": round(float(disk_info.used) / (1024**3), 2),
        "disk_total_gb": round(float(disk_info.total) / (1024**3), 2),
        "gpus": _collect_gpu_metrics(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if metrics["gpus"]:
        metrics["first_gpu"] = metrics["gpus"][0]
    else:
        metrics["first_gpu"] = None
    return metrics
