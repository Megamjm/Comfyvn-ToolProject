# comfyvn/gui/community_assets_browser.py
# Community Assets Browser Dock (Safe Mode + Legal + Update Check)
# ComfyVN_Architect (Asset Sprite Research Branch)

import os, json, requests
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QTextEdit, QHBoxLayout, QMessageBox, QLineEdit, QCheckBox
)
from PySide6.QtCore import Qt

class CommunityAssetsBrowser(QDockWidget):
    def __init__(self, server_url="http://127.0.0.1:8000", parent=None):
        super().__init__("Community Assets Browser", parent)
        self.server_url = server_url

        main = QWidget()
        self.setWidget(main)
        self.v = QVBoxLayout(main)

        title = QLabel("Community Assets Registry")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight:bold; font-size:16px;")
        self.v.addWidget(title)

        # Safe Mode
        sm_row = QHBoxLayout()
        self.chk_safe = QCheckBox("Safe Mode (verified only)")
        sm_row.addWidget(self.chk_safe)
        self.btn_apply_safe = QPushButton("Apply")
        sm_row.addWidget(self.btn_apply_safe)
        self.v.addLayout(sm_row)

        self.list_assets = QListWidget()
        self.v.addWidget(self.list_assets)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 Refresh from Server")
        self.btn_update_github = QPushButton("🌐 Update from GitHub")
        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_update_github)
        self.v.addLayout(btn_row)

        self.v.addWidget(QLabel("Add Custom Asset (⚠️ Not Verified in Safe Mode):"))
        self.name_input = QLineEdit(); self.name_input.setPlaceholderText("Asset Name")
        self.url_input = QLineEdit(); self.url_input.setPlaceholderText("Source URL or local path")
        self.btn_add = QPushButton("➕ Add Custom")
        self.v.addWidget(self.name_input)
        self.v.addWidget(self.url_input)
        self.v.addWidget(self.btn_add)

        self.legal_box = QTextEdit(); self.legal_box.setReadOnly(True); self.legal_box.setMinimumHeight(120)
        self.v.addWidget(QLabel("Legal Disclaimer:"))
        self.v.addWidget(self.legal_box)

        # signals
        self.btn_refresh.clicked.connect(self.load_assets)
        self.btn_update_github.clicked.connect(self.update_github)
        self.btn_add.clicked.connect(self.add_custom)
        self.btn_apply_safe.clicked.connect(self.apply_safe_mode)

        # init
        self.load_legal()
        self.sync_safe_mode_checkbox()
        self.load_assets()
        self.check_for_updates()

    def sync_safe_mode_checkbox(self):
        try:
            r = requests.get(f"{self.server_url}/safe_mode", timeout=8).json()
            self.chk_safe.setChecked(bool(r.get("safe_mode", False)))
        except Exception:
            pass

    def apply_safe_mode(self):
        try:
            payload = {"enabled": self.chk_safe.isChecked()}
            r = requests.post(f"{self.server_url}/safe_mode", json=payload, timeout=8)
            if r.status_code == 200:
                QMessageBox.information(self, "Safe Mode", "Setting applied.")
                self.load_assets()
            else:
                QMessageBox.warning(self, "Safe Mode", f"Failed: {r.text}")
        except Exception as e:
            QMessageBox.critical(self, "Safe Mode", str(e))

    def load_assets(self):
        try:
            r = requests.get(f"{self.server_url}/assets/community", timeout=10).json()
            self.list_assets.clear()
            verified = r.get("assets", {}).get("verified", [])
            user = r.get("assets", {}).get("user", [])
            for a in verified:
                item = QListWidgetItem(f"✅ {a['name']} ({a['type']}) – {a.get('license','N/A')}")
                item.setToolTip(f"{a.get('description','')}\nSource: {a.get('source_url','')}")
                self.list_assets.addItem(item)
            for a in user:
                item = QListWidgetItem(f"⚠️ {a.get('name','(User Asset)')} — {a.get('license','Unknown')}")
                item.setToolTip(f"{a.get('description','')}\nSource: {a.get('source_url','')}")
                item.setForeground(Qt.darkYellow)
                self.list_assets.addItem(item)
        except Exception as e:
            QMessageBox.critical(self, "Assets", f"Failed to load assets:\n{e}")

    def update_github(self):
        try:
            r = requests.get(f"{self.server_url}/assets/update_registry", timeout=10)
            if r.status_code == 200:
                QMessageBox.information(self, "Registry", "Updated from GitHub.")
                self.load_assets()
            else:
                QMessageBox.warning(self, "Registry", f"Update failed: {r.text}")
        except Exception as e:
            QMessageBox.critical(self, "Registry", str(e))

    def add_custom(self):
        if self.chk_safe.isChecked():
            QMessageBox.warning(self, "Safe Mode", "Disable Safe Mode to add unverified assets.")
            return
        name = self.name_input.text().strip()
        url = self.url_input.text().strip()
        if not name or not url:
            QMessageBox.warning(self, "Invalid", "Provide both Name and URL/path.")
            return
        payload = {"name": name, "source_url": url, "type": "user", "license": "Unknown"}
        try:
            r = requests.post(f"{self.server_url}/assets/register", json=payload, timeout=10)
            if r.status_code == 200:
                QMessageBox.information(self, "Added", r.json().get("message","Added."))
                self.load_assets()
            else:
                QMessageBox.warning(self, "Add", f"Failed: {r.text}")
        except Exception as e:
            QMessageBox.critical(self, "Add Error", str(e))

    def load_legal(self):
        try:
            r = requests.get(f"{self.server_url}/legal/disclaimer", timeout=8)
            if r.status_code == 200:
                self.legal_box.setPlainText(r.json().get("text",""))
        except Exception as e:
            self.legal_box.setPlainText(f"Error loading disclaimer: {e}")

    def check_for_updates(self):
        try:
            r = requests.get(f"{self.server_url}/assets/check_updates", timeout=6).json()
            if r.get("update_available"):
                note = QPushButton("⚠️ Registry update available — Click to apply")
                note.setStyleSheet("background-color:#ffebcc;color:#333;border:1px solid #ffcc00;")
                note.clicked.connect(self.update_github)
                self.v.addWidget(note)
        except Exception:
            pass
# ------------------------------------------------------------------