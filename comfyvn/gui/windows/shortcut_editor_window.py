from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor
# comfyvn/gui/windows/shortcut_editor_window.py
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from comfyvn.config.runtime_paths import config_dir
from comfyvn.core.shortcut_registry import DEFAULTS, shortcut_registry
from comfyvn.gui.widgets.shortcut_capture import ShortcutCapture


class ShortcutEditorWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shortcut Editor")
        self.resize(700, 520)

        v = QVBoxLayout(self)
        info = QLabel(
            "Select a row → press ‘Record’ → press keys → Apply/Save.\n"
            "Conflicts are highlighted."
        )
        info.setProperty("accent", True)
        v.addWidget(info)

        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Action", "Shortcut", ""])
        self.table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.table)

        # recorder row
        rec_row = QHBoxLayout()
        rec_row.addWidget(QLabel("Recorder:"))
        self.capture = ShortcutCapture(self)
        self.btn_record = QPushButton("Record")
        self.btn_assign = QPushButton("Assign to Selected")
        rec_row.addWidget(self.capture, 1)
        rec_row.addWidget(self.btn_record)
        rec_row.addWidget(self.btn_assign)
        v.addLayout(rec_row)

        # buttons
        hb = QHBoxLayout()
        self.btn_reset = QPushButton("Reset Defaults")
        self.btn_reload = QPushButton("Reload From File")
        self.btn_apply = QPushButton("Apply")
        self.btn_save = QPushButton("Save")
        self.btn_close = QPushButton("Close")
        for b in (
            self.btn_reset,
            self.btn_reload,
            self.btn_apply,
            self.btn_save,
            self.btn_close,
        ):
            hb.addWidget(b)
        v.addLayout(hb)

        self.btn_record.clicked.connect(self._on_record)
        self.btn_assign.clicked.connect(self._on_assign)
        self.btn_reset.clicked.connect(self.on_reset)
        self.btn_reload.clicked.connect(self.on_reload)
        self.btn_apply.clicked.connect(self.on_apply)
        self.btn_save.clicked.connect(self.on_save)
        self.btn_close.clicked.connect(self.close)

        self._pending_changes = {}
        self.populate()
        self.table.itemSelectionChanged.connect(self._clear_recorder)

    def _clear_recorder(self):
        self.capture.setText("")
        self.capture._seq = None

    def _on_record(self):
        # Focus the capture box; next keypress will set the sequence
        self.capture.setFocus()

    def _on_assign(self):
        seq = self.capture.sequence()
        if not seq:
            QMessageBox.information(
                self, "Shortcuts", "Press ‘Record’ and type a key combo first."
            )
            return
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Shortcuts", "Select a row to assign.")
            return
        name = self.table.item(rows[0].row(), 0).text()
        self._pending_changes[name] = seq
        self.table.item(rows[0].row(), 1).setText(seq)
        self._check_conflicts()

    def populate(self):
        data = shortcut_registry.shortcuts
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for row, (name, seq) in enumerate(sorted(data.items())):
            self.table.insertRow(row)
            a = QTableWidgetItem(name)
            a.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            b = QTableWidgetItem(seq)
            b.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(row, 0, a)
            self.table.setItem(row, 1, b)
            # Reset button per row
            btn = QPushButton("Reset")
            btn.clicked.connect(lambda _=False, n=name, r=row: self._reset_row(n, r))
            container = QWidget()
            lay = QHBoxLayout(container)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(btn, alignment=Qt.AlignCenter)
            self.table.setCellWidget(row, 2, container)
        self.table.blockSignals(False)
        self._check_conflicts()

    def _reset_row(self, name: str, row: int):
        seq = DEFAULTS.get(name, "")
        self._pending_changes[name] = seq
        self.table.item(row, 1).setText(seq)
        self._check_conflicts()

    def _check_conflicts(self):
        # Highlight duplicate sequences
        seq_map = {}
        for r in range(self.table.rowCount()):
            seq = self.table.item(r, 1).text().strip()
            if not seq:
                continue
            seq_map.setdefault(seq.lower(), []).append(r)

        conflict_rows = set()
        for rows in seq_map.values():
            if len(rows) > 1:
                conflict_rows.update(rows)

        # paint rows
        normal = QBrush()
        conflict = QBrush(QColor("#51202B"))  # subtle red panel
        for r in range(self.table.rowCount()):
            brush = conflict if r in conflict_rows else normal
            self.table.item(r, 0).setBackground(brush)
            self.table.item(r, 1).setBackground(brush)

    def on_reset(self):
        shortcut_registry.shortcuts = DEFAULTS.copy()
        self._pending_changes.clear()
        self.populate()

    def on_reload(self):
        shortcut_registry.load_from_file()
        self._pending_changes.clear()
        self.populate()

    def on_apply(self):
        shortcut_registry.shortcuts.update(self._pending_changes)
        win = self.parent()
        try:
            while win and not hasattr(win, "addToolBar"):
                win = win.parent()
        except Exception:
            pass
        if win:
            shortcut_registry.apply_to_window(win)
        self._pending_changes.clear()
        QMessageBox.information(self, "Shortcuts", "Applied to current session.")

    def on_save(self):
        self.on_apply()
        shortcut_registry.save_to_file()
        target = config_dir("settings")
        QMessageBox.information(
            self, "Shortcuts", f"Saved to user settings directory:\n{target}"
        )
