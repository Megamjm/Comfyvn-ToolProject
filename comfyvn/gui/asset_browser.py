# comfyvn/gui/asset_browser.py
# 🎨 Asset & Sprite System Manager — Phase 3.2 Sync
# Replaces direct HTTP calls with ServerBridge integration
# [🎨 GUI Code Production Chat]

import os, json, platform, subprocess, threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QHBoxLayout, QListView, QAbstractItemView, QMenu
)
from PySide6.QtGui import QPixmap, QIcon, QCursor, QDrag, QMimeData
from PySide6.QtCore import Qt, QSize, QTimer, QPoint, QByteArray

from comfyvn.gui.components.progress_overlay import ProgressOverlay
from comfyvn.gui.components.dialog_helpers import info, error, confirm
from comfyvn.gui.server_bridge import ServerBridge


class AssetBrowser(QWidget):
    """Asset Browser & Sprite Manager with multi-select and drag-drop."""

    asset_dropped = None

    def __init__(self, server_url="http://127.0.0.1:8001", export_dir="./exports/assets"):
        super().__init__()
        self.server_url = server_url
        self.export_dir = export_dir
        self.bridge = ServerBridge(server_url)

        self.setWindowTitle("🧍 Asset & Sprite Manager")
        self.resize(900, 600)

        layout = QVBoxLayout(self)
        title = QLabel("🧍 ComfyVN Asset & Sprite Manager")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight:bold;font-size:18px;margin:8px;")
        layout.addWidget(title)

        self.overlay = ProgressOverlay(self, "Processing …", cancellable=False)
        self.overlay.hide()

        # --- Buttons ---------------------------------------------------------
        btn_layout = QHBoxLayout()
        layout.addLayout(btn_layout)

        self.btn_generate_sprite = QPushButton("🎨 Render Sprite")
        self.btn_export_scene = QPushButton("📦 Export Scene")
        self.btn_refresh = QPushButton("🔄 Refresh Assets")
        self.btn_clear_cache = QPushButton("🧹 Clear Cache")

        for b in [self.btn_generate_sprite, self.btn_export_scene, self.btn_refresh, self.btn_clear_cache]:
            btn_layout.addWidget(b)

        # --- Asset grid ------------------------------------------------------
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

        # --- Status labels ---------------------------------------------------
        self.meta_summary = QLabel("No asset selected.")
        self.meta_summary.setWordWrap(True)
        self.meta_summary.setStyleSheet("padding:4px;font-style:italic;")
        layout.addWidget(self.meta_summary)

        self.job_status = QLabel("Job Status: Idle")
        self.job_status.setAlignment(Qt.AlignCenter)
        self.job_status.setStyleSheet("font-weight:bold;color:#888;")
        layout.addWidget(self.job_status)

        # --- Events ----------------------------------------------------------
        self.btn_generate_sprite.clicked.connect(self._generate_sprite)
        self.btn_export_scene.clicked.connect(self._export_scene)
        self.btn_refresh.clicked.connect(self.refresh_assets)
        self.btn_clear_cache.clicked.connect(self._clear_cache)

        self.timer = QTimer()
        self.timer.timeout.connect(self._poll_jobs)
        self.timer.start(5000)

        self.refresh_assets()

    # ==============================================================
    # Sprite Generation / Scene Export
    # ==============================================================
    def _generate_sprite(self):
        """Send /scene/render job to Server Core."""
        items = self.asset_list.selectedItems()
        if not items:
            error(self, "No selection", "Please select one or more assets to render.")
            return

        scene_data = {
            "scene_id": "gui_asset_render",
            "assets": [i.text() for i in items]
        }

        self.overlay.set_text("Dispatching render job …")
        self.overlay.start()

        def _done(resp):
            self.overlay.stop()
            if "error" in resp:
                error(self, "Render Failed", resp["error"])
            else:
                info(self, "Render Complete", f"Server response:\n{json.dumps(resp, indent=2)}")
            self.refresh_assets()

        self.bridge.send_render_request(scene_data, _done)

    def _export_scene(self):
        """Simulate /export/scene API (Server-side bundle)."""
        scene = {"scene_id": "forest_path", "assets": [i.text() for i in self.asset_list.selectedItems()]}
        self.overlay.set_text("Exporting Scene …")
        self.overlay.start()

        def _done(resp):
            self.overlay.stop()
            if "error" in resp:
                error(self, "Export Failed", resp["error"])
            else:
                info(self, "Export Complete", json.dumps(resp, indent=2))
            self.refresh_assets()

        # temporarily use render endpoint until export/scene is implemented
        self.bridge.send_render_request(scene, _done)

    def _clear_cache(self):
        """Mock cache clear request."""
        self.overlay.set_text("Clearing cache …")
        self.overlay.start()
        threading.Timer(1.5, lambda: (self.overlay.stop(), info(self, "Cache Cleared", "Cache cleared successfully."))).start()

    # ==============================================================
    # Asset listing
    # ==============================================================
    def refresh_assets(self):
        self.asset_list.clear()
        os.makedirs(self.export_dir, exist_ok=True)
        for root, _, files in os.walk(self.export_dir):
            for f in files:
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    path = os.path.join(root, f)
                    item = QListWidgetItem(f)
                    item.setToolTip(path)
                    pm = QPixmap(path)
                    if not pm.isNull():
                        item.setIcon(QIcon(pm.scaled(96, 96, Qt.KeepAspectRatio)))
                    self.asset_list.addItem(item)
        self.meta_summary.setText(f"Assets Loaded: {self.asset_list.count()}")

    # ==============================================================
    # Job polling
    # ==============================================================
    def _poll_jobs(self):
        def _cb(data):
            jobs = data.get("jobs", [])
            if isinstance(jobs, list) and jobs:
                active = [j.get("type", "?") for j in jobs if j.get("status") == "running"]
                self.job_status.setText(f"🧩 Active Jobs: {', '.join(active)}")
                self.job_status.setStyleSheet("color: lime; font-weight:bold;")
            else:
                self.job_status.setText("Job Status: Idle")
                self.job_status.setStyleSheet("color:#888; font-weight:bold;")
        self.bridge.poll_jobs(_cb)

    # ==============================================================
    # Context & File operations
    # ==============================================================
    def _show_context_menu(self, pos: QPoint):
        items = self.asset_list.selectedItems()
        if not items:
            return
        menu = QMenu(self)
        paths = [i.toolTip() for i in items]
        if len(paths) == 1:
            menu.addAction("🖼 Open", lambda: self._open_file(paths[0]))
            menu.addAction("📂 Show in Folder", lambda: self._show_in_folder(paths[0]))
            menu.addAction("ℹ️ View Metadata", lambda: self._show_metadata(paths[0]))
            menu.addSeparator()
            menu.addAction("🗑 Delete", lambda: self._delete_assets(paths))
        else:
            menu.addAction(f"🖼 Open All ({len(paths)})", lambda: [self._open_file(p) for p in paths])
            menu.addAction(f"📂 Show All ({len(paths)})", lambda: [self._show_in_folder(p) for p in paths])
            menu.addSeparator()
            menu.addAction(f"🗑 Delete Selected ({len(paths)})", lambda: self._delete_assets(paths))
        menu.exec(QCursor.pos())

    def _open_file(self, path):
        if isinstance(path, QListWidgetItem):
            path = path.toolTip()
        if not os.path.exists(path):
            error(self, "Missing", "File not found.")
            return
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        except Exception as e:
            error(self, "Error", str(e))

    def _show_in_folder(self, path):
        if not os.path.exists(path):
            error(self, "Missing", "File not found.")
            return
        folder = os.path.dirname(path)
        try:
            if platform.system() == "Windows":
                subprocess.run(["explorer", "/select,", path])
            elif platform.system() == "Darwin":
                subprocess.run(["open", folder])
            else:
                subprocess.run(["xdg-open", folder])
        except Exception as e:
            error(self, "Error", str(e))

    def _delete_assets(self, paths):
        if not confirm(self, "Delete Assets", f"Delete {len(paths)} asset(s)?"):
            return
        for p in paths:
            try:
                os.remove(p)
                meta = os.path.splitext(p)[0] + ".json"
                if os.path.exists(meta):
                    os.remove(meta)
            except Exception as e:
                error(self, "Error", f"Could not delete {p}:\n{e}")
        info(self, "Deleted", f"Removed {len(paths)} asset(s).")
        self.refresh_assets()

    def _show_metadata(self, path):
        mf = os.path.splitext(path)[0] + ".json"
        if not os.path.exists(mf):
            info(self, "Metadata", "No metadata found for this asset.")
            return
        try:
            with open(mf, "r", encoding="utf-8") as f:
                pretty = json.dumps(json.load(f), indent=2)
            info(self, "Metadata", f"<pre>{pretty}</pre>")
        except Exception as e:
            error(self, "Error", f"Failed to read metadata:\n{e}")

    # ==============================================================
    # Drag & Drop
    # ==============================================================
    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self.asset_list.viewport() and event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            item = self.asset_list.itemAt(event.pos())
            if item:
                drag = QDrag(self.asset_list)
                mime = QMimeData()
                mime.setData("application/x-comfyvn-asset",
                             QByteArray(item.toolTip().encode("utf-8")))
                drag.setMimeData(mime)
                drag.exec(Qt.CopyAction)
        return super().eventFilter(obj, event)
