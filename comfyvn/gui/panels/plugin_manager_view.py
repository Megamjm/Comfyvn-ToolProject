import json
# comfyvn/gui/panels/plugin_manager_view.py
# [COMFYVN Architect | v1.2 | this chat]
import os

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

from comfyvn.core.extension_loader import (discover_extensions,
                                           reload_extensions, set_enabled)
from comfyvn.core.notifier import notifier


class PluginManagerView(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plugin Manager")
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        hb = QHBoxLayout()
        lay.addLayout(hb)
        self.btn_enable = QPushButton("Enable")
        self.btn_disable = QPushButton("Disable")
        self.btn_reload = QPushButton("Reload All")
        hb.addWidget(self.btn_enable)
        hb.addWidget(self.btn_disable)
        hb.addStretch(1)
        hb.addWidget(self.btn_reload)
        self.btn_enable.clicked.connect(lambda: self._toggle(True))
        self.btn_disable.clicked.connect(lambda: self._toggle(False))
        self.btn_reload.clicked.connect(self._reload)
        self.refresh()

    def _state_file(self):
        return os.path.join(os.getcwd(), "extensions", "state.json")

    def refresh(self):
        self.list.clear()
        base = os.path.join(os.getcwd(), "extensions")
        st = {}
        try:
            with open(self._state_file(), "r", encoding="utf-8") as f:
                st = json.load(f)
        except Exception:
            st = {}
        if os.path.exists(base):
            for root, dirs, files in os.walk(base):
                if "plugin_manifest.json" in files:
                    path = os.path.join(root, "plugin_manifest.json")
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            m = json.load(f)
                        pid = m.get("id") or os.path.basename(root)
                        enabled = st.get(pid, True)
                        self.list.addItem(f"{'🟢' if enabled else '⚪'}  {pid}")
                    except Exception:
                        pass

    def current_id(self):
        it = self.list.currentItem()
        if not it:
            return None
        text = it.text()
        return text.split("  ", 1)[1]

    def _toggle(self, enabled: bool):
        pid = self.current_id()
        if not pid:
            QMessageBox.information(self, "Plugins", "Select a plugin first")
            return
        set_enabled(pid, enabled)
        notifier.toast("info", f"{pid} {'enabled' if enabled else 'disabled'}")
        self.refresh()

    def _reload(self):
        discover_extensions()
        reload_extensions()
        notifier.toast("info", "Extensions reloaded")
        self.refresh()
