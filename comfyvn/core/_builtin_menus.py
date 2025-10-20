from PySide6.QtGui import QAction

# ComfyVN built-in menu provider (rendered via dynamic registry)
from .menu_runtime_bridge import wire_core_menus

def menus(window, registry):
    wire_core_menus(window, registry)