from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/gui/panels/scene_composer.py
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QGraphicsView,QGraphicsScene,QLabel
from PySide6.QtCore import Qt
class SceneComposer(QWidget):
    """Simple live render scene canvas placeholder."""
    def __init__(self,parent=None):
        super().__init__(parent)
        v=QVBoxLayout(self)
        self.label=QLabel("Scene Composer — drag assets here (stub)")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setProperty("accent",True)
        v.addWidget(self.label)
        self.scene=QGraphicsScene(self)
        self.view=QGraphicsView(self.scene)
        v.addWidget(self.view,1)
        hb=QHBoxLayout()
        self.btn_render=QPushButton("Submit Render")
        hb.addWidget(self.btn_render)
        v.addLayout(hb)