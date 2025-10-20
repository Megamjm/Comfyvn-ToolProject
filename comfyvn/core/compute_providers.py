from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/compute_providers.py
import httpx, json, time

def _http_get(url: str, headers=None, timeout=5.0):
    r = httpx.get(url, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    return r.json() if r.headers.get("content-type","").startswith("application/json") else r.text

def _http_post(url: str, body: dict, headers=None, timeout=10.0):
    r = httpx.post(url, json=body, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    return r.json() if r.headers.get("content-type","").startswith("application/json") else r.text

def comfyui_health(base: str) -> dict:
    try:
        _ = _http_get(base.rstrip("/") + "/system_stats")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def comfyui_send(base: str, payload: dict) -> dict:
    try:
        res = _http_post(base.rstrip("/") + "/prompt", payload)
        return {"ok": True, "result": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def service_health(base: str, auth: str|None) -> dict:
    try:
        _ = _http_get(base.rstrip("/"))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def service_send(base: str, payload: dict, auth: str|None) -> dict:
    try:
        return {"ok": True, "echo": {"base": base, "payload": payload, "auth_set": bool(auth)}}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def send_job(provider: dict, payload: dict) -> dict:
    t = (provider.get("service") or provider.get("type") or "").lower()
    base = provider.get("base", "").strip()
    auth = provider.get("auth") or None
    if t in ("comfyui", "local"):
        return comfyui_send(base, payload)
    else:
        return service_send(base, payload, auth)

def health(provider: dict) -> dict:
    t = (provider.get("service") or provider.get("type") or "").lower()
    base = provider.get("base", "").strip()
    auth = provider.get("auth") or None
    if t in ("comfyui", "local"):
        return comfyui_health(base)
    else:
        return service_health(base, auth)