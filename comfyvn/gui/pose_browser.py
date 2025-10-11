# comfyvn/gui/pose_browser.py
# 🎨 Pose Browser and Selector GUI for Asset & Sprite System (ComfyVN_Architect)

import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QHBoxLayout, QMessageBox
)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QSize

from modules.pose_manager import PoseManager


class PoseBrowser(QWidget):
    """GUI interface for browsing and selecting character poses."""

    def __init__(self, on_pose_selected=None):
        super().__init__()
        self.pose_manager = PoseManager()
        self.on_pose_selected = on_pose_selected  # callback for export manager
        self.selected_pose_id = None

        self.setWindowTitle("🧍 Pose Selector")
        self.resize(600, 400)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Header
        title = QLabel("🧍 Pose Browser")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 18px;")
        layout.addWidget(title)

        # Pose list
        self.pose_list = QListWidget()
        self.pose_list.setViewMode(QListWidget.IconMode)
        self.pose_list.setIconSize(QSize(96, 96))
        self.pose_list.setSpacing(10)
        self.pose_list.itemClicked.connect(self.select_pose)
        layout.addWidget(self.pose_list)

        # Buttons
        btn_layout = QHBoxLayout()
        layout.addLayout(btn_layout)
        self.btn_refresh = QPushButton("🔄 Refresh Poses")
        self.btn_select = QPushButton("✅ Assign Pose")
        self.btn_fetch = QPushButton("🌐 Auto-Fetch Poses")
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_fetch)
        btn_layout.addWidget(self.btn_select)

        self.btn_refresh.clicked.connect(self.refresh_pose_list)
        self.btn_fetch.clicked.connect(self.auto_fetch)
        self.btn_select.clicked.connect(self.confirm_selection)

        self.refresh_pose_list()

    # ------------------------------------------------------------
    # Pose Management
    # ------------------------------------------------------------
    def refresh_pose_list(self):
        """Reload the available poses from the registry."""
        self.pose_list.clear()
        poses = self.pose_manager.registry
        if not poses:
            self.pose_list.addItem("No poses available. Try auto-fetching.")
            return

        for pose_id, pose in poses.items():
            item = QListWidgetItem(pose_id)
            preview = pose.get("preview_image", "")
            if preview and os.path.exists(preview):
                pixmap = QPixmap(preview)
                if not pixmap.isNull():
                    icon = QIcon(pixmap.scaled(96, 96, Qt.KeepAspectRatio))
                    item.setIcon(icon)
            else:
                item.setIcon(QIcon())  # fallback
            item.setToolTip(pose_id)
            self.pose_list.addItem(item)

    def auto_fetch(self):
        """Fetch from known public pose sources."""
        QMessageBox.information(self, "Fetching", "Fetching open pose packs (this may take a moment)...")
        self.pose_manager.auto_fetch_all()
        self.refresh_pose_list()
        QMessageBox.information(self, "Complete", "Pose packs fetched and loaded.")

    def select_pose(self, item):
        """When a pose is clicked."""
        self.selected_pose_id = item.text()

    def confirm_selection(self):
        """Send selected pose back to Asset Manager or Exporter."""
        if not self.selected_pose_id:
            QMessageBox.warning(self, "No Pose", "Please select a pose before confirming.")
            return

        pose_data = self.pose_manager.get_pose(self.selected_pose_id)
        if self.on_pose_selected:
            self.on_pose_selected(self.selected_pose_id, pose_data)
        QMessageBox.information(self, "Pose Selected", f"Pose '{self.selected_pose_id}' assigned successfully.")
        self.close()
