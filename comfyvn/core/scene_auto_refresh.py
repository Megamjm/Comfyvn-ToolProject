from __future__ import annotations
from PySide6.QtGui import QAction
import time, json
from pathlib import Path
from typing import Dict, Any, List
#   \"\"\"Tracks scenes needing refresh when render or job completes.\"\"\"

class SceneAutoRefresh:

    def __init__(self, root: str|Path = "data/scene_refresh"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._pending: Dict[str, Dict[str, Any]] = {}

    def add(self, scene_id: str, job_id: str):
        self._pending[scene_id] = {"job_id": job_id, "added": time.time()}
        self._save(scene_id)

    def refresh_ready(self, ttl: int = 300) -> List[str]:
        now = time.time()
        ready = []
        for sid, meta in list(self._pending.items()):
            if now - meta["added"] > ttl:
                ready.append(sid)
        return ready

    def _save(self, scene_id: str):
        (self.root / f"{scene_id}.json").write_text(
            json.dumps(self._pending[scene_id], indent=2), encoding="utf-8"
        )

    def list(self) -> List[str]:
        return list(self._pending.keys())