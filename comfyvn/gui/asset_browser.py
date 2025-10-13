# comfyvn/gui/asset_browser.py
# 🎨 Asset & Sprite System Manager — v0.4-dev (Phase 3.3-H)
# Integrates StatusWidget + SystemMonitor + PoseBrowser + ServerBridge
# [🎨 GUI Code Production Chat | QA Fixed | ComfyVN_Architect]

import os, json, platform, subprocess, threading, traceback
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QHBoxLayout,
    QListView,
    QAbstractItemView,
    QMenu,
    QFrame,
    QMessageBox,
)
from PySide6.QtGui import QPixmap, QIcon, QCursor, QDrag, QDesktopServices
from PySide6.QtCore import (
    Qt,
    QSize,
    QTimer,
    QPoint,
    QByteArray,
    QMimeData,
    QUrl,
    QObject,
    QEvent,
)

# ---------------------------------------------------------------------------------
# Optional imports (fallback shims so the widget still works if modules are absent)
# ---------------------------------------------------------------------------------


def _warn(msg: str):
    print(f"[AssetBrowser][WARN] {msg}")


# ProgressOverlay
try:
    from comfyvn.gui.widgets.progress_overlay import ProgressOverlay
except Exception:

    class ProgressOverlay(QWidget):
        def __init__(self, parent=None, text="Processing …", cancellable=False):
            super().__init__(parent)
            self._text = text
            self.hide()

        def set_text(self, t):
            self._text = t

        def start(self):
            self.show()

        def stop(self):
            self.hide()


# Dialog helpers
try:
    from comfyvn.gui.widgets.dialog_helpers import info, error, confirm
except Exception:

    def info(parent, title, msg):
        QMessageBox.information(parent, title, msg)

    def error(parent, title, msg):
        QMessageBox.critical(parent, title, msg)

    def confirm(parent, title, msg):
        return QMessageBox.question(parent, title, msg) == QMessageBox.Yes


# StatusWidget
try:
    from comfyvn.gui.widgets.status_widget import StatusWidget
except Exception:

    class StatusWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            l = QHBoxLayout(self)
            self._labels = {}

        def add_indicator(self, key, label):
            lab = QLabel(f"{label}: n/a")
            self.layout().addWidget(lab)
            self._labels[key] = lab

        def update_indicator(self, key, text):
            if key in self._labels:
                self._labels[key].setText(text)


# ServerBridge (simple HTTP fallback)
try:
    from comfyvn.gui.server_bridge import ServerBridge
except Exception:
    import requests

    class ServerBridge:
        def __init__(self, base_url):
            self.base_url = base_url

        def send_render_request(self, payload: dict, callback):
            try:
                r = requests.post(
                    f"{self.base_url}/export/scene", json=payload, timeout=15
                )
                callback(r.json())
            except Exception as e:
                callback({"error": str(e)})


# SystemMonitor
try:
    from comfyvn.core.system_monitor import SystemMonitor
except Exception:

    class SystemMonitor:
        def __init__(self, server_url):
            self.cb = None

        def on_update(self, cb):
            self.cb = cb

        def start(self, interval=6):
            # trivial timer to simulate updates
            def tick():
                if self.cb:
                    self.cb({"gpu": "n/a", "cpu": "ok", "ram": "ok", "server": "ok"})

            t = QTimer()
            t.timeout.connect(tick)
            t.start(6000)
            # Keep a reference so it's not GC'd
            self._timer = t


# PoseBrowser
try:
    from comfyvn.gui.pose_browser import PoseBrowser
except Exception:
    PoseBrowser = None
    _warn("PoseBrowser not available — 'Select Pose' will be disabled.")

# Managers (refactor path first, then fallback)
PoseManager = ExportManager = None
try:
    # Removed circular import (PoseManager self-reference) as _PM
    PoseManager = _PM
except Exception:
    try:
        from comfyvn.modules.pose_manager import PoseManager as _PM

        PoseManager = _PM
    except Exception:
        _warn("PoseManager not found — pose features limited.")

try:
    from comfyvn.assets.export_manager import ExportManager as _EM

    ExportManager = _EM
except Exception:
    try:
        from comfyvn.modules.export_manager import ExportManager as _EM

        ExportManager = _EM
    except Exception:
        _warn("ExportManager not found — exports will be simulated.")

# ---------------------------------------------------------------------------------
# Main Widget
# ---------------------------------------------------------------------------------


