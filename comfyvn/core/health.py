from __future__ import annotations
from PySide6.QtGui import QAction
import os, time
from typing import Dict, Any
from urllib.parse import urlparse

try:
    import httpx
except Exception:
    httpx = None  # type: ignore

try:
    from fastapi import APIRouter, Query
except Exception:
    APIRouter = None  # type: ignore

from comfyvn.core.boot_checks import BootChecks

DEFAULT_TIMEOUT = 1.0

def _probe_url(url: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    if not url:
        return {"ok": False, "reason": "empty"}
    try:
        parsed = urlparse(url)
        if not parsed.scheme:
            return {"ok": False, "reason": "invalid"}
    except Exception as e:
        return {"ok": False, "reason": f"invalid:{e.__class__.__name__}"}
    if httpx is None:
        return {"ok": None, "reason": "httpx-missing", "url": url}
    try:
        r = httpx.get(url, timeout=timeout)
        return {"ok": bool(r.status_code and r.status_code < 500), "status": r.status_code, "url": url}
    except Exception as e:
        return {"ok": False, "reason": e.__class__.__name__, "url": url}

def _env(k: str, default: str = "") -> str:
    return os.environ.get(k, default).strip()

def aggregate(probe: bool = False) -> Dict[str, Any]:
    checks = BootChecks.run(strict=False)
    deps: Dict[str, Any] = {}
    comfyui = _env("COMFYUI_BASE")
    lmstudio = _env("LMSTUDIO_BASE")
    st = _env("ST_BASE")
    renpy = _env("RENPY_IPC")
    deps["comfyui"] = {"base": comfyui}
    deps["lmstudio"] = {"base": lmstudio}
    deps["sillytavern"] = {"base": st}
    deps["renpy_ipc"] = {"base": renpy}
    if probe:
        for k in ["comfyui", "lmstudio", "sillytavern"]:
            base = deps[k]["base"]
            if base:
                deps[k]["probe"] = _probe_url(base)
            else:
                deps[k]["probe"] = {"ok": None, "reason": "unset"}
    ok = not checks.get("errors")
    return {"ok": ok, "boot": checks, "deps": deps, "ts": int(time.time()), "version": os.environ.get("COMFYVN_VERSION", "")}

def get_health_router() -> "APIRouter":
    if APIRouter is None:
        raise RuntimeError("FastAPI not installed")
    r = APIRouter(prefix="/system", tags=["System"])
    @r.get("/ping")
    def ping():
        return {"pong": True}
    @r.get("/health")
    def health(probe: bool = Query(False, description="If true, probe dependencies")):
        return aggregate(probe=probe)
    return r