# comfyvn/gui/__init__.py
# 🎨 ComfyVN GUI Package — v0.4-dev (Phase 3.3-G)
# Dynamic Menu System Integration + Modular GUI Architecture
# [🎨 GUI Code Production Chat]

"""
ComfyVN GUI Subsystem
=====================

Phase 3.3-G introduces:
 - Dynamic Top Bar Menu (auto-loadable /gui/menus/)
 - Modular menu registration via `TopBarMenu`
 - Preparation for shared status-bar framework (Phase 3.3-H)
 - Continued integration with Server Core 1.1.4
"""

__version__ = "0.4-dev"
__build__ = "Phase 3.3-G"
__author__ = "ComfyVN Architect Team"

# --------------------------------------------------------------------
# GUI Core Exports
# --------------------------------------------------------------------
from comfyvn.gui.main_window import MainWindow

# Core UI modules
from comfyvn.gui.settings_ui import SettingsUI
from comfyvn.gui.asset_browser import AssetBrowser
from comfyvn.gui.playground_ui import PlaygroundUI

# Components
from comfyvn.gui.components.topbar_menu import TopBarMenu
from comfyvn.gui.components.progress_overlay import ProgressOverlay
from comfyvn.gui.components.dialog_helpers import info, error
from comfyvn.gui.components.task_manager_dock import TaskManagerDock

# Optional modules
try:
    from comfyvn.gui.world_ui import WorldUI
    HAS_WORLD_UI = True
except ImportError:
    HAS_WORLD_UI = False

# --------------------------------------------------------------------
# Package Diagnostics
# --------------------------------------------------------------------
def describe() -> str:
    """Return a short description of GUI system components."""
    menus_path = "comfyvn.gui.menus"
    components = [
        "MainWindow",
        "SettingsUI",
        "AssetBrowser",
        "PlaygroundUI",
        "TaskManagerDock",
        "TopBarMenu",
        "ProgressOverlay",
        "DialogHelpers",
    ]
    desc = [
        f"ComfyVN GUI v{__version__} ({__build__})",
        f"Registered components ({len(components)}): {', '.join(components)}",
        f"Menu package: {menus_path}",
        f"WorldUI enabled: {HAS_WORLD_UI}",
    ]
    return "\n".join(desc)


if __name__ == "__main__":
    print(describe())
