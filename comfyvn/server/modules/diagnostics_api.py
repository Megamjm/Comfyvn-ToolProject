from PySide6.QtGui import QAction
# comfyvn/server/modules/diagnostics_api.py
import psutil, platform, shutil, time, socket
from fastapi import APIRouter

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

@router.get("/summary")
def summary():
    disk = shutil.disk_usage(".")
    return {
        "ok": True,
        "hostname": socket.gethostname(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": psutil.cpu_percent(interval=0.1),
        "mem": psutil.virtual_memory().percent,
        "disk_free_gb": round(disk.free / 1024**3, 2),
    }

@router.get("/queues")
def queue_stats():
    from comfyvn.server.app import app
    jm = getattr(app.state, "job_manager", None)
    rm = getattr(app.state, "render_manager", None)
    return {
        "ok": True,
        "jobs_total": len(jm._jobs) if jm else 0,
        "renders_total": len(rm._jobs) if rm else 0,
    }


@router.get("/registry")
def registry_snapshot():
    from comfyvn.server.app import app
    reg = getattr(app.state, "system_registry", None)
    return {"ok": True, "registry": reg.info() if reg else {}}