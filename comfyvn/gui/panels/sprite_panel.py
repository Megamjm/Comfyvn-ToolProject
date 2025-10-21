from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QFileDialog,
    QTextEdit,
)

from comfyvn.assets.persona_manager import PersonaManager
from comfyvn.assets.pose_manager import PoseManager


class SpritePanel(QDockWidget):
    """UI panel allowing persona sprite and pose management."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("Sprites & Poses", parent)
        self.setAllowedAreas(Qt.AllDockWidgetAreas)

        self.manager = PersonaManager()
        self.pose_manager = PoseManager()
        self._current_persona: Optional[str] = None

        root = QWidget(self)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # Persona list column
        persona_column = QVBoxLayout()
        persona_column.addWidget(QLabel("Personas"))
        self.persona_list = QListWidget()
        self.persona_list.currentItemChanged.connect(self._on_persona_selected)
        persona_column.addWidget(self.persona_list, 1)

        btn_row = QHBoxLayout()
        self.btn_add_persona = QPushButton("Register…")
        self.btn_refresh = QPushButton("Refresh")
        btn_row.addWidget(self.btn_add_persona)
        btn_row.addWidget(self.btn_refresh)
        persona_column.addLayout(btn_row)
        layout.addLayout(persona_column, 1)

        # Detail column
        detail_column = QVBoxLayout()

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(240, 240)
        self.preview.setStyleSheet("QLabel { border: 1px solid #444; background: #111; }")
        detail_column.addWidget(self.preview)

        self.expression_combo = QComboBox()
        self.expression_combo.currentTextChanged.connect(self._apply_expression)
        detail_column.addWidget(QLabel("Expression"))
        detail_column.addWidget(self.expression_combo)

        pose_row = QHBoxLayout()
        self.pose_combo = QComboBox()
        self.pose_combo.setEditable(False)
        self.pose_combo.currentIndexChanged.connect(self._update_pose_preview)
        pose_row.addWidget(self.pose_combo, 1)
        self.btn_browse_pose = QPushButton("Browse…")
        pose_row.addWidget(self.btn_browse_pose)
        self.btn_apply_pose = QPushButton("Apply Pose")
        pose_row.addWidget(self.btn_apply_pose)
        detail_column.addWidget(QLabel("Pose"))
        detail_column.addLayout(pose_row)

        self.pose_preview = QTextEdit()
        self.pose_preview.setReadOnly(True)
        self.pose_preview.setPlaceholderText("Pose data preview…")
        detail_column.addWidget(self.pose_preview, 1)

        layout.addLayout(detail_column, 2)

        root.setLayout(layout)
        self.setWidget(root)

        # Bind buttons
        self.btn_refresh.clicked.connect(self._refresh_personas)
        self.btn_add_persona.clicked.connect(self._register_persona)
        self.btn_browse_pose.clicked.connect(self._browse_pose)
        self.btn_apply_pose.clicked.connect(self._apply_pose_selection)

        self._refresh_personas()
        self._refresh_pose_library()

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        pixmap = self.preview.pixmap()
        if pixmap:
            scaled = pixmap.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview.setPixmap(scaled)

    # ------------------------------------------------------------------
    # Persona handling
    # ------------------------------------------------------------------
    def _refresh_personas(self) -> None:
        self.manager._load_existing()
        self.persona_list.clear()
        for pid in sorted(self.manager.personas.keys()):
            item = QListWidgetItem(pid)
            item.setData(Qt.UserRole, pid)
            self.persona_list.addItem(item)
        if self.persona_list.count() and not self.persona_list.currentItem():
            self.persona_list.setCurrentRow(0)

    def _register_persona(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        pid, ok = QInputDialog.getText(self, "Register Persona", "Persona ID")
        if not ok or not pid.strip():
            return
        pid = pid.strip()
        sprite_folder = QFileDialog.getExistingDirectory(
            self,
            "Select Sprite Folder",
            os.path.join(self.manager.sprite_root, pid),
        )
        profile = {"sprite_folder": sprite_folder} if sprite_folder else {}
        self.manager.register_persona(pid, profile)
        self._refresh_personas()

    def _on_persona_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self._current_persona = None
            self.expression_combo.clear()
            self.preview.clear()
            return
        persona_id = current.data(Qt.UserRole)
        self._current_persona = persona_id
        profile = self.manager.load_persona(persona_id) or {}
        expressions = self.manager.list_expressions(persona_id)
        self.expression_combo.blockSignals(True)
        self.expression_combo.clear()
        for expr in expressions:
            self.expression_combo.addItem(expr)
        current_expr = profile.get("expression")
        if current_expr and current_expr in expressions:
            index = self.expression_combo.findText(current_expr)
            if index >= 0:
                self.expression_combo.setCurrentIndex(index)
        self.expression_combo.blockSignals(False)
        self._update_preview(profile.get("current_sprite"))

        pose = profile.get("poses", {}).get("current")
        if pose:
            self.pose_combo.blockSignals(True)
            existing = self.pose_combo.findData(pose.get("path"))
            if existing >= 0:
                self.pose_combo.setCurrentIndex(existing)
            self.pose_combo.blockSignals(False)
        self._update_pose_preview()

    # ------------------------------------------------------------------
    # Sprite controls
    # ------------------------------------------------------------------
    def _apply_expression(self, expression: str) -> None:
        if not self._current_persona or not expression:
            return
        res = self.manager.set_expression(self._current_persona, expression)
        if res.get("status") == "ok":
            self._update_preview(res.get("sprite"))

    def _update_preview(self, sprite_path: Optional[str]) -> None:
        if not sprite_path or not os.path.exists(sprite_path):
            self.preview.setPixmap(QPixmap())
            self.preview.setText("No sprite preview available")
            return
        pixmap = QPixmap(sprite_path)
        if pixmap.isNull():
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Unable to load sprite")
            return
        self.preview.setText("")
        scaled = pixmap.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(scaled)

    # ------------------------------------------------------------------
    # Pose controls
    # ------------------------------------------------------------------
    def _refresh_pose_library(self) -> None:
        self.pose_combo.clear()
        for pose_path in self.pose_manager.list():
            self.pose_combo.addItem(Path(pose_path).name, pose_path)

    def _browse_pose(self) -> None:
        pose_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Pose JSON",
            str(Path("data/poses")),
            "Pose JSON (*.json)",
        )
        if pose_path:
            if self.pose_combo.findData(pose_path) == -1:
                self.pose_combo.addItem(Path(pose_path).name, pose_path)
            index = self.pose_combo.findData(pose_path)
            if index >= 0:
                self.pose_combo.setCurrentIndex(index)

    def _apply_pose_selection(self) -> None:
        if not self._current_persona:
            return
        pose_path = self.pose_combo.currentData()
        if not pose_path:
            return
        res = self.manager.set_pose(self._current_persona, pose_path)
        if res.get("status") == "ok":
            self._update_pose_preview()

    def _update_pose_preview(self) -> None:
        if not self._current_persona:
            self.pose_preview.clear()
            return
        pose = self.manager.get_current_pose(self._current_persona)
        if pose:
            self.pose_preview.setPlainText(json.dumps(pose.get("data"), indent=2) if isinstance(pose.get("data"), dict) else str(pose.get("data")))
        else:
            self.pose_preview.clear()


__all__ = ["SpritePanel"]
