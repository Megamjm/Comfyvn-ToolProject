# comfyvn/server/modules/system_api.py
# 🖥 System API — Metrics, Verification, Connections & Restore
# [Server Core Production Chat | ComfyVN v3.1.1 Integration Sync]

from __future__ import annotations
import os, shutil, psutil, subprocess, requests
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException

router = APIRouter(prefix="/system", tags=["System"])

# -------------------------------------------------------------------
# 📁 Paths
# -------------------------------------------------------------------
DATA_DIR = Path("comfyvn/data")
TEMPLATES_DIR = DATA_DIR / "templates"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
EXPORTS_DIR = Path("exports")
LOGS_DIR = Path("logs")

for p in [DATA_DIR, TEMPLATES_DIR, SNAPSHOT_DIR, EXPORTS_DIR, LOGS_DIR]:
    p.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------------------------
# 🩺 Status
# -------------------------------------------------------------------
@router.get("/status")
async def status(request: Request):
    """Return basic runtime info."""
    mode_mgr = getattr(request.app.state, "mode_manager", None)
    mode = mode_mgr.get_mode() if mode_mgr else "default"
    return {
        "ok": True,
        "mode": mode,
        "version": getattr(request.app, "version", "unknown"),
        "pid": os.getpid(),
    }


# -------------------------------------------------------------------
# 📊 Metrics
# -------------------------------------------------------------------
@router.get("/metrics")
async def system_metrics():
    """System metrics for GUI dashboard."""
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage(".").percent

        # Optional GPU check (non-fatal)
        gpus = []
        try:
            out = (
                subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
            for line in out.splitlines():
                idx, name, util, mused, mtotal, temp = [
                    x.strip() for x in line.split(",")
                ]
                gpus.append(
                    {
                        "id": int(idx),
                        "name": name,
                        "util": int(util),
                        "mem_used": int(mused),
                        "mem_total": int(mtotal),
                        "temp_c": int(temp),
                    }
                )
        except Exception:
            pass

        return {"ok": True, "cpu": cpu, "mem": mem, "disk": disk, "gpus": gpus}
    except Exception as e:
        raise HTTPException(500, f"metrics error: {e}")


# -------------------------------------------------------------------
# 🔌 Connections Probe
# -------------------------------------------------------------------
@router.get("/connections")
async def connections(request: Request):
    """
    Test connectivity to key integrations (ComfyUI, SillyTavern, LM Studio).
    Used by the Playground and Integrations drawer.
    """
    s = getattr(request.app.state, "settings", None)
    comfyui_url = getattr(s, "COMFYUI_NODE_PATH", "http://127.0.0.1:8188")
    api_base = getattr(s, "API_BASE", "http://127.0.0.1:8001")
    st_url = getattr(s, "SILLYTAVERN_URL", "http://127.0.0.1:8000")
    lmstudio_url = "http://127.0.0.1:1234/v1"

    def ok(url):
        try:
            r = requests.get(url, timeout=2)
            return r.status_code < 400
        except Exception:
            return False

    return {
        "ok": True,
        "connections": {
            "comfyvn_api": {"host": api_base, "ok": ok(f"{api_base}/health")},
            "comfyui": {"host": comfyui_url, "ok": ok(comfyui_url)},
            "sillytavern": {"host": st_url, "ok": ok(st_url)},
            "lmstudio": {"host": lmstudio_url, "ok": ok(lmstudio_url)},
        },
    }


# -------------------------------------------------------------------
# 🧩 Verify Data Structure
# -------------------------------------------------------------------
@router.post("/verify_data")
async def verify_data():
    """Ensure expected data folders exist and repair missing ones."""
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


# -------------------------------------------------------------------
# 🧰 Restore Defaults
# -------------------------------------------------------------------
@router.post("/restore_defaults")
async def restore_defaults():
    """
    Restore baseline files from comfyvn/data/templates → comfyvn/data/.
    Safe operation: overwrites known subfolders (poses, configs, styles).
    """
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


# -------------------------------------------------------------------
# 🧮 Settings Schema
# -------------------------------------------------------------------
@router.get("/settings/schema")
async def schema():
    """Expose Pydantic settings schema for GUI form rendering."""
    from comfyvn.core.settings_manager import Settings

    return {"schema": Settings.model_json_schema()}
