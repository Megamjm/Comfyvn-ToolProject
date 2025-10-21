from __future__ import annotations

# comfyvn/core/space_controller.py
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from comfyvn.gui.panels.gpu_manager_panel import GPUManagerPanel
from comfyvn.gui.panels.importer_panel import ImporterPanel
from comfyvn.gui.panels.render_dashboard_panel import RenderDashboardPanel
from comfyvn.gui.panels.system_monitor_panel import SystemMonitorPanel
# Panels used as central views
from comfyvn.gui.panels.vn_viewport_panel import VNViewportPanel


class SpaceController:
    """
    Manages the 'central space' (main viewport) and attaches common side panels.
    Spaces: 'VN', 'Render', 'Import', 'GPU', 'System'
    """

    def __init__(self, main_window, dockman):
        self.w = main_window
        self.dockman = dockman
        self._current = None
        self._central = None

    def _set_central(self, widget, title: str):
        # Remove previous central widget if present
        if self._central is not None:
            try:
                self._central.setParent(None)
            except Exception:
                pass
        self._central = widget
        # Dock as a large center panel
        self.dockman.dock(widget, title, Qt.LeftDockWidgetArea)

    def activate(self, name: str):
        name = (name or "").strip().lower()
        if name in ("vn", "vn studio"):
            self._activate_vn()
        elif name in ("render", "render studio"):
            self._activate_render()
        elif name in ("import", "import studio"):
            self._activate_import()
        elif name in ("gpu", "gpu studio"):
            self._activate_gpu()
        elif name in ("system", "system studio"):
            self._activate_system()
        else:
            raise ValueError(f"Unknown space: {name}")

    # ---- Space presets ----
    def _activate_vn(self):
        center = VNViewportPanel()
        self._set_central(center, "VN Viewport")
        # Common side panels
        try:
            self.w.open_assets()
            self.w.open_timeline()
        except Exception:
            pass

    def _activate_render(self):
        center = RenderDashboardPanel()
        self._set_central(center, "Render Dashboard")
        try:
            self.w.open_render()
            self.w.open_gpu_local()
            self.w.open_gpu_remote()
        except Exception:
            pass

    def _activate_import(self):
        center = ImporterPanel()
        self._set_central(center, "Importer")
        try:
            # advisory panel can be added later; logs hub already present
            pass
        except Exception:
            pass

    def _activate_gpu(self):
        center = GPUManagerPanel()
        self._set_central(center, "GPU Manager")
        try:
            self.w.open_gpu_local()
            self.w.open_gpu_remote()
        except Exception:
            pass

    def _activate_system(self):
        center = SystemMonitorPanel()
        self._set_central(center, "System Monitor")
        try:
            # keep logs hub in bottom
            pass
        except Exception:
            pass
