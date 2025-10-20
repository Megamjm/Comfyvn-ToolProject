from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHBoxLayout, QMessageBox, QComboBox
import requests

class GPUMgrPanel(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)

        title = QLabel("GPU Manager")
        title.setStyleSheet("font-size:16px; font-weight:600;")
        v.addWidget(title)

        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["ID","Name","Util %","Mem (MB)","Temp Â°C"])
        v.addWidget(self.tbl)

        row = QHBoxLayout()
        self.cmb_policy = QComboBox()
        self.cmb_policy.addItems(["auto","cpu","gpu:0","gpu:1","gpu:best"])
        row.addWidget(QLabel("Policy:"))
        row.addWidget(self.cmb_policy)
        btn_apply = QPushButton("Apply"); btn_apply.clicked.connect(self.apply_policy)
        row.addWidget(btn_apply)
        v.addLayout(row)

        btn_refresh = QPushButton("Refresh"); btn_refresh.clicked.connect(self.refresh)
        v.addWidget(btn_refresh)

        self.refresh()

    def refresh(self):
        base = "http://127.0.0.1:8001"
        self.tbl.setRowCount(0)
        try:
            r = requests.get(f"{base}/system/metrics", timeout=1.5)
            if not r.ok: raise RuntimeError("metrics not ok")
            m = r.json()
            gpus = m.get("gpus") or []
            for g in gpus:
                rix = self.tbl.rowCount(); self.tbl.insertRow(rix)
                for c, val in enumerate([g.get("id","-"), g.get("name","-"), g.get("util","-"), f"{g.get('mem_used','-')}/{g.get('mem_total','-')}", g.get("temp_c","-")]):
                    self.tbl.setItem(rix, c, QTableWidgetItem(str(val)))
        except Exception:
            pass

    def apply_policy(self):
        base = "http://127.0.0.1:8001"
        policy = self.cmb_policy.currentText()
        try:
            r = requests.post(f"{base}/gpu/policy", json={"policy": policy}, timeout=2.5)
            if r.ok:
                QMessageBox.information(self, "GPU Manager", f"Applied: {r.json().get('applied')}")
            else:
                raise RuntimeError(r.text)
        except Exception as e:
            QMessageBox.critical(self, "GPU Manager", f"Failed to set policy: {e}")