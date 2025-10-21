from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
# comfyvn/gui/windows/theme_editor_window.py
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from comfyvn.core.theme_manager import (apply_theme, export_theme,
                                        import_theme, list_themes,
                                        load_palette, save_custom_theme)

_COLOR_KEYS = [
    ("bg", "Background"),
    ("panel", "Panels"),
    ("accent", "Accent"),
    ("highlight", "Highlight"),
    ("text", "Text"),
    ("text2", "Secondary Text"),
    ("border", "Border"),
]


class ThemeEditorWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Theme Editor")
        self.resize(640, 520)

        v = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Preset:"))
        self.cmb = QComboBox(self)
        self.cmb.addItems(list_themes())
        top.addWidget(self.cmb, 1)

        self.btn_load = QPushButton("Load")
        self.btn_apply = QPushButton("Apply")
        self.btn_saveas = QPushButton("Save As Preset…")
        self.btn_export = QPushButton("Export…")
        self.btn_import = QPushButton("Import…")
        for b in (
            self.btn_load,
            self.btn_apply,
            self.btn_saveas,
            self.btn_export,
            self.btn_import,
        ):
            top.addWidget(b)

        v.addLayout(top)

        self.form = QFormLayout()
        self.pickers = {}
        for key, label in _COLOR_KEYS:
            btn = QPushButton("Pick")
            btn.clicked.connect(lambda _=False, k=key: self._pick_color(k))
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addStretch(1)
            row.addWidget(btn)
            w = QWidget()
            w.setLayout(row)
            self.form.addRow(w)
            self.pickers[key] = btn

        v.addLayout(self.form)

        self.preview = QLabel("Preview text  •  Accent", self)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setProperty("accent", True)
        v.addWidget(self.preview)

        self.cmb.currentTextChanged.connect(self._on_preset_changed)
        self.btn_load.clicked.connect(self._on_load)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_saveas.clicked.connect(self._on_saveas)
        self.btn_export.clicked.connect(self._on_export)
        self.btn_import.clicked.connect(self._on_import)

        self._palette = load_palette(self.cmb.currentText())
        self._refresh_preview()

    def _on_preset_changed(self, name: str):
        self._palette = load_palette(name)
        self._refresh_preview()

    def _pick_color(self, key: str):
        from PySide6.QtGui import QColor

        cur = self._palette.get(key, "#000000")
        col = QColorDialog.getColor(QColor(cur), self, f"Pick {key}")
        if col.isValid():
            self._palette[key] = col.name()
            self._refresh_preview()

    def _refresh_preview(self):
        # quick live style via apply_theme: write a temporary theme name
        try:
            tmpname = "_live_custom"
            save_custom_theme(self._palette, tmpname)
            apply_theme(
                (
                    self.parent()
                    .window()
                    .windowHandle()
                    .screen()
                    .virtualSiblings()[0]
                    .context()
                    .screen()
                    .virtualSiblings()
                    if False
                    else self.parent() or self
                ),
                tmpname,
            )
        except Exception:
            try:
                apply_theme(self, "_live_custom")
            except Exception:
                pass

    def _on_load(self):
        self._palette = load_palette(self.cmb.currentText())
        self._refresh_preview()

    def _on_apply(self):
        app = self.parent()
        try:
            while app and not hasattr(app, "setStyleSheet"):
                app = app.parent()
        except Exception:
            pass
        if app:
            save_custom_theme(self._palette, "custom")
            apply_theme(app, "custom")

    def _on_saveas(self):
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(
            self, "Save Preset", "Preset name:", text="my_theme"
        )
        if ok and name.strip():
            save_custom_theme(self._palette, name.strip())

    def _on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Theme", "theme.json", "JSON (*.json)"
        )
        if path:
            export_theme(path, name=self.cmb.currentText())

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Theme", "", "JSON (*.json)")
        if path:
            names = import_theme(path)
            if names:
                self.cmb.clear()
                self.cmb.addItems(list_themes())
                self.cmb.setCurrentText(names[0])
                self._palette = load_palette(names[0])
                self._refresh_preview()
