# comfyvn/gui/playground_ui.py
# 🎨 Playground – Scene Composer / LLM Bridge / Server Planner
# [🎨 GUI Code Production Chat | Phase 3.2 Sync]

import json
import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot, QRectF, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QListWidget, QListWidgetItem, QPushButton, QTextEdit, QSplitter, QLabel,
    QFileDialog, QMessageBox
)
import requests

from comfyvn.gui.components.dialog_helpers import info, error
from comfyvn.gui.components.progress_overlay import ProgressOverlay
from comfyvn.gui.server_bridge import ServerBridge


class PlaygroundUI(QWidget):
    """Interactive scene playground and LM Studio / Server Core bridge."""

    request_log = Signal(str)
    request_settings = Signal(object)
    request_settings_changed = Signal(dict)

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.layers_list = QListWidget()
        self.prompt_box = QTextEdit()

        # --- Buttons ---
        self.btn_plan = QPushButton("Plan Scene (Server)")
        self.btn_apply = QPushButton("Apply Prompt to Scene (LM Studio)")
        self.btn_add_layer = QPushButton("Add Layer (Image)")
        self.btn_export = QPushButton("Export Composite")
        self.btn_send_silly = QPushButton("Send to SillyTavern (JSON)")

        self.overlay = ProgressOverlay(self, "Working …")
        self.overlay.hide()
        self.bridge = ServerBridge()

        self.current_layers = []
        self._build_ui()
        self._wire_events()

    # ------------------------------------------------------------
    # UI Layout
    # ------------------------------------------------------------
    def _build_ui(self):
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel("Scene Preview"))
        left.addWidget(self.view)

        right = QVBoxLayout()
        right.addWidget(QLabel("Layers"))
        right.addWidget(self.layers_list)
        right.addWidget(QLabel("Prompt (describe changes)"))
        right.addWidget(self.prompt_box)

        row = QHBoxLayout()
        row.addWidget(self.btn_plan)
        row.addWidget(self.btn_apply)
        right.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(self.btn_add_layer)
        row2.addWidget(self.btn_export)
        right.addLayout(row2)

        right.addWidget(self.btn_send_silly)

        splitter = QSplitter(Qt.Horizontal)
        wl, wr = QWidget(), QWidget()
        wl.setLayout(left); wr.setLayout(right)
        splitter.addWidget(wl); splitter.addWidget(wr)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

    # ------------------------------------------------------------
    # Events
    # ------------------------------------------------------------
    def _wire_events(self):
        self.btn_add_layer.clicked.connect(self._add_layer)
        self.btn_export.clicked.connect(self._export_composite)
        self.btn_apply.clicked.connect(self._apply_prompt)
        self.btn_plan.clicked.connect(self._plan_scene)
        self.btn_send_silly.clicked.connect(self._send_to_sillytavern)

    # ------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------
    def on_settings_changed(self, cfg: dict):
        pass  # reserved for width/height bindings

    # ------------------------------------------------------------
    # Layers
    # ------------------------------------------------------------
    @Slot()
    def _add_layer(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Add Image Layer", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
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

    # ------------------------------------------------------------
    # Server Core Integration
    # ------------------------------------------------------------
    @Slot()
    def _plan_scene(self):
        """Send current scene JSON to /scene/plan on Server Core."""
        scene_data = self._current_scene_json()
        self.overlay.set_text("Planning scene on server …")
        self.overlay.start()

        def _done(resp):
            self.overlay.stop()
            if "error" in resp:
                error(self, "Scene Plan Failed", resp["error"])
            else:
                info(self, "Scene Plan Complete", json.dumps(resp, indent=2))
                self.request_log.emit(f"Scene planned: {json.dumps(resp, indent=2)}")

        self.bridge.send_scene_plan(scene_data, _done)

    # ------------------------------------------------------------
    # LM Studio Integration
    # ------------------------------------------------------------
    @Slot()
    def _apply_prompt(self):
        """Apply prompt-based edits using LM Studio local LLM."""
        cfg = self._read_settings()
        if not cfg:
            QMessageBox.warning(self, "No Settings", "Settings not available.")
            return
        base = cfg["integrations"]["lmstudio_base_url"].rstrip("/")
        url = base + "/chat/completions"
        scene_desc = self._current_scene_json()
        user_prompt = self.prompt_box.toPlainText().strip() or "Center the main character."
        sys_prompt = (
            "You are a scene layout assistant for a visual novel engine. "
            "Given scene JSON (layers=ordered top-down), return an updated JSON "
            "with numeric positions, scale, opacity, and simple fx tags. "
            "Only output valid JSON."
        )
        body = {
            "model": "gpt-4o-mini-uncensored-or-any-local",
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
                self.request_log.emit(f"Scene updated by LLM: {json.dumps(updated, indent=2)}")
            except Exception as e:
                self.request_log.emit(f"LM Studio request failed: {e}")

        threading.Thread(target=_work, daemon=True).start()

    # ------------------------------------------------------------
    # SillyTavern Bridge
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------
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

    def _read_settings(self) -> Optional[dict]:
        parent = self.parent()
        while parent and not hasattr(parent, "collect_settings"):
            parent = parent.parent()
        if parent and hasattr(parent, "collect_settings"):
            return parent.collect_settings()
        return None
                