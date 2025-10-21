from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

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
