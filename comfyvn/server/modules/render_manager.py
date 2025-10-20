from PySide6.QtGui import QAction
# comfyvn/server/core/render_manager.py
import time, json, itertools
from pathlib import Path

STATE = Path("data/state/render_state.json")

class RenderManager:
    def __init__(self):
        self._seq = itertools.count(1)
        self._jobs = {}
        self.load_state()

    def _save_state(self):
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(self._jobs, indent=2), encoding="utf-8")

    def load_state(self):
        if STATE.exists():
            try:
                self._jobs = json.loads(STATE.read_text(encoding="utf-8"))
                c = max((int(j[1:]) for j in self._jobs.keys()), default=0)
                self._seq = itertools.count(c + 1)
            except Exception:
                self._jobs = {}

    def list(self): return list(self._jobs.values())

    def enqueue(self, payload: dict):
        jid = f"r{next(self._seq)}"
        job = {
            "id": jid,
            "ts": int(time.time()),
            "type": payload.get("type","image"),
            "queue": payload.get("queue","render"),
            "priority": int(payload.get("priority",5)),
            "device": payload.get("device","cpu"),
            "prompt": payload.get("prompt",""),
            "status": "queued",
        }
        self._jobs[jid] = job
        self._save_state()
        return job

    def reprioritize(self, job_id: str, priority: int):
        j = self._jobs.get(job_id)
        if not j: return False
        j["priority"] = int(priority)
        self._save_state()
        return True

    def set_device(self, job_id: str, device: str):
        j = self._jobs.get(job_id)
        if not j: return False
        j["device"] = device
        self._save_state()
        return True

    def reset(self):
        self._jobs.clear()
        self._save_state()
        return True