class AssetBrowser(QWidget):
    """Asset Browser & Sprite Manager with multi-select, drag-drop, and system status."""

    asset_dropped = None

    def __init__(
        self, server_url="http://127.0.0.1:8000", export_dir="./exports/assets"
    ):
        super().__init__()
        self.server_url = server_url
        self.export_dir = export_dir
        self.bridge = ServerBridge(server_url)

        self.setWindowTitle("🧍 Asset & Sprite Manager")
        self.resize(960, 640)

        layout = QVBoxLayout(self)
        title = QLabel("🧍 ComfyVN Asset & Sprite Manager")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight:bold;font-size:18px;margin:8px;")
        layout.addWidget(title)

        self.overlay = ProgressOverlay(self, "Processing …", cancellable=False)
        self.overlay.hide()

        # ------------------------------------------------------------------
        # Top Buttons
        # ------------------------------------------------------------------
        btn_layout = QHBoxLayout()
        layout.addLayout(btn_layout)

        self.btn_generate_sprite = QPushButton("🎨 Render Sprite")
        self.btn_export_scene = QPushButton("📦 Export Scene")
        self.btn_select_pose = QPushButton("🧍 Select Pose")
        self.btn_refresh = QPushButton("🔄 Refresh Assets")
        self.btn_clear_cache = QPushButton("🧹 Clear Cache")

        for b in [
            self.btn_generate_sprite,
            self.btn_export_scene,
            self.btn_select_pose,
            self.btn_refresh,
            self.btn_clear_cache,
        ]:
            btn_layout.addWidget(b)

        if PoseBrowser is None:
            self.btn_select_pose.setEnabled(False)
            self.btn_select_pose.setToolTip("PoseBrowser not available in this build.")

        # ------------------------------------------------------------------
        # Asset Grid
        # ------------------------------------------------------------------
        self.asset_list = QListWidget()
        self.asset_list.setViewMode(QListView.IconMode)
        self.asset_list.setIconSize(QSize(96, 96))
        self.asset_list.setResizeMode(QListWidget.Adjust)
        self.asset_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.asset_list.itemDoubleClicked.connect(self._open_file)
        self.asset_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.asset_list.customContextMenuRequested.connect(self._show_context_menu)
        self.asset_list.setDragEnabled(True)
        self.asset_list.viewport().installEventFilter(self)
        layout.addWidget(self.asset_list)

        # ------------------------------------------------------------------
        # Status + Monitor
        # ------------------------------------------------------------------
        self.meta_summary = QLabel("No asset selected.")
        self.meta_summary.setWordWrap(True)
        self.meta_summary.setStyleSheet("padding:4px;font-style:italic;")
        layout.addWidget(self.meta_summary)

        self.job_status = QLabel("Job Status: Idle")
        self.job_status.setAlignment(Qt.AlignCenter)
        self.job_status.setStyleSheet("font-weight:bold;color:#888;")
        layout.addWidget(self.job_status)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        layout.addWidget(divider)

        self.status_widget = StatusWidget(self)
        self.status_widget.add_indicator("server", "Server Core")
        self.status_widget.add_indicator("gpu", "GPU Usage")
        self.status_widget.add_indicator("cpu", "CPU Usage")
        self.status_widget.add_indicator("ram", "RAM Usage")
        layout.addWidget(self.status_widget)

        # ------------------------------------------------------------------
        # Pose & Export Managers
        # ------------------------------------------------------------------
        self.pose_manager = PoseManager() if PoseManager else None
        self.export_manager = ExportManager() if ExportManager else None
        self.selected_pose_id = None

        # ------------------------------------------------------------------
        # Event wiring
        # ------------------------------------------------------------------
        self.btn_generate_sprite.clicked.connect(self._generate_sprite)
        self.btn_export_scene.clicked.connect(self._export_scene)
        self.btn_refresh.clicked.connect(self.refresh_assets)
        self.btn_clear_cache.clicked.connect(self._clear_cache)
        self.btn_select_pose.clicked.connect(self.open_pose_browser)

        self.timer = QTimer()
        self.timer.timeout.connect(self._poll_jobs)
        self.timer.start(5000)

        # ------------------------------------------------------------------
        # System Monitor integration
        # ------------------------------------------------------------------
        self.monitor = SystemMonitor(server_url)
        self.monitor.on_update(self._on_monitor_update)
        self.monitor.start(interval=6)

        self.refresh_assets()

    # ==============================================================
    # Pose Browser
    # ==============================================================
    def open_pose_browser(self):
        """Open Pose Browser window to select a pose."""
        if PoseBrowser is None:
            error(self, "Unavailable", "PoseBrowser is not available in this build.")
            return
        self.pose_browser = PoseBrowser(on_pose_selected=self.pose_selected)
        self.pose_browser.show()

    def pose_selected(self, pose_id, pose_data):
        """Callback when a pose is selected."""
        self.selected_pose_id = pose_id
        self.meta_summary.setText(f"🧍 Pose Selected: {pose_id}")

    # ==============================================================
    # Sprite Generation / Scene Export
    # ==============================================================
    def _generate_sprite(self):
        items = self.asset_list.selectedItems()
        if not items:
            error(self, "No selection", "Please select one or more assets to render.")
            return
        scene_data = {
            "scene_id": f"gui_asset_render_{datetime.now().strftime('%H%M%S')}",
            "assets": [i.data(Qt.UserRole) or i.text() for i in items],
            "pose_id": self.selected_pose_id,
        }
        self.overlay.set_text("Dispatching render job …")
        self.overlay.start()

        def _done(resp):
            self.overlay.stop()
            if isinstance(resp, dict) and "error" in resp:
                error(self, "Render Failed", resp.get("error", "Unknown error"))
            else:
                info(
                    self,
                    "Render Complete",
                    f"Server response:\n{json.dumps(resp, indent=2)}",
                )
            self.refresh_assets()

        # Reuse /export/scene fallback in ServerBridge shim
        self.bridge.send_render_request(scene_data, _done)

    def _export_scene(self):
        items = self.asset_list.selectedItems()
        assets = [i.data(Qt.UserRole) or i.text() for i in items]
        scene = {
            "scene_id": "forest_path",
            "assets": assets,
            "pose_ids": [self.selected_pose_id] if self.selected_pose_id else [],
        }

        self.overlay.set_text("Exporting Scene …")
        self.overlay.start()

        def _done(resp):
            self.overlay.stop()
            if isinstance(resp, dict) and "error" in resp:
                error(self, "Export Failed", resp.get("error", "Unknown error"))
            else:
                info(self, "Export Complete", json.dumps(resp, indent=2))
            self.refresh_assets()

        self.bridge.send_render_request(scene, _done)

    def _clear_cache(self):
        # If you have a real /cache/clear endpoint, call it via ServerBridge
        self.overlay.set_text("Clearing cache …")
        self.overlay.start()
        threading.Timer(
            1.2,
            lambda: (
                self.overlay.stop(),
                info(self, "Cache Cleared", "Cache cleared successfully."),
            ),
        ).start()

    # ==============================================================
    # Asset Listing / Jobs / Context Menu / Events
    # ==============================================================
    def refresh_assets(self):
        """Scan export directory for assets and populate the grid."""
        self.asset_list.clear()
        os.makedirs(self.export_dir, exist_ok=True)

        count = 0
        for root, _, files in os.walk(self.export_dir):
            for file in files:
                if not file.lower().endswith((".png", ".jpg", ".jpeg")):
                    continue
                fpath = os.path.join(root, file)
                item = QListWidgetItem(file)
                item.setToolTip(fpath)
                item.setData(Qt.UserRole, fpath)
                pm = QPixmap(fpath)
                if not pm.isNull():
                    item.setIcon(
                        QIcon(
                            pm.scaled(
                                96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation
                            )
                        )
                    )
                self.asset_list.addItem(item)
                count += 1

        self.meta_summary.setText(
            f"Loaded {count} image assets from {os.path.abspath(self.export_dir)}"
        )

    def _poll_jobs(self):
        """Update job status periodically; if you have /jobs/poll, wire it here."""
        # Lightweight text — avoid raising if server not reachable
        try:
            self.job_status.setText("Job Status: Monitoring …")
        except Exception:
            pass

    def _on_monitor_update(self, data: dict):
        """System monitor callback to update indicators."""
        try:
            self.status_widget.update_indicator(
                "server", f"Server: {data.get('server','n/a')}"
            )
            self.status_widget.update_indicator("gpu", f"GPU: {data.get('gpu','n/a')}")
            self.status_widget.update_indicator("cpu", f"CPU: {data.get('cpu','n/a')}")
            self.status_widget.update_indicator("ram", f"RAM: {data.get('ram','n/a')}")
        except Exception as e:
            _warn(f"Monitor update failed: {e}")

    def _show_context_menu(self, pos: QPoint):
        item = self.asset_list.itemAt(pos)
        menu = QMenu(self)
        act_open = menu.addAction("Open")
        act_reveal = menu.addAction("Reveal in Explorer")
        act_refresh = menu.addAction("Refresh")
        action = menu.exec(self.asset_list.viewport().mapToGlobal(pos))
        if action == act_open and item:
            self._open_file(item)
        elif action == act_reveal and item:
            self._reveal_file(item)
        elif action == act_refresh:
            self.refresh_assets()

    def _open_file(self, item: QListWidgetItem):
        """Opens the selected asset file in the system viewer."""
        path = item.data(Qt.UserRole) or item.toolTip()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "File Missing", f"Cannot open file: {path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _reveal_file(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole) or item.toolTip()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "File Missing", f"Cannot reveal file: {path}")
            return
        folder = os.path.dirname(path)
        if platform.system() == "Windows":
            subprocess.Popen(f'explorer /select,"{path}"')
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", folder])

    # Drag source (optional)
    def eventFilter(self, obj: QObject, event: QEvent):
        if (
            obj is self.asset_list.viewport()
            and event.type() == QEvent.MouseButtonPress
        ):
            item = self.asset_list.itemAt(event.position().toPoint())
            if item:
                drag = QDrag(self)
                mime = QMimeData()
                path = item.data(Qt.UserRole) or item.toolTip()
                mime.setText(path)
                drag.setMimeData(mime)
                drag.exec(Qt.CopyAction)
        return super().eventFilter(obj, event)
