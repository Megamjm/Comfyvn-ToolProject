from PySide6.QtGui import QAction

# comfyvn/core/extension_loader.py
# [COMFYVN Architect | v2.0 | this chat]
from comfyvn.core.extension_runtime import runtime
from comfyvn.core.log_bus import log


def discover_extensions():
    # kept for backward import compatibility — runtime handles discovery
    return runtime.discover()


def reload_extensions(ctx=None):
    try:
        runtime.unload_all(ctx)
        runtime.load_all(ctx)
        log.info("[ext] reload complete")
    except Exception as e:
        log.error(f"[ext] reload failed: {e}")


def load_extensions(ctx=None):
    try:
        runtime.load_all(ctx)
    except Exception as e:
        log.error(f"[ext] load failed: {e}")


# --- Phase 0.91 augment: GUI helpers (non-destructive) ---
try:
    from comfyvn.core.extension_gui_bridge import bridge

    def get_extensions_info():
        return bridge.info()

    def list_active_tasks():
        return bridge.info().get("tasks", [])

    def mark_restart_needed():
        return bridge.mark_restart_needed()

except Exception:
    # keep backwards-compat if GUI bridge not present
    def get_extensions_info():
        return {"extensions": [], "tasks": [], "restart_needed": False}

    def list_active_tasks():
        return []

    def mark_restart_needed():
        return None


# --- Phase 0.91 augment: GUI helpers (non-destructive) ---
try:
    from comfyvn.core.extension_gui_bridge import bridge

    def get_extensions_info():
        return bridge.info()

    def list_active_tasks():
        return bridge.info().get("tasks", [])

    def mark_restart_needed():
        return bridge.mark_restart_needed()

except Exception:
    # keep backwards-compat if GUI bridge not present
    def get_extensions_info():
        return {"extensions": [], "tasks": [], "restart_needed": False}

    def list_active_tasks():
        return []

    def mark_restart_needed():
        return None
