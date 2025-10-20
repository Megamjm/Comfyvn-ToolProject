from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/core/job_manager.py
# ⚙️ Job Manager — Async + EventBus Integration (v3.3)
# [Server Core Production Chat | ComfyVN Architect Sync]

import os, json, time, uuid, asyncio
from typing import Dict, Any, List, Optional
from comfyvn.core.event_bus import EventBus

LOG_DIR = "logs/jobs"
MAX_LOG_FILES = 10


class JobManager:
    """Tracks render/export tasks, supports persistence, rotation, and async event publishing."""

    def __init__(self, event_bus: Optional[EventBus] = None):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.event_bus = event_bus or EventBus()

    # ------------------------------------------------------------
    # Event Emission
    # ------------------------------------------------------------
    async def _emit_async(self, evt_type: str, job: Dict[str, Any]):
        """Async broadcast helper for Job events."""
        if not self.event_bus:
            return
        await self.event_bus.broadcast(
            {"type": evt_type, "job": job, "ts": int(time.time() * 1000)}
        )

    def _emit(self, evt_type: str, job: Dict[str, Any]):
        """Thread-safe wrapper for broadcasting job events."""
        if not self.event_bus:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._emit_async(evt_type, job))
        except RuntimeError:
            asyncio.run(self._emit_async(evt_type, job))

    # ------------------------------------------------------------
    # Job Lifecycle
    # ------------------------------------------------------------
    def create(
        self,
        job_type: str,
        payload: Dict[str, Any],
        origin: str = "server",
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        job_id = str(uuid.uuid4())[:8]
        job = {
            "id": job_id,
            "type": job_type,
            "status": "queued",
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "payload": payload,
            "progress": 0.0,
            "result": None,
            "origin": origin,
            "token": token or f"t-{uuid.uuid4().hex[:10]}",
        }
        self.jobs[job_id] = job
        self._log(job)
        self._emit("job.created", job)
        return job

    def update(self, job_id: str, **updates):
        job = self.jobs.get(job_id)
        if not job:
            print(f"[JobManager] Unknown job: {job_id}")
            return
        job.update(updates)
        self._log(job)
        self._emit("job.updated", job)

    def progress(self, job_id: str, progress: float):
        """Convenience progress update."""
        self.update(job_id, progress=progress)

    def complete(self, job_id: str, result: Any):
        job = self.jobs.get(job_id)
        if not job:
            return
        job.update({"status": "complete", "progress": 1.0, "result": result})
        self._log(job)
        self._emit("job.completed", job)

    def fail(self, job_id: str, error: str):
        job = self.jobs.get(job_id)
        if not job:
            return
        job.update({"status": "error", "result": {"error": error}, "progress": 1.0})
        self._log(job)
        self._emit("job.failed", job)

    def cancel(self, job_id: str):
        job = self.jobs.get(job_id)
        if not job:
            return
        job.update({"status": "cancelled"})
        self._log(job)
        self._emit("job.cancelled", job)

    # ------------------------------------------------------------
    # Retrieval + Polling
    # ------------------------------------------------------------
    def list(self) -> List[Dict[str, Any]]:
        return list(self.jobs.values())

    def get(self, job_id: str) -> Dict[str, Any]:
        return self.jobs.get(job_id, {})

    def poll(self) -> Dict[str, Any]:
        """Return job summary (for GUI polling or API /jobs/poll)."""
        all_jobs = list(self.jobs.values())
        active = [
            j for j in all_jobs if j["status"] not in ("complete", "error", "cancelled")
        ]
        return {
            "ok": True,
            "total": len(all_jobs),
            "active": len(active),
            "jobs": all_jobs[-25:],
        }

    # ------------------------------------------------------------
    # Logging + Rotation
    # ------------------------------------------------------------
    def _log(self, job: Dict[str, Any]):
        """Append job event to rotating log set."""
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(LOG_DIR, f"{timestamp}_{job['id']}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(job, f, indent=2)
        except Exception as e:
            print(f"[JobManager] Logging error: {e}")
        self._rotate_logs()

    def _rotate_logs(self):
        """Maintain only the newest MAX_LOG_FILES logs."""
        try:
            files = sorted(os.listdir(LOG_DIR))
            while len(files) > MAX_LOG_FILES:
                oldest = files.pop(0)
                os.remove(os.path.join(LOG_DIR, oldest))
        except Exception as e:
            print(f"[JobManager] Log rotation error: {e}")

    # ------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------
    def purge(self, status: str = "complete") -> int:
        """Remove completed or errored jobs from memory."""
        to_delete = [
            jid for jid, job in self.jobs.items() if job.get("status") == status
        ]
        for jid in to_delete:
            del self.jobs[jid]
        print(f"[JobManager] Purged {len(to_delete)} '{status}' jobs.")
        return len(to_delete)