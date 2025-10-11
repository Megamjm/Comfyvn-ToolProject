# comfyvn/gui/pose_browser.py
# 🎨 Pose Browser + Preview Panel for Asset & Sprite System (ComfyVN_Architect)

import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QHBoxLayout, QMessageBox, QTextEdit, QSplitter, QFrame
)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QSize

from modules.pose_manager import PoseManager


class PoseBrowser(QWidget):
    """GUI interface for browsing, previewing, and selecting character poses."""

    def __init__(self, on_pose_selected=None):
        super().__init__()
        self.pose_manager = PoseManager()
        self.on_pose_selected = on_pose_selected
        self.selected_pose_id = None

        self.setWindowTitle("🧍 Pose Browser + Preview")
        self.resize(900, 500)

        # Root layout with splitter (list + preview)
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        title = QLabel("🧍 Pose Browser & Inspector")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 18px;")
        main_layout.addWidget(title)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # ---------------------------------------------------
        # Pose List
        # ---------------------------------------------------
        self.pose_list = QListWidget()
        self.pose_list.setViewMode(QListWidget.IconMode)
        self.pose_list.setIconSize(QSize(96, 96))
        self.pose_list.setSpacing(10)
        self.pose_list.itemClicked.connect(self.preview_pose)
        splitter.addWidget(self.pose_list)

        # ---------------------------------------------------
        # Preview Panel
        # ---------------------------------------------------
        preview_panel = QWidget()
        preview_layout = QVBoxLayout()
        preview_panel.setLayout(preview_layout)
        splitter.addWidget(preview_panel)

        self.preview_image = QLabel("No Pose Selected")
        self.preview_image.setAlignment(Qt.AlignCenter)
        self.preview_image.setFixedHeight(250)
        self.preview_image.setStyleSheet(
            "border: 1px solid #888; background-color: #222; color: #fff;"
        )
        preview_layout.addWidget(self.preview_image)

        self.pose_metadata_label = QLabel("Metadata:")
        self.pose_metadata_label.setAlignment(Qt.AlignLeft)
        self.pose_metadata_label.setStyleSheet("font-weight: bold;")
        preview_layout.addWidget(self.pose_metadata_label)

        self.metadata_view = QTextEdit()
        self.metadata_view.setReadOnly(True)
        self.metadata_view.setFrameShape(QFrame.StyledPanel)
        preview_layout.addWidget(self.metadata_view)

        # ---------------------------------------------------
        # Buttons
        # ---------------------------------------------------
        btn_layout = QHBoxLayout()
        main_layout.addLayout(btn_layout)

        self.btn_refresh = QPushButton("🔄 Refresh Poses")
        self.btn_fetch = QPushButton("🌐 Auto-Fetch Poses")
        self.btn_select = QPushButton("✅ Assign Pose")

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_fetch)
        btn_layout.addWidget(self.btn_select)

        self.btn_refresh.clicked.connect(self.refresh_pose_list)
        self.btn_fetch.clicked.connect(self.auto_fetch)
        self.btn_select.clicked.connect(self.confirm_selection)

        # Initial load
        self.refresh_pose_list()

    # ---------------------------------------------------
    # Pose Management
    # ---------------------------------------------------
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
            item.setToolTip(f"{pose_id} — {pose.get('metadata', {}).get('source', 'Unknown')}")
            self.pose_list.addItem(item)

    def auto_fetch(self):
        """Fetch from known public pose sources."""
        QMessageBox.information(self, "Fetching", "Fetching open pose packs (this may take a moment)...")
        self.pose_manager.auto_fetch_all()
        self.refresh_pose_list()
        QMessageBox.information(self, "Complete", "Pose packs fetched and loaded.")

    def preview_pose(self, item):
        """Display preview + metadata for selected pose."""
        pose_id = item.text()
        self.selected_pose_id = pose_id
        pose_data = self.pose_manager.get_pose(pose_id)
        if not pose_data:
            return

        preview_path = pose_data.get("preview_image", "")
        if preview_path and os.path.exists(preview_path):
            pixmap = QPixmap(preview_path)
            self.preview_image.setPixmap(
                pixmap.scaled(250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.preview_image.setText("🧍 No preview available")

        # Display metadata and skeleton JSON (trimmed for readability)
        meta = pose_data.get("metadata", {})
        skeleton = pose_data.get("skeleton", {})
        info = {
            "pose_id": pose_id,
            "source": meta.get("source", "Unknown"),
            "imported_at": meta.get("imported_at", "Unknown"),
            "keypoints": len(skeleton) if isinstance(skeleton, dict) else "N/A",
        }

        meta_text = json.dumps(info, indent=2)
        if skeleton:
            meta_text += "\n\nSkeleton (truncated):\n" + json.dumps(
                {k: skeleton[k] for k in list(skeleton)[:5]}, indent=2
            )

        self.metadata_view.setText(meta_text)

    def confirm_selection(self):
        """Send selected pose back to Asset Manager or Exporter."""
        if not self.selected_pose_id:
            QMessageBox.warning(self, "No Pose", "Please select a pose before confirming.")
            return

        pose_data = self.pose_manager.get_pose(self.selected_pose_id)
        if self.on_pose_selected:
            self.on_pose_selected(self.selected_pose_id, pose_data)
        QMessageBox.information(
            self, "Pose Selected", f"Pose '{self.selected_pose_id}' assigned successfully."
        )
        self.close()
