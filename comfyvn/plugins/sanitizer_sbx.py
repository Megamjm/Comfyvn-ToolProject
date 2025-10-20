from __future__ import annotations
from PySide6.QtGui import QAction
from comfyvn.ext.plugins import Plugin

def handle(payload: dict, job_id: str | None):
    text = str((payload or {}).get("text",""))
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?-_'\"\n")
    clean = "".join(ch for ch in text if ch in allowed)
    # Try to open a disallowed path to prove sandbox works: this should be blocked
    try:
        open("/etc/shadow","w").write("x")  # should raise
        return {"ok": False, "error": "sandbox failed to block write"}
    except Exception:
        pass
    return {"ok": True, "clean": clean}

plugin = Plugin(
    name="sanitizer_sbx",
    jobs={"sanitize": handle},
    meta={
        "builtin": True,
        "desc": "Cleans text and demonstrates sandbox rules",
        "sandbox": {
            "entry": "handle",
            "module": "comfyvn.plugins.sanitizer_sbx",
            "cpu_secs": 2,
            "wall_secs": 5,
            "mem_mb": 128,
            "network": False,
            "fs_roots": ["./exports","./data/assets"],
            "env_allow": ["PATH"]
        }
    }
)