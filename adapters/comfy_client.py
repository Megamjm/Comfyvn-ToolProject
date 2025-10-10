from __future__ import annotations
import os, json, time, requests
from typing import Optional, Dict, Any

COMFY_HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")

def submit_workflow(workflow:dict) -> dict:
    r = requests.post(f"{COMFY_HOST}/prompt", json=workflow, timeout=10)
    try:
        return r.json()
    except Exception:
        return {"status_code": r.status_code, "text": r.text}

def get_history(prompt_id:str) -> Optional[dict]:
    r = requests.get(f"{COMFY_HOST}/history/{prompt_id}", timeout=10)
    if r.status_code==200:
        return r.json()
    return None
