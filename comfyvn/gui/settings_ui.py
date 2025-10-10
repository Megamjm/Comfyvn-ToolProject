# comfyvn/gui/settings_ui.py
# Settings panel with integration endpoints, audio toggles, render options, paths
# Non-blocking endpoint tests, JSON load/save helpers
# [🎨 GUI Code Production Chat]

import json
import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QHBoxLayout, QPushButton, QCheckBox,
    QSpinBox, QLabel, QFileDialog, QGroupBox, QVBoxLayout, QComboBox
)
import requests


class SettingsUI(QWidget):
    settings_changed = Signal(dict)
    log_message = Signal(str)

    def __init__(self, config_path: str = "comfyvn.json"):
        super().__init__()
        self._config_path = Path(config_path)
        self._build_ui()

    # -------------------- UI --------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Paths
        path_box = QGroupBox("Paths")
        path_form = QFormLayout()
        self.project_root = QLineEdit("")
        btn_browse_root = QPushButton("Browse...")
        btn_browse_root.clicked.connect(self._browse_project)

        wrap = QHBoxLayout()
        wrap.addWidget(self.project_root)
        wrap.addWidget(btn_browse_root)
        path_form.addRow("Project Root", wrap)

        self.assets_dir = QLineEdit("assets/")
        btn_assets = QPushButton("Browse...")
        btn_assets.clicked.connect(lambda: self._browse_dir(self.assets_dir))
        wrap2 = QHBoxLayout()
        wrap2.addWidget(self.assets_dir)
        wrap2.addWidget(btn_assets)
        path_form.addRow("Assets Dir", wrap2)

        self.renpy_project = QLineEdit("renpy_project/")
        btn_renpy = QPushButton("Browse...")
        btn_renpy.clicked.connect(lambda: self._browse_dir(self.renpy_project))
        wrap3 = QHBoxLayout()
        wrap3.addWidget(self.renpy_project)
        wrap3.addWidget(btn_renpy)
        path_form.addRow("Ren'Py Project", wrap3)

        path_box.setLayout(path_form)
        root.addWidget(path_box)

        # Integrations
        integ_box = QGroupBox("Integrations")
        integ_form = QFormLayout()

        self.comfy_host = QLineEdit("http://127.0.0.1:8188")
        self.comfy_workflow = QLineEdit("workflows/sprite_gen.json")
        self.lmstudio_host = QLineEdit("http://127.0.0.1:1234/v1")
        self.sillytavern_host = QLineEdit("http://127.0.0.1:8000")
        self.sillytavern_ext = QLineEdit("sillytavern_extensions.js")

        integ_form.addRow("ComfyUI Host", self.comfy_host)
        integ_form.addRow("ComfyUI Workflow", self.comfy_workflow)
        integ_form.addRow("LM Studio (OpenAI-compat) Base URL", self.lmstudio_host)
        integ_form.addRow("SillyTavern Host", self.sillytavern_host)
        integ_form.addRow("SillyTavern Extension", self.sillytavern_ext)

        # Buttons for testing
        test_row = QHBoxLayout()
        self.btn_test = QPushButton("Test Endpoints")
        self.btn_test.clicked.connect(self.test_endpoints)
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.clicked.connect(self._emit_settings_changed)
        test_row.addWidget(self.btn_test)
        test_row.addWidget(self.btn_save)
        integ_form.addRow("", test_row)

        integ_box.setLayout(integ_form)
        root.addWidget(integ_box)

        # Audio / FX Toggles
        audio_box = QGroupBox("Audio / Effects Toggles")
        audio_layout = QFormLayout()
        self.toggle_music = QCheckBox("Enable Music")
        self.toggle_sfx = QCheckBox("Enable SFX")
        self.toggle_voice = QCheckBox("Enable Voice/Speech")
        self.toggle_fx = QCheckBox("Enable Visual Effects (shakes/filters)")
        self.toggle_music.setChecked(True)
        self.toggle_sfx.setChecked(True)
        self.toggle_voice.setChecked(False)
        self.toggle_fx.setChecked(True)
        audio_layout.addRow(self.toggle_music)
        audio_layout.addRow(self.toggle_sfx)
        audio_layout.addRow(self.toggle_voice)
        audio_layout.addRow(self.toggle_fx)
        audio_box.setLayout(audio_layout)
        root.addWidget(audio_box)

        # Render Options
        render_box = QGroupBox("Render Options")
        render_form = QFormLayout()
        self.quality = QComboBox()
        self.quality.addItems(["Draft", "Standard", "High", "Ultra"])
        self.width = QSpinBox(); self.width.setRange(256, 4096); self.width.setValue(768)
        self.height = QSpinBox(); self.height.setRange(256, 4096); self.height.setValue(1024)
        self.npc_background_mode = QCheckBox("NPC Background Mode (no faces/details)")
        self.full_dump = QCheckBox("Full Character Dump Mode")

        render_form.addRow("Quality Preset", self.quality)
        render_form.addRow("Width", self.width)
        render_form.addRow("Height", self.height)
        render_form.addRow(self.npc_background_mode)
        render_form.addRow(self.full_dump)
        render_box.setLayout(render_form)
        root.addWidget(render_box)

        # Auto-save on change
        for w in [self.project_root, self.assets_dir, self.renpy_project,
                  self.comfy_host, self.comfy_workflow, self.lmstudio_host,
                  self.sillytavern_host, self.sillytavern_ext,
                  self.quality, self.width, self.height,
                  self.toggle_music, self.toggle_sfx, self.toggle_voice, self.toggle_fx,
                  self.npc_background_mode, self.full_dump]:
            if hasattr(w, "editingFinished"):
                w.editingFinished.connect(self._emit_settings_changed)
            elif hasattr(w, "stateChanged"):
                w.stateChanged.connect(self._emit_settings_changed)
            elif hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(self._emit_settings_changed)
            elif hasattr(w, "valueChanged"):
                w.valueChanged.connect(self._emit_settings_changed)

        root.addStretch(1)

    # -------------------- Collect / Apply --------------------

    def collect_settings(self) -> dict:
        return {
            "paths": {
                "project_root": self.project_root.text(),
                "assets_dir": self.assets_dir.text(),
                "renpy_project": self.renpy_project.text(),
            },
            "integrations": {
                "comfyui_host": self.comfy_host.text(),
                "comfyui_workflow": self.comfy_workflow.text(),
                "lmstudio_base_url": self.lmstudio_host.text(),
                "sillytavern_host": self.sillytavern_host.text(),
                "sillytavern_extension": self.sillytavern_ext.text(),  # reference: sillytavern_extensions.js
            },
            "audio": {
                "music": self.toggle_music.isChecked(),
                "sfx": self.toggle_sfx.isChecked(),
                "voice": self.toggle_voice.isChecked(),
                "fx": self.toggle_fx.isChecked(),
            },
            "render": {
                "quality": self.quality.currentText(),
                "width": self.width.value(),
                "height": self.height.value(),
                "npc_background_mode": self.npc_background_mode.isChecked(),
                "full_character_dump": self.full_dump.isChecked(),
            }
        }

    def apply_settings(self, cfg: dict):
        p = cfg.get("paths", {})
        i = cfg.get("integrations", {})
        a = cfg.get("audio", {})
        r = cfg.get("render", {})

        self.project_root.setText(p.get("project_root", self.project_root.text()))
        self.assets_dir.setText(p.get("assets_dir", self.assets_dir.text()))
        self.renpy_project.setText(p.get("renpy_project", self.renpy_project.text()))

        self.comfy_host.setText(i.get("comfyui_host", self.comfy_host.text()))
        self.comfy_workflow.setText(i.get("comfyui_workflow", self.comfy_workflow.text()))
        self.lmstudio_host.setText(i.get("lmstudio_base_url", self.lmstudio_host.text()))
        self.sillytavern_host.setText(i.get("sillytavern_host", self.sillytavern_host.text()))
        self.sillytavern_ext.setText(i.get("sillytavern_extension", self.sillytavern_ext.text()))

        self.toggle_music.setChecked(a.get("music", True))
        self.toggle_sfx.setChecked(a.get("sfx", True))
        self.toggle_voice.setChecked(a.get("voice", False))
        self.toggle_fx.setChecked(a.get("fx", True))

        q = r.get("quality", self.quality.currentText())
        idx = self.quality.findText(q)
        if idx >= 0:
            self.quality.setCurrentIndex(idx)
        self.width.setValue(r.get("width", self.width.value()))
        self.height.setValue(r.get("height", self.height.value()))
        self.npc_background_mode.setChecked(r.get("npc_background_mode", False))
        self.full_dump.setChecked(r.get("full_character_dump", False))

        # notify others
        self._emit_settings_changed()

    # -------------------- Actions --------------------

    @Slot()
    def test_endpoints(self):
        cfg = self.collect_settings()
        self.log_message.emit("Testing endpoints...")
        def _work():
            results = []
            # ComfyUI /prompt endpoint
            try:
                r = requests.get(cfg["integrations"]["comfyui_host"])
                results.append(f"ComfyUI Host OK: {r.status_code}")
            except Exception as e:
                results.append(f"ComfyUI Host FAIL: {e}")

            # LM Studio models list (OpenAI compatible: /models may not exist; try a harmless POST to /chat/completions)
            try:
                test_url = cfg["integrations"]["lmstudio_base_url"].rstrip("/") + "/models"
                rq = requests.get(test_url)
                results.append(f"LM Studio (/models) {rq.status_code if rq is not None else '??'}")
            except Exception as e:
                results.append(f"LM Studio check FAIL: {e}")

            # SillyTavern (assume a health endpoint or static root)
            try:
                r2 = requests.get(cfg["integrations"]["sillytavern_host"])
                results.append(f"SillyTavern Host OK: {r2.status_code}")
            except Exception as e:
                results.append(f"SillyTavern Host FAIL: {e}")

            self.log_message.emit("\n".join(results))

        threading.Thread(target=_work, daemon=True).start()

    @Slot()
    def _emit_settings_changed(self):
        cfg = self.collect_settings()
        # Auto-save to comfyvn.json (reference: comfyvn.json)
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            self.log_message.emit(f"Settings persisted to {self._config_path}")
        except Exception as e:
            self.log_message.emit(f"Failed to write {self._config_path}: {e}")
        self.settings_changed.emit(cfg)

    def _browse_project(self):
        d = QFileDialog.getExistingDirectory(self, "Select Project Root")
        if d:
            self.project_root.setText(d)
            self._emit_settings_changed()

    def _browse_dir(self, line: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "Select Directory")
        if d:
            line.setText(d)
            self._emit_settings_changed()
