import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
# comfyvn/server/core/router_loader.py
# 🌐 Router Loader — discovers & registers all API modules

from comfyvn.server.core.import_utils import safe_import


def load_routers(app):
    """
    Load all API routers dynamically with fault-tolerance.
    Returns two lists: loaded, failed.
    """
    router_paths = [
        "comfyvn.server.modules.playground_api",
        "comfyvn.server.modules.roleplay.roleplay_api",
        "comfyvn.server.modules.player_state_api",
        "comfyvn.server.modules.snapshot_api",  # ✅ added snapshot system
        "comfyvn.server.modules.jobs_api",  # optional
        "comfyvn.server.modules.settings_api",  # optional
        "comfyvn.server.modules.system_api",  # optional
        "comfyvn.server.modules.events_api",  # optional
        "comfyvn.server.modules.search_api",  # optional
    ]
    loaded, failed = [], []

    for path in router_paths:
        mod = safe_import(path)
        if mod and hasattr(mod, "router"):
            app.include_router(mod.router)
            loaded.append(path)
        else:
            failed.append(path)

    return loaded, failed
