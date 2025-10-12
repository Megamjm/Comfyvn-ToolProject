# comfyvn/gui/components/topbar_menu.py
# 🎨 Dynamic Top Bar Menu Loader — Phase 3.3-G
# [🎨 GUI Code Production Chat]

import importlib
import pkgutil
import logging
from PySide6.QtWidgets import QMenuBar

log = logging.getLogger("ComfyVN.TopBarMenu")


class TopBarMenu(QMenuBar):
    """Dynamic menu bar that auto-loads menu modules from /gui/menus."""

    def __init__(self, parent=None, menu_pkg="comfyvn.gui.menus"):
        super().__init__(parent)
        self.menu_pkg = menu_pkg
        self.loaded_menus = []
        self.load_menus()

    # ------------------------------------------------------------------
    def load_menus(self):
        """Dynamically discover and register all menus."""
        try:
            pkg = importlib.import_module(self.menu_pkg)
        except ModuleNotFoundError:
            log.warning("No menu package found: %s", self.menu_pkg)
            return

        for mod_info in pkgutil.iter_modules(pkg.__path__):
            try:
                module = importlib.import_module(f"{self.menu_pkg}.{mod_info.name}")
                if hasattr(module, "register_menu"):
                    m = module.register_menu(self)
                    self.loaded_menus.append(m)
                    log.info("Loaded menu: %s", mod_info.name)
            except Exception as e:
                log.error("Failed to load menu %s: %s", mod_info.name, e)