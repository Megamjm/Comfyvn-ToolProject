# comfyvn/modules/task_allocator.py
# 🚚 Task Allocator — v0.4-dev (Phase 3.4-A)
# Thin client for job reallocation (CPU <-> GPU)
# [🎨 GUI Code Production Chat]

import requests


class TaskAllocator:
    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip("/")

    def reallocate(self, job_id: str, target: str) -> bool:
        """
        Ask Server Core to reassign job to target device.
        target ∈ {"cpu", "gpu"} (future: "gpu:1", "gpu:0", "ram")
        """
        url = f"{self.server_url}/jobs/reallocate"
        r = requests.post(url, json={"job_id": job_id, "target": target}, timeout=8)
        return r.status_code == 200