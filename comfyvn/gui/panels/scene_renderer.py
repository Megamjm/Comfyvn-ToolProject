from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/gui/panels/scene_renderer.py
from pathlib import Path
from typing import Optional
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QDockWidget, QWidget,
    QVBoxLayout, QFileDialog, QMessageBox
)
from PySide6.QtGui import QPainter, QPixmap, QColor, QFont
from PySide6.QtCore import Qt, QRectF
from comfyvn.core.scene_model import load_scene

DATA_SCENE = Path("comfyvn/data/scene.json")

class SceneCanvas(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor("#0E1116"))
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setSceneRect(QRectF(0, 0, 1280, 720))
        self._last_path: Path = DATA_SCENE
        self.reload_from(self._last_path)

    def _add_text_box(self, speaker: str, text: str):
        # very light dialogue box
        box_h = 120
        y0 = 720 - box_h - 10
        rect = self._scene.addRect(10, y0, 1260, box_h, brush=QColor(0,0,0,140))
        title = self._scene.addText(speaker or "", QFont("Segoe UI", 12, QFont.Bold))
        title.setDefaultTextColor(QColor("#29D7D7"))
        title.setPos(28, y0 + 12)

        body = self._scene.addText(text or "", QFont("Segoe UI", 16))
        body.setDefaultTextColor(QColor("#E9EEF1"))
        body.setTextWidth(1220)
        body.setPos(28, y0 + 40)

    def reload_from(self, scene_path: Path):
        self._scene.clear()
        self._last_path = scene_path
        doc = load_scene(scene_path)
        # background
        if doc.background and Path(doc.background).exists():
            bg = QPixmap(doc.background)
            self._scene.addPixmap(bg)
        else:
            self._scene.addText("[No background]").setPos(50, 50)

        # characters sorted by z
        for c in sorted(doc.characters, key=lambda x: x.z):
            if c.src and Path(c.src).exists():
                pm = QPixmap(c.src)
                if c.scale != 1.0:
                    w = int(pm.width() * c.scale)
                    h = int(pm.height() * c.scale)
                    pm = pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                item = self._scene.addPixmap(pm)
                item.setOffset(c.x, c.y)
            else:
                self._scene.addText(f"[{c.id}]").setPos(c.x, c.y)

        # dialogue
        self._add_text_box(doc.dialogue.speaker, doc.dialogue.text)

    def refresh(self):
        self.reload_from(self._last_path)

class JSONSceneDock(QDockWidget):
    """Dock with JSON-driven scene preview and quick actions."""
    def __init__(self):
        super().__init__("Scene Preview")
        self.setObjectName("JSONSceneDock")
        self.setAllowedAreas(Qt.AllDockWidgetAreas)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        self.canvas = SceneCanvas()
        layout.addWidget(self.canvas)
        inner.setLayout(layout)
        self.setWidget(inner)

    def reload_scene(self):
        self.canvas.refresh()

    def open_scene_json(self, parent=None):
        try:
            p = QFileDialog.getOpenFileName(
                parent, "Open Scene JSON", str(DATA_SCENE.parent),
                "JSON Files (*.json)")[0]
            if p:
                self.canvas.reload_from(Path(p))
        except Exception as e:
            QMessageBox.critical(parent or self, "Scene JSON", str(e))