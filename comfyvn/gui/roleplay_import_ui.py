from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/gui/roleplay_import_ui.py
# 🤝 Roleplay Import Panel — Phase 3.5 LLM Sampler
# [ComfyVN_Architect | Roleplay Import & Collaboration Chat]

import os, json, threading
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QHBoxLayout,
    QFormLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import Qt
from comfyvn.gui.server_bridge import ServerBridge


class RoleplayImportUI(QWidget):
    def __init__(self, parent=None, api_base="http://127.0.0.1:8001"):
        super().__init__(parent)
        self.api_base = api_base.rstrip("/")
        self.server = ServerBridge(base_url=self.api_base)
        self.current_scene = None
        self.character_meta = {}

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        layout.addWidget(QLabel("<b>Roleplay Importer</b>"))

        form = QFormLayout()
        self.path_edit = QLineEdit()
        b = QPushButton("Browse")
        b.clicked.connect(self._browse_file)
        r = QHBoxLayout()
        r.addWidget(self.path_edit)
        r.addWidget(b)
        form.addRow("Chat Log File", r)

        self.world_edit = QLineEdit("unlinked")
        self.source_edit = QLineEdit("manual")
        form.addRow("World Tag", self.world_edit)
        form.addRow("Source", self.source_edit)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.btn_upload = QPushButton("Import Log")
        self.btn_finalize = QPushButton("Finalize Scene")
        self.btn_finalize.setEnabled(False)
        self.btn_llm = QPushButton("Generate LLM Sample")
        self.btn_llm.setEnabled(False)
        self.btn_savecorr = QPushButton("Save Corrections")
        self.btn_savecorr.setEnabled(False)
        btn_row.addWidget(self.btn_upload)
        btn_row.addWidget(self.btn_finalize)
        btn_row.addWidget(self.btn_llm)
        btn_row.addWidget(self.btn_savecorr)
        layout.addLayout(btn_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Line #", "Speaker", "Text"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.table)

        layout.addWidget(QLabel("<b>Character Descriptions (optional)</b>"))
        self.desc_box = QTextEdit()
        self.desc_box.setPlaceholderText(
            "Name: short description\nAlex: shy artist\nMira: energetic fox girl with sarcasm"
        )
        layout.addWidget(self.desc_box)

        # LLM endpoint config
        cfg = QFormLayout()
        self.endpoint_edit = QLineEdit("http://127.0.0.1:1234/v1")
        self.model_edit = QLineEdit("gpt-4o-mini")
        self.key_edit = QLineEdit("")  # blank for LM Studio
        cfg.addRow("LLM Endpoint", self.endpoint_edit)
        cfg.addRow("Model", self.model_edit)
        cfg.addRow("API Key (optional)", self.key_edit)
        layout.addLayout(cfg)

        layout.addWidget(QLabel("<b>LLM Result</b>"))
        self.llm_out = QTextEdit()
        self.llm_out.setReadOnly(True)
        layout.addWidget(self.llm_out)

        self.btn_upload.clicked.connect(self._upload_file)
        self.btn_finalize.clicked.connect(self._finalize)
        self.btn_llm.clicked.connect(self._generate_llm_sample)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Chat Log", "", "Text/JSON (*.txt *.json)"
        )
        if path:
            self.path_edit.setText(path)

    def _upload_file(self):
        path = self.path_edit.text().strip()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Error", "File not found.")
            return
        self.btn_upload.setEnabled(False)

        def worker():
            import requests

            try:
                with open(path, "rb") as f:
                    r = requests.post(
                        f"{self.api_base}/roleplay/import",
                        files={"file": f},
                        data={
                            "world_tag": self.world_edit.text().strip(),
                            "source": self.source_edit.text().strip(),
                        },
                        timeout=120,
                    )
                if r.status_code == 200:
                    res = r.json()
                    self.current_scene = res.get("scene_id")
                    self._load_preview(self.current_scene)
                else:
                    self.llm_out.setPlainText(f"Error {r.status_code}: {r.text}")
            except Exception as e:
                self.llm_out.setPlainText(str(e))
            finally:
                self.btn_upload.setEnabled(True)

        threading.Thread(target=worker, daemon=True).start()

    def _load_preview(self, scene_id):
        import requests

        try:
            r = requests.get(f"{self.api_base}/roleplay/preview/{scene_id}", timeout=30)
            r.raise_for_status()
            data = r.json()
            lines = data.get("lines", [])[:50]
            self.table.setRowCount(len(lines))
            for i, line in enumerate(lines):
                self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                self.table.setItem(i, 1, QTableWidgetItem(line.get("speaker", "")))
                self.table.setItem(i, 2, QTableWidgetItem(line.get("text", "")))
            self.btn_finalize.setEnabled(True)
            self.btn_savecorr.setEnabled(True)
            self.btn_llm.setEnabled(True)
        except Exception as e:
            self.llm_out.setPlainText(str(e))

    def _finalize(self):
        if not self.current_scene:
            QMessageBox.information(self, "Finalize", "No scene imported.")
            return
        rows = self.table.rowCount()
        self.character_meta = {}
        corrected = []
        for i in range(rows):
            spk = self.table.item(i, 1).text() if self.table.item(i, 1) else ""
            txt = self.table.item(i, 2).text() if self.table.item(i, 2) else ""
            corrected.append({"speaker": spk, "text": txt})
        meta_text = self.desc_box.toPlainText().strip()
        if meta_text:
            for line in meta_text.splitlines():
                if ":" in line:
                    n, d = line.split(":", 1)
                    self.character_meta[n.strip()] = d.strip()
        os.makedirs("./data/roleplay/metadata", exist_ok=True)
        meta_path = f"./data/roleplay/metadata/{self.current_scene}_characters.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(self.character_meta, f, indent=2)
        QMessageBox.information(self, "Finalize", f"Saved metadata:\n{meta_path}")

    def _generate_llm_sample(self):
        if not self.current_scene:
            QMessageBox.information(self, "LLM", "Import a scene first.")
            return
        rows = self.table.rowCount()
        excerpt = []
        for i in range(rows):
            spk = self.table.item(i, 1).text() if self.table.item(i, 1) else ""
            txt = self.table.item(i, 2).text() if self.table.item(i, 2) else ""
            if spk or txt:
                excerpt.append({"speaker": spk, "text": txt})

        # rebuild character_meta from box each call to reflect edits
        character_meta = {}
        meta_text = self.desc_box.toPlainText().strip()
        if meta_text:
            for line in meta_text.splitlines():
                if ":" in line:
                    n, d = line.split(":", 1)
                    character_meta[n.strip()] = d.strip()

        endpoint = self.endpoint_edit.text().strip()
        model = self.model_edit.text().strip()
        api_key = self.key_edit.text().strip()

        self.btn_llm.setEnabled(False)
        self.btn_llm.setText("Generating…")

        def worker():
            import requests

            try:
                r = requests.post(
                    f"{self.api_base}/roleplay/sample_llm",
                    json={
                        "scene_id": self.current_scene,
                        "excerpt": excerpt,
                        "character_meta": character_meta,
                        "instructions": "Summarize each character's voice and propose 3 style tags.",
                        "endpoint": endpoint,
                        "model": model,
                        "api_key": api_key,
                    },
                    timeout=180,
                )
                if r.status_code == 200:
                    res = r.json()
                    self.llm_out.setPlainText(res.get("llm_output", "<no content>"))
                else:
                    self.llm_out.setPlainText(f"Error {r.status_code}: {r.text}")
            except Exception as e:
                self.llm_out.setPlainText(str(e))
            finally:
                self.btn_llm.setEnabled(True)
                self.btn_llm.setText("Generate LLM Sample")

        threading.Thread(target=worker, daemon=True).start()

    def _save_corrections(self):
        if not self.current_scene:
            QMessageBox.information(self, "Save", "Import a scene first.")
            return
        rows = self.table.rowCount()
        lines = []
        for i in range(rows):
            spk = self.table.item(i, 1).text() if self.table.item(i, 1) else ""
            txt = self.table.item(i, 2).text() if self.table.item(i, 2) else ""
            if spk or txt:
                lines.append({"speaker": spk, "text": txt})

        # build character meta from desc_box
        meta = {}
        txt = self.desc_box.toPlainText().strip()
        if txt:
            for l in txt.splitlines():
                if ":" in l:
                    n, d = l.split(":", 1)
                    meta[n.strip()] = d.strip()

        def worker():
            import requests

            try:
                r = requests.post(
                    f"{self.api_base}/roleplay/apply_corrections",
                    json={
                        "scene_id": self.current_scene,
                        "lines": lines,
                        "character_meta": meta,
                    },
                    timeout=60,
                )
                if r.status_code == 200:
                    self.llm_out.setPlainText(f"Corrections saved:\n{r.text}")
                else:
                    self.llm_out.setPlainText(f"Error {r.status_code}: {r.text}")
            except Exception as e:
                self.llm_out.setPlainText(str(e))

        threading.Thread(target=worker, daemon=True).start()