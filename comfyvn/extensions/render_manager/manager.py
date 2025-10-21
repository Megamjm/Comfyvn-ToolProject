from __future__ import annotations

import random
# comfyvn/extensions/render_manager/manager.py
import threading
import time

from PySide6.QtGui import QAction

from comfyvn.core.task_registry import task_registry


class RenderJob:
    def __init__(self, job_id: str, payload: dict):
        self.id = job_id
        self.payload = payload
        self.progress = 0.0
        self.status = "queued"


class RenderManager:
    def __init__(self):
        self._jobs: dict[str, RenderJob] = {}
        self._lock = threading.Lock()

    def submit(self, payload: dict):
        item = task_registry.create("render", "Queued render", {"payload": payload})
        job = RenderJob(item.id, payload)
        with self._lock:
            self._jobs[item.id] = job
        t = threading.Thread(target=self._simulate_job, args=(job,), daemon=True)
        t.start()
        return job

    def _simulate_job(self, job: RenderJob):
        task_registry.update(job.id, status="running", message="Rendering started")
        for i in range(1, 11):
            time.sleep(random.uniform(0.2, 0.6))
            job.progress = i * 10
            task_registry.update(job.id, progress=job.progress)
        job.status = "done"
        task_registry.update(job.id, status="done", message="Render complete")


render_manager = RenderManager()
