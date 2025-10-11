# comfyvn/modules/job_manager.py
# ⚙️ Server Core v2.3 – Job Management + Event Publishing + Origin/Token (Synced)
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

import os, json, time, uuid, asyncio
from typing import Dict, Any, List, Optional
from .event_bus import EventBus

LOG_DIR = "./logs/jobs"
MAX_LOG_FILES = 10

class JobManager:
    """Tracks render/export tasks, supports persistence, rotation, and event publishing."""

    def __init__(self, event_bus: Optional[EventBus] = None):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.event_bus = event_bus

    # -------------------------------------------------
    # Event Emission
    # -------------------------------------------------
    async def _emit_async(self, evt_type: str, job: Dict[str, Any]):
        """Async broadcast helper for Job events."""
        if not self.event_bus:
            return
        await self.event_bus.broadcast({
            "type": evt_type,
            "job": job,
            "ts": time.time()
        })

    def _emit(self, evt_type: str, job: Dict[str, Any]):
        """Thread-safe wrapper for broadcasting events."""
        if not self.event_bus:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._emit_async(evt_type, job))
        except RuntimeError:
            asyncio.run(self._emit_async(evt_type, job))

    # -------------------------------------------------
    # Job Lifecycle
    # -------------------------------------------------
    def create(self, job_type: str, payload: Dict[str, Any],
               origin: str = "server", token: Optional[str] = None) -> Dict[str, Any]:
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
            "token": token or f"t-{uuid.uuid4().hex[:10]}"
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

    # -------------------------------------------------
    # Retrieval + Polling
    # -------------------------------------------------
    def list(self) -> List[Dict[str, Any]]:
        return list(self.jobs.values())

    def get(self, job_id: str) -> Dict[str, Any]:
        return self.jobs.get(job_id, {})

    def poll(self) -> Dict[str, Any]:
        """Return summary + active/incomplete jobs (for GUI polling)."""
        all_jobs = list(self.jobs.values())
        active = [j for j in all_jobs if j["status"] not in ("complete", "error", "cancelled")]
        return {
            "total": len(all_jobs),
            "active": len(active),
            "jobs": all_jobs[-25:]
        }

    # -------------------------------------------------
    # Logging + Rotation
    # -------------------------------------------------
    def _log(self, job: Dict[str, Any]):
        """Append job event to rolling log."""
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(LOG_DIR, f"{timestamp}_{job['id']}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(job, f, indent=2)
        except Exception as e:
            print(f"[JobManager] Logging error: {e}")
        self._rotate_logs()

    def _rotate_logs(self):
        """Delete oldest logs beyond MAX_LOG_FILES."""
        try:
            files = sorted(os.listdir(LOG_DIR))
            while len(files) > MAX_LOG_FILES:
                oldest = files.pop(0)
                os.remove(os.path.join(LOG_DIR, oldest))
        except Exception as e:
            print(f"[JobManager] Log rotation error: {e}")

    # -------------------------------------------------
    # Optional Maintenance
    # -------------------------------------------------
    def purge(self, status: str = "complete") -> int:
        """
        Remove completed or errored jobs from memory to reduce RAM usage.
        Returns the number of removed jobs.
        """
        to_delete = [jid for jid, job in self.jobs.items() if job.get("status") == status]
        for jid in to_delete:
            del self.jobs[jid]
        print(f"[JobManager] Purged {len(to_delete)} '{status}' jobs.")
        return len(to_delete)
