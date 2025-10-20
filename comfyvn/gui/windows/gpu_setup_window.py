from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/gui/windows/gpu_setup_window.py
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QListWidget, QListWidgetItem, QTextBrowser)
from PySide6.QtCore import Qt
from comfyvn.gui.services.server_bridge import ServerBridge
import json, os
from pathlib import Path

PROVIDERS = [
    {
        "name": "RunPod",
        "url": "https://www.runpod.io/",
        "notes": "Pay-per-minute pods, good for burst rendering. Create API key, pick a template with CUDA.",
        "config_keys": ["RUNPOD_API_KEY"]
    },
    {
        "name": "Lambda Labs",
        "url": "https://lambdalabs.com/service/gpu-cloud",
        "notes": "Hourly instances. Good A10/A100 availability.",
        "config_keys": ["LAMBDA_API_KEY"]
    },
    {
        "name": "Vast.ai",
        "url": "https://vast.ai/",
        "notes": "Marketplace with variable pricing. Check bandwidth + storage.",
        "config_keys": ["VAST_API_KEY"]
    },
    {
        "name": "Google Colab",
        "url": "https://colab.research.google.com/",
        "notes": "Free/Pro tiers, session-based. Requires notebook runner.",
        "config_keys": []
    }
]

class GPUSetupWindow(QDialog):
    def __init__(self, parent=None, base="http://127.0.0.1:8001"):
        super().__init__(parent)
        self.setWindowTitle("GPU Setup")
        self.resize(760, 520)
        self.bridge = ServerBridge(base=base)
        self._load_local_cfg()

        self.list = QListWidget()
        for p in PROVIDERS:
            QListWidgetItem(p["name"], self.list)

        self.info = QTextBrowser()
        self.api_key_edit = QLineEdit()
        self.remote_list_edit = QLineEdit()
        self.remote_list_edit.setPlaceholderText("Comma-separated remote endpoints … e.g. http://host1:8001,http://host2:8001")

        self.btn_save = QPushButton("Save")
        self.btn_ping = QPushButton("Ping Remotes")
        self.btn_close = QPushButton("Close")

        left = QVBoxLayout()
        left.addWidget(QLabel("Providers")); left.addWidget(self.list)

        right = QVBoxLayout()
        right.addWidget(QLabel("Provider Info"))
        right.addWidget(self.info)
        right.addWidget(QLabel("API Key (if applicable)"))
        right.addWidget(self.api_key_edit)
        right.addWidget(QLabel("Remote GPU Endpoints"))
        right.addWidget(self.remote_list_edit)

        btns = QHBoxLayout()
        btns.addWidget(self.btn_save); btns.addWidget(self.btn_ping); btns.addStretch(1); btns.addWidget(self.btn_close)
        right.addLayout(btns)

        root = QHBoxLayout(self)
        root.addLayout(left, 1); root.addLayout(right, 2)

        self.list.currentRowChanged.connect(self._on_select)
        self.btn_close.clicked.connect(self.close)
        self.btn_save.clicked.connect(self._save_all)
        self.btn_ping.clicked.connect(self._ping_all)

        self.list.setCurrentRow(0)

    # ---- config I/O (local, decoupled from server) ----
    def _cfg_path(self) -> Path:
        p = Path("data/settings_gpu.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _load_local_cfg(self):
        try:
            data = json.loads(self._cfg_path().read_text(encoding="utf-8"))
        except Exception:
            data = {}
        self._cfg = data

    def _save_local_cfg(self):
        try:
            self._cfg_path().write_text(json.dumps(self._cfg, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    # ---- UI handlers ----
    def _on_select(self, idx: int):
        p = PROVIDERS[idx]
        html = f"<h3>{p['name']}</h3><p><a href='{p['url']}'>{p['url']}</a></p><p>{p['notes']}</p>"
        if p["config_keys"]:
            html += "<p><b>Config keys:</b> " + ", ".join(p["config_keys"]) + "</p>"
        self.info.setHtml(html)
        # load remembered key
        keyname = (p["config_keys"][0] if p["config_keys"] else None)
        self.api_key_edit.setText(self._cfg.get(keyname, "") if keyname else "")

        # load endpoints
        self.remote_list_edit.setText(self._cfg.get("REMOTE_GPU_LIST", ""))

    def _save_all(self):
        idx = self.list.currentRow()
        p = PROVIDERS[idx]
        keyname = (p["config_keys"][0] if p["config_keys"] else None)
        if keyname:
            self._cfg[keyname] = self.api_key_edit.text().strip()
        self._cfg["REMOTE_GPU_LIST"] = self.remote_list_edit.text().strip()
        ok = self._save_local_cfg()
        # best-effort server push if available
        _ = self.bridge.set("REMOTE_GPU_LIST", self._cfg.get("REMOTE_GPU_LIST",""))
        self.setWindowTitle("GPU Setup (saved)" if ok else "GPU Setup (save failed)")

    def _ping_all(self):
        raw = self.remote_list_edit.text().strip()
        if not raw:
            self.info.append("<p><i>No remotes configured.</i></p>")
            return
        hosts = [h.strip() for h in raw.split(",") if h.strip()]
        self.info.append("<p><b>Pinging remotes…</b></p>")
        for h in hosts:
            alive = self.bridge.get_json(f"{h}/health", default=None) is not None
            self.info.append(f"<p>{h}: {'🟢 OK' if alive else '🔴 Unreachable'}</p>")