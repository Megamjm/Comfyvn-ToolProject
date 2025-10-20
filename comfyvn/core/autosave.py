from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/autosave.py
import json,time
from pathlib import Path
STATE=Path("comfyvn/data/workspace_state.json")

def save_state(layout:str="default"):
    STATE.write_text(json.dumps({"layout":layout,"ts":time.time()},indent=2),encoding="utf-8")

def load_state(): 
    if STATE.exists():
        try:return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:pass
    return {"layout":"default"}