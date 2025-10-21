import json
import os

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)


class EditorView(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel("Scenes"))
        self.scene_list = QListWidget()
        left.addWidget(self.scene_list, 1)
        btn_new = QPushButton("New Scene")
        left.addWidget(btn_new)
        btn_new.clicked.connect(self.new_scene)
        root.addLayout(left, 1)
        center = QVBoxLayout()
        center.addWidget(QLabel("Dialogue / Script"))
        self.editor = QTextEdit()
        center.addWidget(self.editor, 3)
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.save_scene)
        center.addWidget(btn_save)
        root.addLayout(center, 3)
        right = QVBoxLayout()
        right.addWidget(QLabel("Meta"))
        self.meta = QTextEdit()
        right.addWidget(self.meta, 2)
        root.addLayout(right, 1)
        self.scene_list.itemSelectionChanged.connect(self._load_selected)
        self.refresh()

    def refresh(self):
        self.scene_list.clear()
        if not self.state.project_path:
            return
        sdir = os.path.join(self.state.project_path, "scenes")
        os.makedirs(sdir, exist_ok=True)
        for fn in sorted(os.listdir(sdir)):
            if fn.endswith(".json"):
                it = QListWidgetItem(fn)
                it.setData(32, os.path.join(sdir, fn))
                self.scene_list.addItem(it)

    def _load_selected(self):
        it = self.scene_list.currentItem()
        if not it:
            return
        path = it.data(32)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.editor.setPlainText(data.get("script", ""))
            self.meta.setPlainText(json.dumps(data.get("meta", {}), indent=2))
        except Exception:
            self.editor.clear()
            self.meta.clear()

    def new_scene(self):
        if not self.state.project_path:
            return
        sdir = os.path.join(self.state.project_path, "scenes")
        os.makedirs(sdir, exist_ok=True)
        name = QFileDialog.getSaveFileName(
            self, "New Scene JSON", sdir, "JSON (*.json)"
        )[0]
        if not name:
            return
        base = {
            "id": os.path.splitext(os.path.basename(name))[0],
            "script": "",
            "meta": {},
        }
        with open(name, "w", encoding="utf-8") as f:
            json.dump(base, f, indent=2)
            self.refresh()

    def save_scene(self):
        it = self.scene_list.currentItem()
        if not it:
            return
        path = it.data(32)
        import json as _j

        data = {
            "script": self.editor.toPlainText(),
            "meta": _j.loads(self.meta.toPlainText() or "{}"),
        }
        with open(path, "w", encoding="utf-8") as f:
            _j.dump(data, f, indent=2)
