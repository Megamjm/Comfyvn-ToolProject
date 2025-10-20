from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/gui/windows/import_center_window.py
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout, QPushButton, QFileDialog, QLabel, QMessageBox
from pathlib import Path
import shutil, zipfile

class ImportCenterWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Center")
        v = QVBoxLayout(self)
        self.tabs = QTabWidget(self); v.addWidget(self.tabs,1)
        self.tabs.addTab(self._tab_generic("VN", "imports/vn"), "Visual Novel")
        self.tabs.addTab(self._tab_generic("Manga", "imports/manga"), "Manga")
        self.tabs.addTab(self._tab_generic("Assets", "imports/assets"), "Assets")

    def _tab_generic(self, label: str, default_dir: str):
        w = QWidget(); f = QFormLayout(w)
        self._src = None; self._dst = Path(default_dir)
        lbl_src = QLabel("—", w); lbl_dst = QLabel(str(self._dst.resolve()), w)
        btn_src = QPushButton(f"Select {label} (.zip / folder)")
        btn_dst = QPushButton("Choose Output Folder")
        btn_go  = QPushButton(f"Import {label}")
        def pick_src():
            fn, _ = QFileDialog.getOpenFileName(self, f"Choose {label} Zip", "", "Zip (*.zip)")
            if fn: self._src = Path(fn); lbl_src.setText(fn)
            else:
                d = QFileDialog.getExistingDirectory(self, f"Choose {label} Folder")
                if d: self._src = Path(d); lbl_src.setText(d)
        def pick_dst():
            d = QFileDialog.getExistingDirectory(self, "Choose Output Folder")
            if d: self._dst = Path(d); lbl_dst.setText(d)
        def do_import():
            try:
                self._extract(self._src, self._dst)
                QMessageBox.information(self, label, "Imported.")
            except Exception as e:
                QMessageBox.critical(self, label, str(e))
        btn_src.clicked.connect(pick_src); btn_dst.clicked.connect(pick_dst); btn_go.clicked.connect(do_import)
        f.addRow("Source:", lbl_src); f.addRow(btn_src)
        f.addRow("Output:", lbl_dst); f.addRow(btn_dst)
        f.addRow(btn_go)
        return w

    def _extract(self, src: Path|None, dst: Path):
        if not src: raise RuntimeError("No source chosen")
        dst.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower()==".zip":
            with zipfile.ZipFile(src,'r') as zf: zf.extractall(dst)
        else:
            for p in Path(src).rglob("*"):
                tp = dst / p.relative_to(src)
                if p.is_dir(): tp.mkdir(parents=True, exist_ok=True)
                else:
                    tp.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, tp)