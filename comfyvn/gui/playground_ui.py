# comfyvn/gui/playground_ui.py
# 🎭 Playground UI — v0.4-dev (Phase 3.3-H)
# Scene preview + prompt editing + SillyTavern / LM Studio links
# Integrates SystemMonitor + StatusWidget Framework
# [🎨 GUI Code Production Chat]

import json
import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot, QRectF
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QListWidget, QListWidgetItem, QPushButton, QTextEdit, QSplitter, QLabel, QFileDialog, QMessageBox, QFrame
)
import requests

# Internal imports
from comfyvn.gui.components.status_widget import StatusWidget
from comfyvn.modules.system_monitor import SystemMonitor


class PlaygroundUI(QWidget):
    """Interactive scene composer with LLM-driven layout editing."""

    request_log = Signal(str)
    request_settings = Signal(object)
    request_settings_changed = Signal(dict)

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.layers_list = QListWidget()
        self.prompt_box = QTextEdit()
        self.btn_apply = QPushButton("Apply Prompt to Scene")
        self.btn_add_layer = QPushButton("Add Layer (Image)")
        self.btn_export = QPushButton("Export Composite")
        self.btn_send_silly = QPushButton("Send to SillyTavern (JSON)")
        self.current_layers = []
        self._build_ui()
        self._wire_events()

        # System Monitor + Status Widget
        self.monitor = SystemMonitor()
        self.monitor.on_update(self._on_monitor_update)
        self.monitor.start(interval=6)

    # -------------------- UI --------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Horizontal)

        # ---- Left: Scene Preview ----
        left = QVBoxLayout()
        left.addWidget(QLabel("🎨 Scene Preview"))
        left.addWidget(self.view)

        # ---- Right: Controls ----
        right = QVBoxLayout()
        right.addWidget(QLabel("Layers"))
        right.addWidget(self.layers_list)
        right.addWidget(QLabel("Prompt (describe changes)"))
        right.addWidget(self.prompt_box)

        row = QHBoxLayout()
        row.addWidget(self.btn_apply)
        row.addWidget(self.btn_add_layer)
        row.addWidget(self.btn_export)
        right.addLayout(row)
        right.addWidget(self.btn_send_silly)

        w_left = QWidget(); w_left.setLayout(left)
        w_right = QWidget(); w_right.setLayout(right)
        splitter.addWidget(w_left)
        splitter.addWidget(w_right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        layout.addWidget(divider)

        # ---- StatusWidget Footer ----
        self.status_widget = StatusWidget(self)
        self.status_widget.add_indicator("lmstudio", "LM Studio Link")
        self.status_widget.add_indicator("sillytavern", "SillyTavern Link")
        self.status_widget.add_indicator("cpu", "CPU Usage")
        self.status_widget.add_indicator("ram", "RAM Usage")
        layout.addWidget(self.status_widget)

    def _wire_events(self):
        self.btn_add_layer.clicked.connect(self._add_layer)
        self.btn_export.clicked.connect(self._export_composite)
        self.btn_apply.clicked.connect(self._apply_prompt)
        self.btn_send_silly.clicked.connect(self._send_to_sillytavern)

    # -------------------- System Monitor Update --------------------

    def _on_monitor_update(self, data: dict):
        """Reflect system and integration state in the footer."""
        lm = (data.get("lmstudio") or {}).get("state", "offline")
        st = (data.get("sillytavern") or {}).get("state", "offline")
        cpu = data.get("cpu_percent", 0)
        ram = data.get("ram_percent", 0)

        self.status_widget.update_indicator("lmstudio", lm, f"LM Studio: {lm}")
        self.status_widget.update_indicator("sillytavern", st, f"SillyTavern: {st}")

        def load_to_state(v):
            if v >= 90:
                return "error"
            if v >= 70:
                return "busy"
            if v <= 5:
                return "idle"
            return "online"

        self.status_widget.update_indicator("cpu", load_to_state(cpu), f"CPU: {cpu:.0f}%")
        self.status_widget.update_indicator("ram", load_to_state(ram), f"RAM: {ram:.0f}%")

    # -------------------- Layers --------------------

    @Slot()
    def _add_layer(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add Image Layer", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        pix = QPixmap(path)
        if pix.isNull():
            QMessageBox.warning(self, "Invalid", "Could not load image.")
            return
        item = QGraphicsPixmapItem(pix)
        self.scene.addItem(item)
        self.scene.setSceneRect(QRectF(pix.rect()))
        self.current_layers.append({"path": path, "item": item})
        li = QListWidgetItem(Path(path).name)
        li.setData(Qt.UserRole, path)
        self.layers_list.addItem(li)
        self.request_log.emit(f"Layer added: {path}")

    @Slot()
    def _export_composite(self):
        out, _ = QFileDialog.getSaveFileName(self, "Export Composite", "composite.png", "PNG (*.png)")
        if not out:
            return
        img = self._grab_scene()
        if img:
            img.save(out, "PNG")
            self.request_log.emit(f"Composite exported: {out}")

    def _grab_scene(self):
        if self.scene.items():
            rect = self.scene.sceneRect()
            from PySide6.QtGui import QImage, QPainter
            img = QImage(int(rect.width()), int(rect.height()), QImage.Format_ARGB32_Premultiplied)
            img.fill(0)
            painter = QPainter(img)
            self.scene.render(painter)
            painter.end()
            return img
        return None

    # -------------------- Prompt Application --------------------

    @Slot()
    def _apply_prompt(self):
        """Use LM Studio to apply prompt-based edits to the scene JSON."""
        cfg = self._read_settings()
        if not cfg:
            QMessageBox.warning(self, "No Settings", "Settings not available.")
            return

        base = cfg["integrations"]["lmstudio_base_url"].rstrip("/")
        url = base + "/chat/completions"

        scene_desc = self._current_scene_json()
        user_prompt = self.prompt_box.toPlainText().strip() or "Center the main character, add slight vignette."
        sys_prompt = (
            "You are a scene layout assistant for a visual novel engine. "
            "Given scene JSON (layers=ordered top-down), return updated JSON with numeric positions, scale, opacity, and fx tags. "
            "Only output valid JSON."
        )

        body = {
            "model": "gpt-4o-mini-or-local",
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": json.dumps({"scene": scene_desc, "instruction": user_prompt})}
            ],
            "temperature": 0.3,
        }

        def _work():
            try:
                r = requests.post(url, json=body, timeout=60)
                if r.status_code != 200:
                    self.request_log.emit(f"LM Studio error: {r.status_code} - {r.text}")
                    return
                data = r.json()
                out = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                try:
                    updated = json.loads(out)
                except Exception:
                    import re
                    m = re.search(r"\{.*\}", out, re.DOTALL)
                    updated = json.loads(m.group(0)) if m else {}
                self.request_log.emit("Scene updated by LLM. (Apply-to-view pending mapping)")
            except Exception as e:
                self.request_log.emit(f"LM Studio request failed: {e}")

        threading.Thread(target=_work, daemon=True).start()

    def _current_scene_json(self) -> dict:
        layers = []
        for entry in self.current_layers:
            p = entry["path"]
            item = entry["item"]
            pos = item.pos()
            layers.append({
                "path": p,
                "x": pos.x(),
                "y": pos.y(),
                "scale": 1.0,
                "opacity": 1.0,
                "fx": []
            })
        return {"layers": layers, "canvas": {"w": self.view.width(), "h": self.view.height()}}

    # -------------------- SillyTavern Bridge --------------------

    @Slot()
    def _send_to_sillytavern(self):
        """Send current scene JSON to SillyTavern via local extension."""
        cfg = self._read_settings()
        if not cfg:
            QMessageBox.warning(self, "No Settings", "Settings not available.")
            return
        host = cfg["integrations"]["sillytavern_host"].rstrip("/")
        url = host + "/comfyvn/scene"

        payload = {
            "scene": self._current_scene_json(),
            "audio": cfg.get("audio", {}),
            "render": cfg.get("render", {}),
        }

        def _work():
            try:
                r = requests.post(url, json=payload, timeout=30)
                self.request_log.emit(f"SillyTavern reply: {r.status_code} - {r.text[:200]}...")
            except Exception as e:
                self.request_log.emit(f"SillyTavern bridge failed: {e}")

        threading.Thread(target=_work, daemon=True).start()

    # -------------------- Helpers --------------------

    def _read_settings(self) -> Optional[dict]:
        parent = self.parent()
        while parent and not hasattr(parent, "collect_settings"):
            parent = parent.parent()
        if parent and hasattr(parent, "collect_settings"):
            return parent.collect_settings()
        return None
# -------------------- System Monitor Module --------------------