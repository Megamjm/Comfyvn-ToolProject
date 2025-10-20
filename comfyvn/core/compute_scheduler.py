from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/compute_scheduler.py
from typing import Dict, Any, List
from .compute_providers import send_job, health

def pick_and_send(settings: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    rset = settings.get("render") or {}
    order: List[str] = rset.get("priority_order") or []
    providers: Dict[str, Dict[str, Any]] = rset.get("providers") or {}
    if not order:
        raise RuntimeError("No providers in priority_order")
    last_err = None
    for pid in order:
        prov = providers.get(pid)
        if not prov or not prov.get("active", True):
            continue
        try:
            res = send_job(prov, payload)
            if res.get("ok"):
                return {"ok": True, "provider": pid, "result": res}
            last_err = res
        except Exception as e:
            last_err = {"ok": False, "error": str(e), "provider": pid}
            continue
    return {"ok": False, "error": last_err or "no provider accepted", "provider": None}