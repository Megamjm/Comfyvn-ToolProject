from PySide6.QtGui import QAction
# comfyvn/gui/panels/settings_shortcuts_view.py
# [COMFYVN Architect | v1.2 | this chat]
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QInputDialog,
                               QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from comfyvn.core.shortcut_manager import ShortcutManager


class SettingsShortcutsView(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shortcut Manager")
        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Action", "Shortcut"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.table)
        hb = QHBoxLayout()
        self.btn_rebind = QPushButton("Rebind Selected")
        self.btn_clear = QPushButton("Clear Binding")
        hb.addWidget(self.btn_rebind)
        hb.addWidget(self.btn_clear)
        hb.addStretch(1)
        lay.addLayout(hb)
        self.btn_rebind.clicked.connect(self._rebinder)
        self.btn_clear.clicked.connect(self._clear)
        self.table.cellDoubleClicked.connect(self._rebinder)
        self.refresh()

    def refresh(self):
        data = ShortcutManager.list_shortcuts()
        self.table.setRowCount(len(data))
        for i, (name, seq) in enumerate(sorted(data.items())):
            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem(seq))

    def _current_name(self):
        it = self.table.currentItem()
        if not it:
            return None
        row = it.row()
        return self.table.item(row, 0).text()

    def _rebinder(self, *args):
        name = self._current_name()
        if not name:
            QMessageBox.information(self, "Shortcuts", "Select an action first.")
            return
        current = ShortcutManager.list_shortcuts().get(name, "")
        new_seq, ok = QInputDialog.getText(
            self, "Rebind Shortcut", f"{name}\nCurrent: {current}\nNew:"
        )
        if ok:
            ShortcutManager.rebind(name, new_seq or "")
            self.refresh()

    def _clear(self):
        name = self._current_name()
        if not name:
            return
        ShortcutManager.rebind(name, "")
        self.refresh()
