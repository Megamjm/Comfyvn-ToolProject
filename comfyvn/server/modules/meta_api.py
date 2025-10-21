from __future__ import annotations

# comfyvn/server/modules/meta_api.py
import os
import sys
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, Request
from PySide6.QtGui import QAction

from comfyvn.config.baseurl_authority import default_base_url

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/info")
def info():
    env_vars = {k: v for k, v in os.environ.items() if k.startswith("COMFYVN_")}
    return {
        "name": "ComfyVN",
        "version": "3.5.0",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "env": env_vars,
    }


@router.get("/routes")
def routes(request: Request):
    items: List[Dict[str, Any]] = []
    for r in request.app.routes:
        try:
            path = getattr(r, "path", None) or getattr(r, "path_format", None) or str(r)
            methods = sorted(getattr(r, "methods", []) or [])
            name = getattr(r, "name", None) or getattr(
                getattr(r, "endpoint", None), "__name__", "unknown"
            )
            tags = getattr(r, "tags", []) or []
            items.append({"path": path, "methods": methods, "name": name, "tags": tags})
        except Exception:
            continue
    return {"count": len(items), "routes": items}


def _probe_one(c: httpx.Client, url: str) -> Dict[str, Any]:
    try:
        r = c.get(url)
        return {"status": r.status_code, "ok": 200 <= r.status_code < 300}
    except Exception:
        return {"status": 0, "ok": False}


@router.get("/checks")
def checks(base: str | None = None, timeout_s: float = 2.0):
    base = (base or default_base_url()).rstrip("/")
    paths = {
        "system": ["/system/health", "/v1/system/health"],
        "render": ["/render/health", "/v1/render/health"],
        "scanner": ["/scanner/health", "/v1/scanner/health"],
        "jobs": ["/jobs/health", "/v1/jobs/health"],
        "metrics": ["/metrics"],
    }
    out: Dict[str, Any] = {}
    try:
        with httpx.Client(timeout=float(timeout_s)) as c:
            for k, variants in paths.items():
                res = {"status": 0, "ok": False}
                for pth in variants:
                    res = _probe_one(c, f"{base}{pth}")
                    if res["ok"]:
                        break
                out[k] = res
    except Exception:
        out = {k: {"status": 0, "ok": False} for k in paths.keys()}
    overall = all(v.get("ok") for v in out.values()) if out else False
    return {
        "ok": overall,
        "timeout_s": float(timeout_s),
        "base": base,
        "components": out,
    }


@router.get("/self-test")
def self_test(request: Request):
    st = getattr(request.app, "state", None)
    state = {
        "event_bus": bool(getattr(st, "event_bus", None)),
        "plugins": bool(getattr(st, "plugins", None)),
        "job_manager": bool(getattr(st, "job_manager", None)),
        "render_manager": bool(getattr(st, "render_manager", None)),
    }

    def has(path: str) -> bool:
        return any(getattr(r, "path", None) == path for r in request.app.routes)

    probes = {
        "system": {
            "status": 200 if has("/system/health") else 404,
            "ok": has("/system/health"),
        },
        "render": {
            "status": 200 if has("/render/health") else 404,
            "ok": has("/render/health"),
        },
        "scanner": {
            "status": 200 if has("/scanner/health") else 404,
            "ok": has("/scanner/health"),
        },
        "jobs": {
            "status": 200 if has("/jobs/health") else 404,
            "ok": has("/jobs/health"),
        },
    }
    return {
        "ok": all(v["ok"] for v in probes.values()),
        "state": state,
        "fs": {"ok": True, "error": None},
        "probes": probes,
    }
