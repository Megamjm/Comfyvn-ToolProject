from __future__ import annotations

import io
import tarfile
import time
from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtGui import QAction

try:
    import psutil  # optional
except Exception:
    psutil = None  # type: ignore

try:
    from fastapi import APIRouter
    from fastapi.responses import StreamingResponse
except Exception:
    APIRouter = None  # type: ignore
    StreamingResponse = None  # type: ignore

from comfyvn.core.health import aggregate as _aggregate

LOG_DIRS = [Path("logs")]
DATA_DIRS = [Path("data")]


def _metrics() -> Dict[str, Any]:
    m: Dict[str, Any] = {"time": int(time.time())}
    if psutil is None:
        m["note"] = "psutil not installed"
        return m
    try:
        vm = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
    except Exception:
        vm = type("vm", (), {"total": 0, "used": 0, "percent": 0.0})()
        cpu = 0.0
    disks: Dict[str, Any] = {}
    try:
        for part in psutil.disk_partitions(all=False):
            try:
                du = psutil.disk_usage(part.mountpoint)
                disks[str(part.mountpoint)] = {
                    "total": du.total,
                    "used": du.used,
                    "percent": du.percent,
                }
            except Exception:
                continue
    except Exception:
        pass
    m.update(
        {
            "cpu_percent": cpu,
            "mem": {
                "total": getattr(vm, "total", 0),
                "used": getattr(vm, "used", 0),
                "percent": getattr(vm, "percent", 0.0),
            },
            "disk": disks,
        }
    )
    return m


def _routes(app) -> List[Dict[str, Any]]:
    items = []
    for r in app.routes:
        path = getattr(r, "path", None) or getattr(r, "path_format", None)
        methods = list(getattr(r, "methods", []) or [])
        name = getattr(r, "name", "")
        items.append({"path": str(path), "methods": methods, "name": name})
    items.sort(key=lambda x: x["path"])
    return items


def _diag_bundle() -> bytes:
    memfile = io.BytesIO()
    with tarfile.open(mode="w:gz", fileobj=memfile) as tf:
        for d in LOG_DIRS + DATA_DIRS:
            if d.exists():
                for p in d.rglob("*"):
                    if p.is_file() and p.stat().st_size < 5_000_000:
                        try:
                            tf.add(str(p), arcname=str(p))
                        except Exception:
                            continue
    memfile.seek(0)
    return memfile.read()


def get_ops_router(app_ref=None) -> "APIRouter":
    if APIRouter is None:
        raise RuntimeError("FastAPI not installed")
    r = APIRouter(prefix="/system", tags=["System"])

    @r.get("/ping")
    def ping():
        return {"pong": True}

    @r.get("/health")
    def health(probe: bool = False):
        return _aggregate(probe=probe)

    @r.get("/metrics")
    def metrics():
        return _metrics()

    @r.get("/routes")
    def routes():
        from comfyvn.server.app import \
            app as _app  # local import to avoid cycles

        return {"routes": _routes(_app)}

    @r.get("/diag.tar.gz")
    def diag():
        if StreamingResponse is None:
            return {"ok": False, "reason": "no StreamingResponse"}
        data = _diag_bundle()
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/gzip",
            headers={"Content-Disposition": "attachment; filename=diag.tar.gz"},
        )

    return r
