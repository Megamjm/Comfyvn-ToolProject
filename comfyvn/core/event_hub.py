from PySide6.QtGui import QAction
# comfyvn/core/event_hub.py
# Compat shim # [Main window update chat]
try:
    from .event_hub_v05 import *  # re-export
except Exception as _e:
    # Minimal fallback to avoid hard import errors; adjust as needed
    pass