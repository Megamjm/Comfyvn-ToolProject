from PySide6.QtGui import QAction
# comfyvn/gui/panels/template_manager_view.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QPushButton, QHBoxLayout, QMessageBox, QInputDialog
from comfyvn.core.core import workspace_templates

class TemplateManagerView(QWidget):
    def __init__(self, apply_cb=None):
        super().__init__()
        self.setWindowTitle("Template Manager")
        self.apply_cb = apply_cb
        lay = QVBoxLayout(self)
        self.list = QListWidget(); lay.addWidget(self.list, 1)
        hb = QHBoxLayout(); lay.addLayout(hb)
        self.btn_apply = QPushButton("Apply"); hb.addWidget(self.btn_apply)
        self.btn_save  = QPushButton("Save As…"); hb.addWidget(self.btn_save)
        self.btn_reload= QPushButton("Reload"); hb.addWidget(self.btn_reload)
        self.btn_apply.clicked.connect(self.apply)
        self.btn_save.clicked.connect(self.save_as)
        self.btn_reload.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for name in workspace_templates.list_templates():
            self.list.addItem(name)

    def cur(self):
        it = self.list.currentItem()
        return it.text() if it else None

    def apply(self):
        n = self.cur(); 
        if not n: QMessageBox.information(self,"Templates","Pick one"); return
        data = workspace_templates.load_template(n)
        if self.apply_cb: self.apply_cb(data)

    def save_as(self):
        n, ok = QInputDialog.getText(self,"Save As","Template Name:")
        if not (ok and n): return
        # minimal save: geometry only
        workspace_templates.save_template(n, {"open_panels":[],"geometry":None})
        self.refresh()