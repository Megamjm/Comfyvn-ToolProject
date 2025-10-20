from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout, QLineEdit, QMessageBox
from comfyvn.gui.server_bridge import ServerBridge

SCOPES = ["jobs.write","artifacts.write","assets.write","content.write","scheduler.write","plugins.write","tokens.admin","projects.write"]

class TokensUI(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.bridge=ServerBridge()
        self.list = QListWidget()
        form = QHBoxLayout()
        self.name = QLineEdit("dev")
        self.scopes = QLineEdit(",".join(SCOPES[:2]))
        b_add = QPushButton("Create"); b_add.clicked.connect(self.create)
        b_del = QPushButton("Revoke"); b_del.clicked.connect(self.revoke)
        form.addWidget(QLabel("Name")); form.addWidget(self.name); form.addWidget(QLabel("Scopes(csv)")); form.addWidget(self.scopes); form.addWidget(b_add); form.addWidget(b_del)
        lay = QVBoxLayout(self); lay.addWidget(QLabel("User Tokens")); lay.addLayout(form); lay.addWidget(self.list)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for t in self.bridge.tokens_list():
            it = QListWidgetItem(f"{t.get('id')}  {t.get('name')}  scopes={','.join(t.get('scopes',[]))}")
            self.list.addItem(it)

    def create(self):
        scopes = [s.strip() for s in self.scopes.text().split(",") if s.strip()]
        out = self.bridge.tokens_create(self.name.text().strip() or "token", scopes)
        QMessageBox.information(self, "Token", f"Created: {out.get('token',{}).get('id')}"); self.refresh()

    def revoke(self):
        it = self.list.currentItem()
        if not it: return
        tid = it.text().split()[0]
        self.bridge.tokens_revoke(tid); self.refresh()