from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/server/modules/system_api.py
import os, shutil, psutil, subprocess, requests
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException

router = APIRouter(prefix="/system", tags=["System"])

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "comfyvn" / "data"
TEMPLATES_DIR = DATA_DIR / "templates"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
EXPORTS_DIR = ROOT / "exports"
LOGS_DIR = ROOT / "logs"

for p in [DATA_DIR, TEMPLATES_DIR, SNAPSHOT_DIR, EXPORTS_DIR, LOGS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

@router.get("/health")
async def health():
    return {"status": "ok"}

@router.get("/status")
async def status(request: Request):
    mode_mgr = getattr(request.app.state, "mode_manager", None)
    mode = mode_mgr.get_mode() if mode_mgr else "default"
    return {"ok": True, "mode": mode, "version": getattr(request.app, "version", "unknown"), "pid": os.getpid()}

@router.get("/metrics")
async def system_metrics():
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage(ROOT).percent
        gpus = []
        try:
            out = subprocess.check_output(
                ["nvidia-smi",
                 "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL, text=True
            ).strip()
            for line in out.splitlines():
                idx, name, util, mused, mtotal, temp = [x.strip() for x in line.split(",")]
                gpus.append({"id": int(idx), "name": name, "util": int(util),
                             "mem_used": int(mused), "mem_total": int(mtotal), "temp_c": int(temp)})
        except Exception:
            pass
        return {"ok": True, "cpu": cpu, "mem": mem, "disk": disk, "gpus": gpus}
    except Exception as e:
        raise HTTPException(500, f"metrics error: {e}")

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