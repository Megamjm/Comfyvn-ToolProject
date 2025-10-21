# comfyvn/gui/windows/theme_manager_window.py
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QListWidget, QMessageBox, QPushButton,
                               QVBoxLayout)

from comfyvn.core.theme_manager import (apply_theme, export_theme,
                                        import_theme, list_themes,
                                        save_custom_theme)


class ThemeManagerWindow(QDialog):
    def __init__(self, parent=None, app=None):
        super().__init__(parent)
        self.setWindowTitle("Theme Manager")
        self._app = app

        v = QVBoxLayout(self)
        v.addWidget(QLabel("Available Themes:"))
        self.listbox = QListWidget()
        for name in list_themes():
            self.listbox.addItem(name)
        v.addWidget(self.listbox)

        h = QHBoxLayout()
        btn_apply = QPushButton("Apply")
        btn_export = QPushButton("Export…")
        btn_import = QPushButton("Import…")
        btn_custom = QPushButton("Save as Custom")
        h.addWidget(btn_apply)
        h.addWidget(btn_export)
        h.addWidget(btn_import)
        h.addWidget(btn_custom)
        v.addLayout(h)

        btn_apply.clicked.connect(self._apply)
        btn_export.clicked.connect(self._export)
        btn_import.clicked.connect(self._import)
        btn_custom.clicked.connect(self._save_custom)

    def _selected(self):
        it = self.listbox.currentItem()
        return it.text() if it else None

    def _apply(self):
        name = self._selected()
        if not name:
            return
        try:
            apply_theme(self._app, name)
        except Exception as e:
            QMessageBox.critical(self, "Theme", str(e))

    def _export(self):
        name = self._selected()
        if not name:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Theme", f"{name}.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            export_theme(path, name)
        except Exception as e:
            QMessageBox.critical(self, "Export", str(e))

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Theme", "", "JSON (*.json)")
        if not path:
            return
        try:
            names = import_theme(path)
            if names:
                self.listbox.clear()
                for n in list_themes():
                    self.listbox.addItem(n)
        except Exception as e:
            QMessageBox.critical(self, "Import", str(e))

    def _save_custom(self):
        # take currently applied palette from manager would be ideal;
        # for now, just copy the selected into "custom"
        name = self._selected()
        if not name:
            return
        try:
            from comfyvn.core.theme_manager import load_palette

            pal = load_palette(name)
            save_custom_theme(pal, "custom")
            QMessageBox.information(self, "Theme", "Saved as 'custom'.")
        except Exception as e:
            QMessageBox.critical(self, "Custom", str(e))
