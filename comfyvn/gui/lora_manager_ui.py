from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/gui/lora_manager_ui.py
# 🧬 LoRA Manager UI — v1.0 (Phase 3)
# Chat Source: 🧬 9. LoRA System Production Chat

import os, threading
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from comfyvn.assets.lora_manager import LoRAManager
from comfyvn.comfyui.scripts.train_lora import LoRATrainerWithSignals


class LoRAManagerUI(QWidget):
    """Interactive panel for managing and training LoRAs."""

    def __init__(self, parent=None, task_manager=None):
        super().__init__(parent)
        self.manager = LoRAManager()
        self.trainer = LoRATrainerWithSignals()
        self.task_manager = task_manager

        # --- Connect trainer signals if task manager is available ---
        if self.task_manager:
            s = self.trainer.signals
            s.job_started.connect(self.task_manager.add_job)
            s.job_updated.connect(self.task_manager.update_job_status)
            s.job_finished.connect(
                lambda jid: self.task_manager.update_job_status(jid, "completed")
            )

        # --- UI Layout ---
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)

        # --- Search Bar ---
        search_layout = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search local LoRAs…")
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.search_loras)
        search_layout.addWidget(self.search_box)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)

        # --- Results List ---
        self.results = QListWidget()
        layout.addWidget(self.results)

        # --- Train Section ---
        train_layout = QVBoxLayout()
        train_layout.addWidget(QLabel("🧠 Train New LoRA"))

        form = QHBoxLayout()
        self.dataset_btn = QPushButton("Select Dataset")
        self.dataset_btn.clicked.connect(self.select_dataset)
        self.output_box = QLineEdit()
        self.output_box.setPlaceholderText("Output Name")
        self.start_train_btn = QPushButton("Start Training")
        self.start_train_btn.clicked.connect(self.start_training)
        form.addWidget(self.dataset_btn)
        form.addWidget(self.output_box)
        form.addWidget(self.start_train_btn)
        train_layout.addLayout(form)

        # --- Logs ---
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addLayout(train_layout)
        layout.addWidget(QLabel("Training Log"))
        layout.addWidget(self.log_view)

        # --- Poll Timer ---
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_logs)
        self.timer.start(5000)

        self.current_job = None
        self.current_dataset = None

    # --------------------------
    # 🔍 Search LoRAs
    # --------------------------
    def search_loras(self):
        query = self.search_box.text().strip()
        results = self.manager.search(query)
        self.results.clear()
        for r in results:
            item = QListWidgetItem(f"{r['name']} — {r['meta'].get('size_kb', '?')} KB")
            self.results.addItem(item)

    # --------------------------
    # 🧠 Train LoRA
    # --------------------------
    def select_dataset(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Dataset Folder")
        if folder:
            self.current_dataset = folder
            QMessageBox.information(
                self, "Dataset Selected", f"Using dataset:\n{folder}"
            )

    def start_training(self):
        if not self.current_dataset or not self.output_box.text().strip():
            QMessageBox.warning(
                self, "Missing Data", "Please select dataset and output name."
            )
            return

        output_name = self.output_box.text().strip()
        base_model = "./models/base_model.safetensors"  # configurable
        self.trainer.start_job(self.current_dataset, output_name, base_model)
        self.current_job = output_name
        QMessageBox.information(
            self, "Training Started", f"Job '{output_name}' started!"
        )

    # --------------------------
    # 📜 Logs
    # --------------------------
    def refresh_logs(self):
        if not self.current_job:
            return
        logs = self.trainer.tail_log(self.current_job)
        self.log_view.setPlainText("".join(logs))