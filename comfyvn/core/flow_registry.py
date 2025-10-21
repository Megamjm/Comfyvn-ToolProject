from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtGui import QAction

try:
    from fastapi import APIRouter, Body, HTTPException
except Exception:
    APIRouter = None  # type: ignore

SEARCH_DIRS = [Path("comfyvn/flows"), Path("data/flows")]
STATE_DIR = Path("data/state")
STATE_DIR.mkdir(parents=True, exist_ok=True)
ACTIVE_FILE = STATE_DIR / "flow.json"


class FlowRegistry:
    def __init__(self) -> None:
        self._by_id: Dict[str, Dict[str, Any]] = {}
        self._active: Optional[str] = None

    def refresh(self) -> None:
        self._by_id.clear()
        for root in SEARCH_DIRS:
            if not root.exists():
                continue
            for p in root.glob("*.json"):
                try:
                    obj = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                    fid = obj.get("id") or p.stem
                    obj.setdefault("id", fid)
                    obj.setdefault("source_path", str(p))
                    self._by_id[fid] = obj
                except Exception:
                    continue
        if ACTIVE_FILE.exists():
            try:
                self._active = json.loads(ACTIVE_FILE.read_text(encoding="utf-8")).get(
                    "active_flow"
                )
            except Exception:
                self._active = None

    def list(self) -> List[Dict[str, Any]]:
        if not self._by_id:
            self.refresh()
        return sorted(self._by_id.values(), key=lambda o: o.get("id", ""))

    def get(self, flow_id: str) -> Dict[str, Any]:
        if not self._by_id:
            self.refresh()
        if flow_id not in self._by_id:
            raise KeyError(flow_id)
        return self._by_id[flow_id]

    def active(self) -> Optional[str]:
        if not self._by_id:
            self.refresh()
        return self._active

    def set_active(self, flow_id: str) -> Dict[str, Any]:
        if not self._by_id:
            self.refresh()
        if flow_id not in self._by_id:
            raise KeyError(flow_id)
        self._active = flow_id
        ACTIVE_FILE.write_text(
            json.dumps({"active_flow": flow_id}, indent=2), encoding="utf-8"
        )
        return {"ok": True, "active_flow": flow_id}


def get_flow_router() -> "APIRouter":
    if APIRouter is None:
        raise RuntimeError("FastAPI not installed")
    reg = FlowRegistry()
    r = APIRouter(prefix="/flows", tags=["Flows"])

    @r.get("")
    def list_flows():
        return {"items": reg.list(), "count": len(reg._by_id), "active": reg.active()}

    @r.get("/{flow_id}")
    def get_flow(flow_id: str):
        try:
            return reg.get(flow_id)
        except KeyError:
            raise HTTPException(404, f"Flow not found: {flow_id}")

    @r.post("/refresh")
    def refresh():
        reg.refresh()
        return {"ok": True, "count": len(reg._by_id), "active": reg.active()}

    @r.get("/active")
    def get_active():
        return {"active": reg.active()}

    @r.post("/active")
    def set_active(flow_id: str = Body(..., embed=True)):
        try:
            return reg.set_active(flow_id)
        except KeyError:
            raise HTTPException(404, f"Flow not found: {flow_id}")

    return r
