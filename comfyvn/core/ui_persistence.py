from PySide6.QtGui import QAction
# comfyvn/core/ui_persistence.py
# [COMFYVN Architect | v0.8.3s2 | this chat]
import json
from pathlib import Path
from comfyvn.core.log_bus import log
from comfyvn.config.runtime_paths import settings_file
CONF = settings_file("features.json")
def load_state():
    if CONF.exists():
        try: return json.loads(CONF.read_text(encoding="utf-8"))
        except Exception as e: log.error(f"load_state: {e}")
    return {"enabled": {}, "layout": {}, "last_space": "Default"}
def save_state(state: dict):
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text(json.dumps(state, indent=2), encoding="utf-8")
    log.debug("GUI state saved")
