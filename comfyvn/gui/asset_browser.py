# comfyvn/gui/asset_browser.py
# 🎨 GUI Integration for 🧍 Asset & Sprite System — with Previews and Open Functionality
# (ComfyVN_Architect)

import json, os, requests, subprocess, platform
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QHBoxLayout,
    QMessageBox, QFileDialog, QListView, QAbstractItemView
)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QSize, QTimer


class AssetBrowser(QWidget):
    """GUI interface for NPCs, exports, and cache management — with visual previews."""

    def __init__(self, server_url="http://127.0.0.1:8000", export_dir="./exports/assets"):
        super().__init__()
        self.server_url = server_url
        self.export_dir = export_dir
        self.setWindowTitle("🧍 Asset & Sprite Manager")
        self.resize(800, 500)

        # Layout setup
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Title
        title = QLabel("🧍 ComfyVN Asset Manager")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 18px;")
        layout.addWidget(title)

        # Buttons
        btn_layout = QHBoxLayout()
        layout.addLayout(btn_layout)

        self.btn_generate_npc = QPushButton("Generate NPCs")
        self.btn_export_character = QPushButton("Export Character")
        self.btn_export_scene = QPushButton("Export Scene")
        self.btn_refresh = QPushButton("🔄 Refresh Assets")
        self.btn_clear_cache = QPushButton("🧹 Clear Cache")

        for btn in [
            self.btn_generate_npc, self.btn_export_character,
            self.btn_export_scene, self.btn_refresh, self.btn_clear_cache
        ]:
            btn_layout.addWidget(btn)

        # Asset list
        self.asset_list = QListWidget()
        self.asset_list.setViewMode(QListView.IconMode)
        self.asset_list.setIconSize(QSize(96, 96))
        self.asset_list.setResizeMode(QListWidget.Adjust)
        self.asset_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.asset_list.itemDoubleClicked.connect(self.open_asset)
        layout.addWidget(self.asset_list)

        # Job status
        self.job_status = QLabel("Job Status: Idle")
        layout.addWidget(self.job_status)

        # Bind buttons
        self.btn_generate_npc.clicked.connect(self.generate_npc)
        self.btn_export_character.clicked.connect(self.export_character)
        self.btn_export_scene.clicked.connect(self.export_scene)
        self.btn_refresh.clicked.connect(self.refresh_assets)
        self.btn_clear_cache.clicked.connect(self.clear_cache)

        # Auto job polling every 4s
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_jobs)
        self.timer.start(4000)

        # Initial asset load
        self.refresh_assets()

    # -----------------------------------------------------------
    # 🧍 Core Server Calls
    # -----------------------------------------------------------

    def generate_npc(self):
        """Generate faceless NPCs from server."""
        payload = {"scene_id": "city_square", "location": "market"}
        try:
            res = requests.post(f"{self.server_url}/npc/generate", json=payload)
            data = res.json()
            count = data.get("npc_count", 0)
            QMessageBox.information(self, "NPC Generation", f"Generated {count} NPCs successfully.")
            self.refresh_assets()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate NPCs:\n{e}")

    def export_character(self):
        """Export a test character."""
        character_data = {
            "id": "hero_caelum",
            "name": "Caelum",
            "sprite": "hero_caelum.png",
            "metadata": {"pose": "neutral", "expression": "focused"}
        }
        try:
            res = requests.post(f"{self.server_url}/export/character", json=character_data)
            data = res.json()
            QMessageBox.information(self, "Export", f"Character exported to: {data.get('export_path')}")
            self.refresh_assets()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Character export failed:\n{e}")

    def export_scene(self):
        """Export a mock scene layer."""
        scene_data = {
            "scene_id": "forest_path",
            "assets": ["bg_forest.png", "hero_caelum.png", "npc_01.png"]
        }
        try:
            res = requests.post(f"{self.server_url}/export/scene", json=scene_data)
            data = res.json()
            QMessageBox.information(self, "Scene Export", f"Scene bundle saved at: {data.get('export_path')}")
            self.refresh_assets()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Scene export failed:\n{e}")

    def clear_cache(self):
        """Clear expired cache entries."""
        try:
            res = requests.post(f"{self.server_url}/cache/clear", json={"ttl": 0})
            data = res.json()
            QMessageBox.information(self, "Cache", data.get("message", "Cache cleared"))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cache clear failed:\n{e}")

    # -----------------------------------------------------------
    # 🧩 Asset Browser Logic
    # -----------------------------------------------------------

    def refresh_assets(self):
        """Scan export directory for available assets."""
        self.asset_list.clear()
        if not os.path.exists(self.export_dir):
            os.makedirs(self.export_dir, exist_ok=True)

        for root, dirs, files in os.walk(self.export_dir):
            for file in files:
                if file.endswith(".png"):
                    item = QListWidgetItem(file)
                    item.setToolTip(os.path.join(root, file))
                    pixmap = QPixmap(os.path.join(root, file))
                    if not pixmap.isNull():
                        item.setIcon(QIcon(pixmap))
                    else:
                        item.setIcon(QIcon())  # fallback
                    self.asset_list.addItem(item)

    def open_asset(self, item):
        """Double-click handler: open sprite image externally."""
        path = item.toolTip()
        if not os.path.exists(path):
            QMessageBox.warning(self, "File Missing", "This asset no longer exists.")
            return

        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")

    # -----------------------------------------------------------
    # 🔁 Job Polling
    # -----------------------------------------------------------

    def poll_jobs(self):
        """Poll FastAPI for job statuses."""
        try:
            res = requests.get(f"{self.server_url}/jobs/poll")
            data = res.json()
            jobs = data.get("jobs", {})
            self.job_status.setText(
                f"Job Status — NPCs: {jobs.get('npc_generation')} | "
                f"Exports: {jobs.get('exports')} | Cache: {jobs.get('cache_status')}"
            )
        except Exception:
            self.job_status.setText("⚠️ Server offline.")
