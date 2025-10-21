import json
import logging

# comfyvn/core/job_offloader.py
# [ComfyVN Architect | Phase 0.94 | Unified Job Offload Bridge]
import requests
from PySide6.QtGui import QAction

from comfyvn.config.baseurl_authority import default_base_url

log = logging.getLogger(__name__)


def ensure_server_alive(base: str | None = None):
    base = (base or default_base_url()).rstrip("/")
    try:
        r = requests.get(f"{base}/health", timeout=2)
        if r.status_code == 200:
            return True
    except Exception:
        pass
    return False


def offload_job_local(job: dict, base: str | None = None):
    base_url = (base or default_base_url()).rstrip("/")
    if not ensure_server_alive(base_url):
        return {"ok": False, "error": "Server offline"}
    try:
        r = requests.post(f"{base_url}/jobs/enqueue", json=job, timeout=10)
        return r.json() if r.status_code < 400 else {"ok": False, "error": r.text}
    except Exception as e:
        log.error(f"Local job offload failed: {e}")
        return {"ok": False, "error": str(e)}


def offload_job_remote(job: dict, endpoint: str):
    try:
        r = requests.post(f"{endpoint}/jobs/enqueue", json=job, timeout=10)
        return r.json() if r.status_code < 400 else {"ok": False, "error": r.text}
    except Exception as e:
        log.error(f"Remote job offload failed: {e}")
        return {"ok": False, "error": str(e)}
