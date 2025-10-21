from __future__ import annotations
from PySide6.QtGui import QAction
import json, time
from pathlib import Path
from typing import Dict, Any, Optional, List
from comfyvn.config.runtime_paths import render_cache_dir

DEFAULT_DIR = render_cache_dir()

class RenderCache:
    def __init__(self, root: str|Path = DEFAULT_DIR):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        safe = "".join(c for c in job_id if c.isalnum() or c in ("-", "_"))
        return self.root / f"{safe}.json"

    def save(self, job_id: str, payload: Dict[str, Any]):
        data = dict(payload)
        data.setdefault("updated", time.time())
        self._path(job_id).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self, job_id: str) -> Dict[str, Any]:
        p = self._path(job_id)
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    def list(self) -> List[str]:
        return [p.stem for p in self.root.glob("*.json")]

    def cleanup(self, ttl: int = 3600 * 12):
        now = time.time()
        for p in self.root.glob("*.json"):
            try:
                if now - p.stat().st_mtime > ttl:
                    p.unlink(missing_ok=True)
            except Exception:
                pass
