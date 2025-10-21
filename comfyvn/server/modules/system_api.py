from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import psutil
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/system", tags=["System"])

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "comfyvn" / "data"
TEMPLATES_DIR = DATA_DIR / "templates"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
EXPORTS_DIR = ROOT / "exports"
LOGS_DIR = ROOT / "logs"

for path in (DATA_DIR, TEMPLATES_DIR, SNAPSHOT_DIR, EXPORTS_DIR, LOGS_DIR):
    path.mkdir(parents=True, exist_ok=True)


@router.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@router.get("/status")
async def status(request: Request) -> Dict[str, Any]:
    mode_mgr = getattr(request.app.state, "mode_manager", None)
    mode = mode_mgr.get_mode() if mode_mgr else "default"
    version = getattr(request.app, "version", getattr(request.app.state, "version", "unknown"))
    return {"status": "ok", "mode": mode, "version": version, "pid": os.getpid()}


def _query_gpus() -> List[Dict[str, Any]]:
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    gpus: List[Dict[str, Any]] = []
    for line in output.splitlines():
        try:
            idx, name, util, mem_used, mem_total, temp = [segment.strip() for segment in line.split(",")]
            gpus.append(
                {
                    "id": int(idx),
                    "name": name,
                    "util": int(util),
                    "mem_used": int(mem_used),
                    "mem_total": int(mem_total),
                    "temp_c": int(temp),
                }
            )
        except ValueError:
            continue
    return gpus


@router.get("/metrics")
async def system_metrics() -> Dict[str, Any]:
    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage(ROOT).percent
        return {"cpu": cpu, "mem": mem, "disk": disk, "gpus": _query_gpus()}
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"metrics error: {exc}")

@router.post("/verify_data")
async def verify_data():
    checks = []
    for p in [DATA_DIR, TEMPLATES_DIR, SNAPSHOT_DIR, EXPORTS_DIR, LOGS_DIR]:
        ok = p.exists() and p.is_dir()
        if not ok:
            try:
                p.mkdir(parents=True, exist_ok=True)
                ok = True
            except Exception:
                ok = False
        checks.append({"path": str(p), "ok": ok})
    return {"ok": all(c["ok"] for c in checks), "checks": checks}

@router.post("/restore_defaults")
async def restore_defaults():
    targets = ["poses", "configs", "styles"]
    restored = []
    for name in targets:
        src = TEMPLATES_DIR / name
        dst = DATA_DIR / name
        try:
            if dst.exists():
                shutil.rmtree(dst)
            if src.exists():
                shutil.copytree(src, dst)
                restored.append({"name": name, "restored": True})
            else:
                restored.append({"name": name, "restored": False})
        except Exception as e:
            raise HTTPException(500, f"restore {name} failed: {e}")
    return {"ok": True, "restored": restored}
