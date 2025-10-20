from PySide6.QtGui import QAction
# comfyvn/gui/panels/command_palette.py
# [COMFYVN Architect | v1.4 | this chat]
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt
from comfyvn.core.command_registry import registry

def _simple_fuzzy(needle: str, hay: str) -> int:
    """Naive fuzzy score: subsequence match bonus."""
    if not needle: return 0
    n = needle.lower(); h = hay.lower()
    score, i = 0, 0
    for ch in n:
        pos = h.find(ch, i)
        if pos < 0: return -1
        score += 5
        if pos == i: score += 2
        i = pos + 1
    return score + max(0, 10 - (len(h) - len(n)))

class CommandPalette(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.setWindowModality(Qt.ApplicationModal)
        self.resize(640, 400)
        v = QVBoxLayout(self)
        self.input = QLineEdit(self); self.input.setPlaceholderText("Type a command…")
        v.addWidget(self.input)
        self.list = QListWidget(self)
        v.addWidget(self.list, 1)
        hb = QHBoxLayout()
        self.hint = QLabel("Enter to run • Esc to close")
        hb.addWidget(self.hint); hb.addStretch(1)
        v.addLayout(hb)
        self.input.textChanged.connect(self.refresh)
        self.list.itemActivated.connect(self._run_selected)
        self.refresh()

    def refresh(self):
        q = self.input.text().strip()
        cmds = registry.list()
        ranked = []
        for cid, cmd in cmds.items():
            title = cmd.title or cid
            score = 100 if not q else _simple_fuzzy(q, f"{title} {cid}")
            if score >= 0:
                ranked.append((score, cid, title, cmd.shortcut))
        ranked.sort(reverse=True)
        self.list.clear()
        for _, cid, title, sc in ranked:
            it = QListWidgetItem(f"{title}    [{cid}]{('  ⌨ '+sc) if sc else ''}")
            it.setData(Qt.UserRole, cid)
            self.list.addItem(it)
        if self.list.count() > 0:
            self.list.setCurrentRow(0)

    def _run_selected(self, *_):
        it = self.list.currentItem()
        if not it: return
        cid = it.data(Qt.UserRole)
        registry.run(cid)
        self.accept()