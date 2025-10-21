import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
# comfyvn/server/core/import_utils.py
# ⚙️ Safe Import Utility

import importlib
import traceback


def safe_import(module_path: str):
    """Safely import a module and log issues instead of raising ImportError."""
    try:
        mod = importlib.import_module(module_path)
        print(f"[Import] ✅ Loaded {module_path}")
        return mod
    except Exception as e:
        print(f"[Import][WARN] Could not import {module_path}: {e}")
        print(f" ↳ {traceback.format_exc(limit=1).strip()}")
        return None
