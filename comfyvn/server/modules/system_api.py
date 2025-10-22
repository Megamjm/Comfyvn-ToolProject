from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from comfyvn.server.system_metrics import collect_system_metrics

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
async def health() -> Dict[str, Any]:
    return {"status": "ok", "ok": True}


@router.get("/status")
async def status(request: Request) -> Dict[str, Any]:
    mode_mgr = getattr(request.app.state, "mode_manager", None)
    mode = mode_mgr.get_mode() if mode_mgr else "default"
    version = getattr(
        request.app, "version", getattr(request.app.state, "version", "unknown")
    )
    return {
        "status": "ok",
        "ok": True,
        "mode": mode,
        "version": version,
        "pid": os.getpid(),
    }


@router.get("/metrics")
async def system_metrics() -> Dict[str, Any]:
    return collect_system_metrics()


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
