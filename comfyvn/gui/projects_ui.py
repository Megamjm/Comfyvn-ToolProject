from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout, QLineEdit, QMessageBox
from comfyvn.gui.services.server_bridge import ServerBridge

class ProjectsUI(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.bridge=ServerBridge()
        self.list = QListWidget()
        form = QHBoxLayout()
        self.name = QLineEdit("demo")
        b_add = QPushButton("Create"); b_add.clicked.connect(self.create)
        b_sel = QPushButton("Select"); b_sel.clicked.connect(self.select)
        form.addWidget(QLabel("Name")); form.addWidget(self.name); form.addWidget(b_add); form.addWidget(b_sel)
        lay = QVBoxLayout(self); lay.addWidget(QLabel("Projects")); lay.addLayout(form); lay.addWidget(self.list)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for p in self.bridge.projects():
            it = QListWidgetItem(f"{p.get('name')}  scenes={p.get('scenes')} chars={p.get('characters')} {'[current]' if p.get('current') else ''}")
            self.list.addItem(it)

    def create(self):
        out = self.bridge.projects_create(self.name.text().strip() or "proj")
        if out.get("ok"): QMessageBox.information(self, "Project", "Created")
        self.refresh()

    def select(self):
        it = self.list.currentItem(); 
        if not it: return
        name = it.text().split()[0]
        self.bridge.projects_select(name); self.refresh()