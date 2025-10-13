# comfyvn/gui/settings_ui.py
# 🎛 Settings Panel with Drawers — Phase 3.3 Integration + Server Control + Auto-Start
# [COMFYVN Architect | Integration Alignment + Embedded Control]

import os, requests, json
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QMessageBox,
    QHBoxLayout,
    QFormLayout,
    QScrollArea,
    QCheckBox,  # ✅ added QCheckBox
)
from PySide6.QtCore import Qt, QTimer

from comfyvn.gui.components.drawer_widget import DrawerWidget
from comfyvn.gui.snapshots.snapshot_defaults_drawer import SnapshotDefaultsDrawer
from comfyvn.gui.server_bridge import ServerBridge
from comfyvn.gui.components.server_manager import ServerManager


class SettingsUI(QWidget):
    """Unified settings panel with save/reload actions, server control, and live API tests."""

    def __init__(self, parent=None, api_base="http://127.0.0.1:8001"):
        super().__init__(parent)
        self.api_base = api_base.rstrip("/")
        self.server = ServerBridge(base_url=self.api_base)
        self.server_mgr = ServerManager(port=8001)

        # ---------------- State persistence ----------------
        self._state_path = os.path.join("comfyvn", "data", "ui_state.json")
        self._ui_state = self._load_ui_state()

        # ---------------- Layout ----------------
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        page = QWidget()
        scroll.setWidget(page)
        layout = QVBoxLayout(page)
        self.drawer = DrawerWidget(page)
        layout.addWidget(self.drawer)

        # ---------------- Sections ----------------
        self._init_paths()
        self._init_asset_folders()
        self._init_integrations()
        self._init_server_control()
        self._init_snapshots()

        layout.addStretch()
        if self.drawer.sections:
            self.drawer.sections[0]["header"].setChecked(True)

        # ---------------- Status & Auto-start ----------------
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_server_status)
        self._status_timer.start(5000)  # ✅ safer polling interval
        self._update_server_status()

        # Auto-start if user enabled
        QTimer.singleShot(3000, self._auto_start_check)

    # ------------------------------------------------------------
    # UI State Persistence
    # ------------------------------------------------------------
    def _load_ui_state(self):
        """Load persisted UI state from disk."""
        if not os.path.exists(self._state_path):
            return {}
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"[SettingsUI] Loaded UI state: {data}")
                return data
        except Exception as e:
            print(f"[SettingsUI] Failed to load UI state: {e}")
            return {}

    def _save_ui_state(self):
        """Save UI state to disk."""
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(self._ui_state, f, indent=2)
            print("[SettingsUI] Saved UI state.")
        except Exception as e:
            print(f"[SettingsUI] Failed to save UI state: {e}")

    # ------------------------------------------------------------
    # Auto-start logic
    # ------------------------------------------------------------
    def _auto_start_check(self):
        """If user enabled auto-start, start server automatically."""
        if hasattr(self, "chk_autostart") and self.chk_autostart.isChecked():
            if not self.server_mgr.is_running():
                try:
                    msg = self.server_mgr.start("embedded")
                    print(f"[AutoStart] {msg}")
                except Exception as e:
                    print(f"[AutoStart] Failed: {e}")
            self._update_server_status()

    # ------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------
    def _defaults(self):
        cwd = os.path.abspath(os.getcwd())
        return {
            "project_root": cwd,
            "asset_folders": {
                "backgrounds": os.path.join(cwd, "assets", "backgrounds"),
                "characters": os.path.join(cwd, "assets", "characters"),
                "props": os.path.join(cwd, "assets", "props"),
                "ui": os.path.join(cwd, "assets", "ui"),
            },
            "integrations": {
                "api_base": self._ui_state.get("api_base", self.api_base),
                "comfyui_url": self._ui_state.get(
                    "comfyui_url", "http://127.0.0.1:8188"
                ),
                "sillytavern_url": self._ui_state.get(
                    "sillytavern_url", "http://127.0.0.1:8000"
                ),
            },
        }

    # ------------------------------------------------------------
    # Project Paths
    # ------------------------------------------------------------
    def _init_paths(self):
        d = self._defaults()
        form = QFormLayout()
        self.edit_project = QLineEdit(d["project_root"])
        form.addRow("Project Directory Path", self.edit_project)

        box = QWidget()
        v = QVBoxLayout(box)
        v.addLayout(form)
        btn = QPushButton("Save Paths")
        btn.clicked.connect(self._save_paths)
        v.addWidget(btn, alignment=Qt.AlignLeft)
        self.drawer.add_section("Project Paths", box)

    # ------------------------------------------------------------
    # Asset Folders
    # ------------------------------------------------------------
    def _init_asset_folders(self):
        d = self._defaults()["asset_folders"]
        form = QFormLayout()
        self.bg_path = QLineEdit(d["backgrounds"])
        self.char_path = QLineEdit(d["characters"])
        self.props_path = QLineEdit(d["props"])
        self.ui_path = QLineEdit(d["ui"])

        form.addRow("Backgrounds Folder", self.bg_path)
        form.addRow("Characters Folder", self.char_path)
        form.addRow("Props Folder", self.props_path)
        form.addRow("UI Folder", self.ui_path)

        box = QWidget()
        v = QVBoxLayout(box)
        v.addLayout(form)
        btn = QPushButton("Save Asset Folders")
        btn.clicked.connect(self._save_asset_folders)
        v.addWidget(btn, alignment=Qt.AlignLeft)
        self.drawer.add_section("Asset Folders", box)

    # ------------------------------------------------------------
    # Integrations
    # ------------------------------------------------------------
    def _init_integrations(self):
        d = self._defaults()["integrations"]
        form = QFormLayout()
        self.api_base_edit = QLineEdit(d["api_base"])
        self.comfyui_edit = QLineEdit(d["comfyui_url"])
        self.st_edit = QLineEdit(d["sillytavern_url"])

        form.addRow("ComfyVN API Base", self.api_base_edit)
        form.addRow("ComfyUI URL", self.comfyui_edit)
        form.addRow("SillyTavern URL", self.st_edit)

        buttons = QWidget()
        row = QHBoxLayout(buttons)
        btn_save = QPushButton("Save Integrations")
        btn_test_api = QPushButton("Test ComfyVN")
        btn_reload = QPushButton("Reload Settings")
        row.addWidget(btn_save)
        row.addWidget(btn_test_api)
        row.addWidget(btn_reload)
        row.addStretch()

        vbox = QVBoxLayout()
        vbox.addLayout(form)
        vbox.addWidget(buttons)
        box = QWidget()
        box.setLayout(vbox)
        self.drawer.add_section("Integrations", box)

        btn_save.clicked.connect(self._save_integrations)
        btn_test_api.clicked.connect(
            lambda: self._test_url(self.api_base_edit.text().strip(), "/status")
        )
        btn_reload.clicked.connect(self._reload_settings)

    # ------------------------------------------------------------
    # Server Control
    # ------------------------------------------------------------
    def _init_server_control(self):
        box = QWidget()
        v = QVBoxLayout(box)

        self.label_status = QLabel("🔴 Server Offline")
        self.label_status.setAlignment(Qt.AlignCenter)
        self.label_status.setStyleSheet("font-weight: bold; font-size: 10pt;")
        v.addWidget(self.label_status)

        btn_start = QPushButton("▶️ Start Server")
        btn_restart = QPushButton("🔁 Restart Server")
        btn_stop = QPushButton("⛔ Force Stop Server")
        btn_kill = QPushButton("💀 Kill All Server Processes")

        self.chk_autostart = QCheckBox("☑️ Auto-start Server on Launch")
        self.chk_autostart.setCheckable(True)
        auto_on = self._ui_state.get("autostart_enabled", True)
        self.chk_autostart.setChecked(auto_on)
        self.chk_autostart.setToolTip(
            "If enabled, ComfyVN will start its internal server when GUI launches."
        )
        self.chk_autostart.toggled.connect(self._on_autostart_toggle)
        v.addWidget(self.chk_autostart)

        for b in [btn_start, btn_restart, btn_stop, btn_kill]:
            b.setMinimumHeight(30)
            v.addWidget(b)

        btn_start.clicked.connect(lambda: self._server_action("start"))
        btn_restart.clicked.connect(lambda: self._server_action("restart"))
        btn_stop.clicked.connect(lambda: self._server_action("stop"))
        btn_kill.clicked.connect(lambda: self._server_action("kill"))

        self.drawer.add_section("⚙️ Server Control", box)

    def _on_autostart_toggle(self, state: bool):
        """Persist auto-start checkbox change."""
        self._ui_state["autostart_enabled"] = bool(state)
        QTimer.singleShot(500, self._save_ui_state)

    # ------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------
    def _init_snapshots(self):
        snap = SnapshotDefaultsDrawer(self, api_base=self.api_base)
        self.drawer.add_section("Snapshots / Defaults", snap)

    # ------------------------------------------------------------
    # Save Handlers
    # ------------------------------------------------------------
    def _save_paths(self):
        payload = {"project_root": self.edit_project.text().strip()}
        res = self.server.save_settings(payload, lambda r: None) or {}
        if isinstance(res, dict) and not res.get("error"):
            QMessageBox.information(self, "Paths", "Saved.")
        else:
            QMessageBox.warning(self, "Paths", f"Save may have failed: {res}")

    def _save_asset_folders(self):
        payload = {
            "asset_folders": {
                "backgrounds": self.bg_path.text().strip(),
                "characters": self.char_path.text().strip(),
                "props": self.props_path.text().strip(),
                "ui": self.ui_path.text().strip(),
            }
        }
        res = self.server.save_settings(payload, lambda r: None) or {}
        if isinstance(res, dict) and not res.get("error"):
            QMessageBox.information(self, "Asset Folders", "Saved.")
        else:
            QMessageBox.warning(self, "Asset Folders", f"Save may have failed: {res}")

    def _save_integrations(self):
        base = self.api_base_edit.text().strip()
        self.server.set_host(base)
        payload = {
            "integrations": {
                "api_base": base,
                "comfyui_url": self.comfyui_edit.text().strip(),
                "sillytavern_url": self.st_edit.text().strip(),
            }
        }
        res = self.server.save_settings(payload, lambda r: None) or {}
        self._ui_state.update(payload["integrations"])
        self._save_ui_state()
        if isinstance(res, dict) and not res.get("error"):
            QMessageBox.information(self, "Integrations", "Saved.")
        else:
            QMessageBox.warning(self, "Integrations", f"Save may have failed: {res}")

    # ------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------
    def _reload_settings(self):
        btn = self.sender()
        if btn:
            btn.setEnabled(False)
            btn.setText("Reloading...")

        def on_result(result: dict):
            if btn:
                btn.setEnabled(True)
                btn.setText("Reload Settings")
            if isinstance(result, dict) and result.get("error"):
                QMessageBox.critical(self, "Reload", f"Failed: {result['error']}")
            else:
                QMessageBox.information(
                    self, "Reload", "Settings reloaded successfully."
                )

        self.server.reload_settings(on_result)

    # ------------------------------------------------------------
    # Server control actions
    # ------------------------------------------------------------
    def _server_action(self, action: str):
        """Handle start/stop/restart/kill commands safely."""
        try:
            if action == "start":
                msg = self.server_mgr.start("embedded")
            elif action == "restart":
                msg = self.server_mgr.restart()
            elif action == "stop":
                msg = self.server_mgr.stop(force=False)
            elif action == "kill":
                msg = self.server_mgr.force_kill_all()
            else:
                msg = "Unknown action"
        except Exception as e:
            msg = f"Error: {e}"

        QMessageBox.information(self, "Server Control", msg)
        self._update_server_status()

    # ------------------------------------------------------------
    # Server Status
    # ------------------------------------------------------------
    def _update_server_status(self):
        try:
            running = self.server_mgr.is_running() or self.server_mgr.ping()
        except Exception:
            running = False

        if running:
            self.label_status.setText(
                f"🟢 Server Running on {self.server_mgr.host}:{self.server_mgr.port}"
            )
            self.label_status.setStyleSheet("color: #2a2; font-weight: bold;")
        else:
            self.label_status.setText("🔴 Server Offline")
            self.label_status.setStyleSheet("color: #c22; font-weight: bold;")

    # ------------------------------------------------------------
    # Test helper
    # ------------------------------------------------------------
    def _test_url(self, base: str, path: str):
        base = base.rstrip("/")
        try:
            r = requests.get(f"{base}{path}", timeout=8)
            if r.status_code < 400:
                QMessageBox.information(self, "Test", f"OK • {base}{path}")
            else:
                QMessageBox.critical(self, "Test", f"{r.status_code} • {base}{path}")
        except Exception as e:
            QMessageBox.critical(self, "Test", f"{base}{path}\n{e}")
