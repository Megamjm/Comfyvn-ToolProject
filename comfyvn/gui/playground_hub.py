# comfyvn/gui/playground_hub.py
# 🧩 Playground Hub — v0.4.4 (Phase 3.6-F)
# Unified GUI for Scene Prompt Editor + Pose Interpolator
# [ComfyVN_Architect | Asset & Sprite System Integration]

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QLabel
from PySide6.QtCore import Qt


class PlaygroundHub(QWidget):
    """Unified hub combining Scene Playground and Pose Playground."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧩 ComfyVN Playground Hub")
        self.resize(1100, 700)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("🧩 ComfyVN Playground Hub — Multi-Mode Editor")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight:bold;font-size:20px;margin:4px;")
        layout.addWidget(title)

        # Tabbed interface
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Lazy import avoids circular dependencies and heavy startup load
        from comfyvn.gui.playground_ui import PlaygroundUI
        from comfyvn.gui.playground_window import PlaygroundWindow

        # Add Scene Playground
        self.scene_tab = PlaygroundUI()
        self.tabs.addTab(self.scene_tab, "🎭 Scene Editor (LLM)")

        # Add Pose Playground
        self.pose_tab = PlaygroundWindow()
        self.tabs.addTab(self.pose_tab, "🧍 Pose Animator (Δ Interpolation)")

        # Future expansion
        # self.tabs.addTab(QWidget(), "🧠 AI Simulation (future)")

        self.tabs.setCurrentIndex(0)
