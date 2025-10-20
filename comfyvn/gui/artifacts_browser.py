from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from comfyvn.gui.services.server_bridge import ServerBridge

class ArtifactsBrowser(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.bridge=ServerBridge()
        self.list = QListWidget(); self.list.currentItemChanged.connect(self._on_select)
        self.preview = QLabel("No selection"); self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumHeight(320)
        btn = QPushButton("Refresh"); btn.clicked.connect(self.refresh)
        bar = QHBoxLayout(); bar.addWidget(QLabel("Artifacts")); bar.addWidget(btn)
        lay = QVBoxLayout(self); lay.addLayout(bar); lay.addWidget(self.list); lay.addWidget(self.preview)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for it in self.bridge.artifacts():
            q = QListWidgetItem(f"{it.get('path')}  ({it.get('size')})"); q.setData(Qt.UserRole, it.get('path')); self.list.addItem(q)

    def _on_select(self, cur, prev):
        if not cur: self.preview.setText("No selection"); return
        try:
            data = self.bridge.artifact_download(cur.data(Qt.UserRole))
            pm = QPixmap(); pm.loadFromData(data)
            if pm.isNull(): self.preview.setText("Invalid image")
            else: self.preview.setPixmap(pm.scaledToHeight(320, Qt.SmoothTransformation))
        except Exception as e:
            self.preview.setText(str(e))