from __future__ import annotations

import time
from typing import Any, Dict, List

from PySide6.QtGui import QAction


class DeviceRegistry:
    def __init__(self):
        self._d: Dict[str, Dict[str, Any]] = {}

    def register(
        self, name: str, kind: str, info: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        item = {
            "name": name,
            "kind": kind,
            "info": dict(info or {}),
            "status": "idle",
            "ts": time.time(),
        }
        self._d[name] = item
        return item

    def set_status(self, name: str, status: str, **kw) -> Dict[str, Any]:
        row = self._d.setdefault(
            name,
            {"name": name, "kind": "unknown", "info": {}, "status": "idle", "ts": 0},
        )
        row["status"] = status
        row["ts"] = time.time()
        row.update(kw)
        return row

    def list(self) -> List[Dict[str, Any]]:
        return list(self._d.values())

    def get(self, name: str) -> Dict[str, Any] | None:
        return self._d.get(name)
