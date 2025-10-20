from PySide6.QtGui import QAction
# comfyvn/gui/panels/gpu_manager_view.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QHBoxLayout, QPushButton, QMessageBox
from comfyvn.core.gpu_manager import list_providers, set_priority_order, activate
from comfyvn.core.notifier import notifier

class GPUManagerView(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GPU Manager")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Providers (top = highest priority; double-click to toggle active)"))
        self.list = QListWidget(); lay.addWidget(self.list, 1)
        hb = QHBoxLayout(); lay.addLayout(hb)
        self.btn_up = QPushButton("Move Up"); self.btn_down = QPushButton("Move Down")
        self.btn_save = QPushButton("Save Order")
        hb.addWidget(self.btn_up); hb.addWidget(self.btn_down); hb.addStretch(1); hb.addWidget(self.btn_save)
        self.list.itemDoubleClicked.connect(self.toggle_active)
        self.btn_up.clicked.connect(lambda: self.move(-1))
        self.btn_down.clicked.connect(lambda: self.move(+1))
        self.btn_save.clicked.connect(self.save_order)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for name, meta in list_providers():
            label = f"{'🟢' if meta.get('active') else '⚪'}  {name}  [{meta.get('service')}]  gpu={meta.get('gpu')}"
            self.list.addItem(label)

    def _current_index(self):
        row = self.list.currentRow()
        return row if row >=0 else None

    def move(self, delta):
        row = self._current_index()
        if row is None: return
        new = max(0, min(self.list.count()-1, row+delta))
        if new == row: return
        it = self.list.takeItem(row)
        self.list.insertItem(new, it)
        self.list.setCurrentRow(new)

    def save_order(self):
        names = []
        for i in range(self.list.count()):
            t = self.list.item(i).text()
            name = t.split()[1]
            names.append(name)
        set_priority_order(names)
        notifier.toast("info", "GPU priority saved")

    def toggle_active(self, item):
        name = item.text().split()[1]
        is_active = item.text().startswith("🟢")
        activate(name, not is_active)
        self.refresh()
        notifier.toast("info", f"{name} {'activated' if not is_active else 'deactivated'}")