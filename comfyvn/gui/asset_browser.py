# comfyvn/gui/asset_browser.py
# 🎨 Asset & Sprite System Manager — Phase 3.3
# Multi-select / Drag-drop / Server Job integration
# [🎨 GUI Code Production Chat]

import os, json, platform, subprocess, threading, requests
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QHBoxLayout, QListView, QAbstractItemView, QMenu
)
from PySide6.QtGui import QPixmap, QIcon, QCursor, QDrag, QMimeData
from PySide6.QtCore import Qt, QSize, QTimer, QPoint, QByteArray

from comfyvn.gui.components.progress_overlay import ProgressOverlay
from comfyvn.gui.components.dialog_helpers import info, error, confirm


class AssetBrowser(QWidget):
    """Asset Browser & Sprite Manager with multi-select and drag-drop."""

    asset_dropped = None  # external signal placeholder

    def __init__(self, server_url="http://127.0.0.1:8000", export_dir="./exports/assets"):
        super().__init__()
        self.server_url = server_url
        self.export_dir = export_dir

        self.setWindowTitle("🧍 Asset & Sprite Manager")
        self.resize(900, 600)

        layout = QVBoxLayout(self)
        self.setLayout(layout)

        title = QLabel("🧍 ComfyVN Asset & Sprite Manager")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight:bold;font-size:18px;margin:8px;")
        layout.addWidget(title)

        self.overlay = ProgressOverlay(self, "Processing …", cancellable=False)
        self.overlay.hide()

        # ----------------------------------------------------------
        # Top buttons
        # ----------------------------------------------------------
        btn_layout = QHBoxLayout()
        layout.addLayout(btn_layout)

        self.btn_generate_npc = QPushButton("Generate NPCs")
        self.btn_export_character = QPushButton("Export Character")
        self.btn_export_scene = QPushButton("Export Scene")
        self.btn_refresh = QPushButton("🔄 Refresh Assets")
        self.btn_clear_cache = QPushButton("🧹 Clear Cache")

        for b in [self.btn_generate_npc, self.btn_export_character,
                  self.btn_export_scene, self.btn_refresh, self.btn_clear_cache]:
            btn_layout.addWidget(b)

        # ----------------------------------------------------------
        # Asset grid
        # ----------------------------------------------------------
        self.asset_list = QListWidget()
        self.asset_list.setViewMode(QListView.IconMode)
        self.asset_list.setIconSize(QSize(96, 96))
        self.asset_list.setResizeMode(QListWidget.Adjust)
        self.asset_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.asset_list.itemDoubleClicked.connect(self._open_file)
        layout.addWidget(self.asset_list)

        # Context menu / drag-drop
        self.asset_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.asset_list.customContextMenuRequested.connect(self._show_context_menu)
        self.asset_list.setDragEnabled(True)
        self.asset_list.viewport().installEventFilter(self)

        # ----------------------------------------------------------
        # Status labels
        # ----------------------------------------------------------
        self.meta_summary = QLabel("No asset selected.")
        self.meta_summary.setWordWrap(True)
        self.meta_summary.setStyleSheet("padding:4px;font-style:italic;")
        layout.addWidget(self.meta_summary)

        self.job_status = QLabel("Job Status: Idle")
        self.job_status.setAlignment(Qt.AlignCenter)
        self.job_status.setStyleSheet("font-weight:bold;color:#888;")
        layout.addWidget(self.job_status)

        # ----------------------------------------------------------
        # Event wiring
        # ----------------------------------------------------------
        self.btn_generate_npc.clicked.connect(self.generate_npc)
        self.btn_export_character.clicked.connect(self.export_character)
        self.btn_export_scene.clicked.connect(self.export_scene)
        self.btn_refresh.clicked.connect(self.refresh_assets)
        self.btn_clear_cache.clicked.connect(self.clear_cache)

        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_jobs)
        self.timer.start(4000)

        self.refresh_assets()

    # ==============================================================
    # Threaded HTTP utility
    # ==============================================================
    def _thread_request(self, method, endpoint, payload=None, on_success=None, on_error=None):
        def _worker():
            try:
                url = f"{self.server_url.rstrip('/')}/{endpoint.lstrip('/')}"
                r = requests.request(method, url, json=payload, timeout=30)
                r.raise_for_status()
                data = r.json()
                if on_success:
                    on_success(data)
            except Exception as e:
                if on_error:
                    on_error(str(e))
        threading.Thread(target=_worker, daemon=True).start()

    # ==============================================================
    # Core server calls
    # ==============================================================
    def _start_job(self, text, endpoint, payload, success_msg, fail_msg):
        self.overlay.set_text(text)
        self.overlay.start()

        def ok(data):
            self.overlay.stop()
            info(self, text, success_msg.format(**data))
            self.refresh_assets()

        def fail(err):
            self.overlay.stop()
            error(self, "Error", f"{fail_msg}:\n{err}")

        self._thread_request("POST", endpoint, payload, ok, fail)

    def generate_npc(self):
        self._start_job("Generating NPCs …", "npc/generate",
                        {"scene_id": "city_square", "location": "market"},
                        "Generated {npc_count} NPCs successfully.",
                        "Failed to generate NPCs")

    def export_character(self):
        data = {
            "id": "hero_caelum",
            "name": "Caelum",
            "sprite": "hero_caelum.png",
            "metadata": {"pose": "neutral", "expression": "focused"}
        }
        self._start_job("Exporting Character …", "export/character", data,
                        "Character exported to: {export_path}",
                        "Character export failed")

    def export_scene(self):
        data = {"scene_id": "forest_path",
                "assets": ["bg_forest.png", "hero_caelum.png", "npc_01.png"]}
        self._start_job("Exporting Scene …", "export/scene", data,
                        "Scene bundle saved at: {export_path}",
                        "Scene export failed")

    def clear_cache(self):
        self._start_job("Clearing Cache …", "cache/clear", {"ttl": 0},
                        "{message}", "Cache clear failed")

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
    # Context menu
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
            menu.addAction(
                f"🗑 Delete Selected ({len(paths)})",
                lambda: self._delete_assets(paths)
            )
        menu.exec(QCursor.pos())
            
            
# ==============================================================
# File operations
# ==============================================================
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
# Drag-and-drop integration
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

# ==============================================================
# Job polling
# ==============================================================
def poll_jobs(self):
    def ok(data):
        j = data.get("jobs", {})
        self.job_status.setText(
            f"🧩 Jobs — NPCs:{j.get('npc_generation','idle')} | Exports:{j.get('exports','idle')} | Cache:{j.get('cache_status','idle')}"
        )
    def fail(_):
        self.job_status.setText("⚠️ Server offline.")
    self._thread_request("GET", "jobs/poll", None, ok, fail)
