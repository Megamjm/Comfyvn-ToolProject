from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/render_queue.py
from pathlib import Path
import json,uuid,time
QUEUE_FILE=Path("comfyvn/data/render_queue.json")

def enqueue(job:dict):
    job["id"]=str(uuid.uuid4());job["ts"]=time.time();jobs=list_queue();jobs.append(job)
    QUEUE_FILE.parent.mkdir(parents=True,exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(jobs,indent=2),encoding="utf-8");return job["id"]

def list_queue(): 
    if QUEUE_FILE.exists():
        try:return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:return []
    return []

def clear_completed(): 
    jobs=[j for j in list_queue() if not j.get('done')]
QUEUE_FILE.write_text(json.dumps(jobs, indent=2), encoding='utf-8')