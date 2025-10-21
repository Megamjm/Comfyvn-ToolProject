from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtGui import QAction

from comfyvn.core.feedback_tracker import FeedbackTracker
from comfyvn.core.render_cache import RenderCache

# Tracks active jobs, completion, and auto-refresh for scenes.


class JobLifecycle:
    def __init__(self, root: str | Path = "data/jobs/state"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.fb = FeedbackTracker()
        self.cache = RenderCache()
        self.jobs: Dict[str, Dict[str, Any]] = {}

    def add(self, job_id: str, payload: Dict[str, Any]):
        payload = dict(payload)
        payload["ts"] = time.time()
        payload["state"] = "queued"
        self.jobs[job_id] = payload
        self._save(job_id, payload)

    def mark_done(self, job_id: str, output: Dict[str, Any]):
        if job_id not in self.jobs:
            self.jobs[job_id] = {"id": job_id, "state": "unknown"}
        self.jobs[job_id]["state"] = "done"
        self.jobs[job_id]["done_ts"] = time.time()
        self.jobs[job_id]["output"] = output
        self.cache.save(job_id, output)
        self.fb.append(job_id, {"event": "complete", "output": output})
        self._save(job_id, self.jobs[job_id])

    def heartbeat(self, job_id: str, msg: str):
        self.fb.append(job_id, {"event": "heartbeat", "msg": msg, "ts": time.time()})

    def cleanup(self, ttl: int = 7200):
        now = time.time()
        for job_id, meta in list(self.jobs.items()):
            if now - meta.get("ts", now) > ttl:
                self.jobs.pop(job_id, None)
                try:
                    (self.root / f"{job_id}.json").unlink(missing_ok=True)
                except Exception:
                    pass

    def _save(self, job_id: str, data: Dict[str, Any]):
        (self.root / f"{job_id}.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def load(self, job_id: str) -> Dict[str, Any]:
        p = self.root / f"{job_id}.json"
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    def list_jobs(self) -> List[str]:
        return sorted([p.stem for p in self.root.glob("*.json")])
