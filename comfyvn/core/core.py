from PySide6.QtGui import QAction

"""Auto-generated module exports."""

__all__ = [
    "bridge_comfyui",
    "event_bus",
    "job_manager",
    "mode_manager",
    "scene_compositor",
    "scene_preprocessor",
    "settings_manager",
    "st_sync_manager",
    "system_monitor",
    "workflow_bridge",
    "world_loader",
]


# ---- Back-compat hook registry (added by Main window update chat) ----
class HookRegistry:
    def __init__(self):
        self._handlers = {}  # name -> list[callable]

    def register(self, name: str, fn):
        self._handlers.setdefault(name, []).append(fn)
        return fn

    def emit(self, name: str, *args, **kwargs):
        for fn in self._handlers.get(name, []):
            try:
                fn(*args, **kwargs)
            except Exception:
                # swallow to avoid crashing UI; log here if you have a logger
                pass

    def listeners(self, name: str):
        return list(self._handlers.get(name, []))

    def clear(self, name: str | None = None):
        if name is None:
            self._handlers.clear()
        else:
            self._handlers.pop(name, None)


hooks = HookRegistry()


def on(name: str):
    """Decorator to register a hook handler: @on('menu.populate')"""

    def _wrap(fn):
        hooks.register(name, fn)
        return fn

    return _wrap


# ----------------------------------------------------------------------
