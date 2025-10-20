from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/gui/windows/extension_manager_window.py
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QListWidget, QListWidgetItem, QMessageBox, QWidget)
from PySide6.QtCore import Qt, QTimer

from comfyvn.core.extension_gui_bridge import bridge

class ExtensionManagerWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extension Manager")
        self.setModal(False)
        self.resize(600, 420)

        self.list = QListWidget()
        self.lbl_status = QLabel("Status: ready")
        self.btn_reload = QPushButton("Reload All")
        self.btn_restart = QPushButton("Save & Restart Studio")
        self.btn_close = QPushButton("Close")

        top = QVBoxLayout(self)
        top.addWidget(self.list)

        row = QHBoxLayout()
        row.addWidget(self.lbl_status)
        row.addStretch(1)
        row.addWidget(self.btn_reload)
        row.addWidget(self.btn_restart)
        row.addWidget(self.btn_close)
        top.addLayout(row)

        self.btn_close.clicked.connect(self.close)
        self.btn_reload.clicked.connect(self._reload)
        self.btn_restart.clicked.connect(self._restart)

        self._refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(3000)

    def _refresh(self):
        self.list.clear()
        info = bridge.info()
        for e in info.get("extensions", []):
            item = QListWidgetItem(f"{e['name']}  v{e.get('version','?')}  "
                                   f"{'ENABLED' if e['enabled'] else 'DISABLED'}")
            if e.get("reload_required"):
                item.setText(item.text() + "  [RESTART REQUIRED]")
            self.list.addItem(item)
        tasks = info.get("tasks", [])
        if tasks:
            self.lbl_status.setText(f"Status: {len(tasks)} active task(s)")
        else:
            self.lbl_status.setText("Status: server is on standby")

    def _reload(self):
        try:
            bridge.reload_all({})
            self._refresh()
            QMessageBox.information(self, "Extensions", "Reload complete.")
        except Exception as e:
            QMessageBox.critical(self, "Extensions", str(e))

    def _restart(self):
        # Persist state, let outer app decide how to restart
        try:
            bridge.save_state()
            QMessageBox.information(self, "Restart", "State saved. Please restart Studio.")
            self.close()
        except Exception as e:
            QMessageBox.critical(self, "Restart", str(e))


        # [Phase 2.90] runtime wiring (safe if already present)
        try:
            from comfyvn.core import extension_runtime as _ext_rt
            _ext_rt.load_all()
            self._runtime = _ext_rt
        except Exception:
            self._runtime = None

    # ------------------------------------------------------------------
    # Optional Enable/Disable controls (future enhancement placeholder)
    # ------------------------------------------------------------------
    def toggle_extension_state(self, ext_id: str):
        """Enable or disable an extension via runtime registry."""
        try:
            if not getattr(self, "_runtime", None):
                return
            reg = self._runtime.list_registry()
            if reg.get(ext_id, {}).get("enabled"):
                self._runtime.disable(ext_id)
            else:
                self._runtime.enable(ext_id)
            self._refresh()
        except Exception as e:
            QMessageBox.critical(self, "Extensions", str(e))