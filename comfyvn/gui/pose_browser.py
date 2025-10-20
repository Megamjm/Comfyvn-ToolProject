from __future__ import annotations
from PySide6.QtGui import QAction, QPixmap, QPainter, QColor, QPen, QIcon
from PySide6.QtCore import Qt, QPointF, QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QFileDialog, QFrame, QLabel
import json, os, threading
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

try:
    from comfyvn.assets.pose_manager import PoseManager
except Exception:
    PoseManager = None  # type: ignore

class PoseBrowser(QWidget):
    """Simple pose browser widget (GUI-only)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PoseBrowser")
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Pose Browser"))
        # TODO: implement list/grid + preview; GUI-only: no server imports here.
