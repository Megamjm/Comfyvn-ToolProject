from PySide6.QtGui import QAction

# comfyvn/server/modules/gpu_api.py
# Minimal GPU endpoints (safe if nvidia-smi missing)

from fastapi import APIRouter
import subprocess, shutil, json, os

router = APIRouter(prefix="/gpu", tags=["GPU"])

def _list_local():
    gpus = []
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            for line in out.splitlines():
                idx, name, util, mused, mtotal, temp = [x.strip() for x in line.split(",")]
                gpus.append({
                    "id": int(idx), "name": name, "util": int(util),
                    "mem_used": int(mused), "mem_total": int(mtotal), "temp_c": int(temp)
                })
        except Exception:
            pass
    return gpus

@router.get("/list")
def list_gpus():
    return {"gpus": _list_local()}

PROVIDERS = [
    {"name":"RunPod", "howto":"Provision a GPU pod. Open ports 8001/8188. Install Python + ComfyVN server deps. Set COMFYVN_PORT. Return API at /system/metrics and /gpu/list."},
    {"name":"Vast.ai", "howto":"Rent a machine with CUDA. Docker or bare-metal. Expose HTTP. Install ComfyVN server minimal, start with uvicorn."},
    {"name":"Lambda", "howto":"EC2-like instances. Install NVIDIA drivers + Docker (optional). Deploy server container; expose 8001."},
    {"name":"Unraid/Local Node", "howto":"Enable Docker/NVIDIA plugin. Deploy a ComfyVN worker container on LAN; point Studio to http://node:8001."},
]

@router.get("/providers")
def providers():
    return {"providers": PROVIDERS}

# very light remote registry (in-mem + optional file)
_REMOTE_FILE = "config/remote_gpus.json"
_REG = None

def _load():
    global _REG
    if _REG is not None:
        return _REG
    try:
        with open(_REMOTE_FILE, "r", encoding="utf-8") as f:
            _REG = json.load(f)
    except Exception:
        _REG = {"endpoints": []}
    return _REG

def _save():
    os.makedirs("config", exist_ok=True)
    with open(_REMOTE_FILE, "w", encoding="utf-8") as f:
        json.dump(_REG, f, indent=2)

@router.post("/remote/register")
def remote_register(payload: dict):
    reg = _load()
    ep = payload.get("endpoint","").strip()
    if not ep:
        return {"ok": False, "error":"missing endpoint"}
    reg["endpoints"].append({"endpoint": ep, "notes": payload.get("notes","")})
    _save()
    return {"ok": True}

@router.get("/remote/list")
def remote_list():
    return _load()

@router.post("/remote/save")
def remote_save(payload: dict):
    global _REG
    _REG = {"endpoints": payload.get("endpoints", [])}
    _save()
    return {"ok": True}