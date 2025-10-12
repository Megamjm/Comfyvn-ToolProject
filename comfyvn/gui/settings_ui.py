# comfyvn/gui/settings_ui.py
# ⚙️ Settings Panel — v0.4-dev (Phase 3.3-H)
# Integrates StatusWidget + SystemMonitor for live connectivity indicators
# [🎨 GUI Code Production Chat]

import json
import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QHBoxLayout, QPushButton, QCheckBox,
    QSpinBox, QLabel, QFileDialog, QGroupBox, QVBoxLayout, QComboBox, QFrame
)
import requests

# Internal imports
from comfyvn.gui.widgets.status_widget import StatusWidget
from comfyvn.core.system_monitor import SystemMonitor


class SettingsUI(QWidget):
    """Configuration panel for ComfyVN integrations, render, and paths."""

    settings_changed = Signal(dict)
    log_message = Signal(str)

    def __init__(self, config_path: str = "comfyvn.json"):
        super().__init__()
        self._config_path = Path(config_path)
        self.monitor = SystemMonitor()
        self._build_ui()
        self._wire_monitor()

    # ===============================================================
    # UI Setup
    # ===============================================================
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        # -------------------- Paths --------------------
        path_box = QGroupBox("Project Paths")
        path_form = QFormLayout()

        self.project_root = QLineEdit("")
        btn_browse_root = QPushButton("Browse…")
        btn_browse_root.clicked.connect(self._browse_project)
        wrap = QHBoxLayout(); wrap.addWidget(self.project_root); wrap.addWidget(btn_browse_root)
        path_form.addRow("Project Root", wrap)

        self.assets_dir = QLineEdit("assets/")
        btn_assets = QPushButton("Browse…")
        btn_assets.clicked.connect(lambda: self._browse_dir(self.assets_dir))
        wrap2 = QHBoxLayout(); wrap2.addWidget(self.assets_dir); wrap2.addWidget(btn_assets)
        path_form.addRow("Assets Directory", wrap2)

        self.renpy_project = QLineEdit("renpy_project/")
        btn_renpy = QPushButton("Browse…")
        btn_renpy.clicked.connect(lambda: self._browse_dir(self.renpy_project))
        wrap3 = QHBoxLayout(); wrap3.addWidget(self.renpy_project); wrap3.addWidget(btn_renpy)
        path_form.addRow("Ren’Py Project", wrap3)

        path_box.setLayout(path_form)
        root.addWidget(path_box)

        # -------------------- Integrations --------------------
        integ_box = QGroupBox("Integrations")
        integ_form = QFormLayout()

        self.comfy_host = QLineEdit("http://127.0.0.1:8188")
        self.comfy_workflow = QLineEdit("workflows/sprite_gen.json")
        self.lmstudio_host = QLineEdit("http://127.0.0.1:1234/v1")
        self.sillytavern_host = QLineEdit("http://127.0.0.1:8000")
        self.sillytavern_ext = QLineEdit("sillytavern_extensions.js")

        integ_form.addRow("ComfyUI Host", self.comfy_host)
        integ_form.addRow("ComfyUI Workflow", self.comfy_workflow)
        integ_form.addRow("LM Studio Base URL", self.lmstudio_host)
        integ_form.addRow("SillyTavern Host", self.sillytavern_host)
        integ_form.addRow("SillyTavern Extension", self.sillytavern_ext)

        # Test / Save Buttons
        test_row = QHBoxLayout()
        self.btn_test = QPushButton("🔍 Test Endpoints")
        self.btn_test.clicked.connect(self._test_endpoints)
        self.btn_save = QPushButton("💾 Save Settings")
        self.btn_save.clicked.connect(self._emit_settings_changed)
        test_row.addWidget(self.btn_test)
        test_row.addWidget(self.btn_save)
        integ_form.addRow("", test_row)

        integ_box.setLayout(integ_form)
        root.addWidget(integ_box)

        # -------------------- Audio / FX Toggles --------------------
        audio_box = QGroupBox("Audio / Effects")
        audio_layout = QFormLayout()
        self.toggle_music = QCheckBox("Enable Music")
        self.toggle_sfx = QCheckBox("Enable SFX")
        self.toggle_voice = QCheckBox("Enable Voice")
        self.toggle_fx = QCheckBox("Enable Visual Effects")
        for w in [self.toggle_music, self.toggle_sfx, self.toggle_voice, self.toggle_fx]:
            audio_layout.addRow(w)
        audio_box.setLayout(audio_layout)
        root.addWidget(audio_box)

        # -------------------- Render Options --------------------
        render_box = QGroupBox("Render Options")
        render_form = QFormLayout()
        self.quality = QComboBox()
        self.quality.addItems(["Draft", "Standard", "High", "Ultra"])
        self.width = QSpinBox(); self.width.setRange(256, 4096); self.width.setValue(768)
        self.height = QSpinBox(); self.height.setRange(256, 4096); self.height.setValue(1024)
        self.npc_background_mode = QCheckBox("NPC Background Mode")
        self.full_dump = QCheckBox("Full Character Dump Mode")
        render_form.addRow("Quality Preset", self.quality)
        render_form.addRow("Width", self.width)
        render_form.addRow("Height", self.height)
        render_form.addRow(self.npc_background_mode)
        render_form.addRow(self.full_dump)
        render_box.setLayout(render_form)
        root.addWidget(render_box)

        # -------------------- Status Footer --------------------
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        root.addWidget(divider)

        self.status_widget = StatusWidget(self)
        self.status_widget.add_indicator("server", "Server Core")
        self.status_widget.add_indicator("lmstudio", "LM Studio")
        self.status_widget.add_indicator("sillytavern", "SillyTavern")
        root.addWidget(self.status_widget)

        root.addStretch(1)

        # Auto-save triggers
        for w in [
            self.project_root, self.assets_dir, self.renpy_project,
            self.comfy_host, self.comfy_workflow, self.lmstudio_host,
            self.sillytavern_host, self.sillytavern_ext,
            self.quality, self.width, self.height,
            self.toggle_music, self.toggle_sfx, self.toggle_voice, self.toggle_fx,
            self.npc_background_mode, self.full_dump
        ]:
            if hasattr(w, "editingFinished"):
                w.editingFinished.connect(self._emit_settings_changed)
            elif hasattr(w, "stateChanged"):
                w.stateChanged.connect(self._emit_settings_changed)
            elif hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(self._emit_settings_changed)
            elif hasattr(w, "valueChanged"):
                w.valueChanged.connect(self._emit_settings_changed)

    # ===============================================================
    # System Monitor Integration
    # ===============================================================
    def _wire_monitor(self):
        """Attach SystemMonitor live update callback."""
        self.monitor.on_update(self._on_monitor_update)
        self.monitor.start(interval=8)

    def _on_monitor_update(self, data: dict):
        """Update footer indicators."""
        srv = (data.get("server") or {}).get("state", "offline")
        lm = (data.get("lmstudio") or {}).get("state", "offline")
        st = (data.get("sillytavern") or {}).get("state", "offline")

        self.status_widget.update_indicator("server", srv, f"Server Core: {srv}")
        self.status_widget.update_indicator("lmstudio", lm, f"LM Studio: {lm}")
        self.status_widget.update_indicator("sillytavern", st, f"SillyTavern: {st}")

    # ===============================================================
    # Data Management
    # ===============================================================
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
                "sillytavern_extension": self.sillytavern_ext.text(),
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
        """Load settings into fields."""
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
        self._emit_settings_changed()

    # ===============================================================
    # Endpoint Testing
    # ===============================================================
    @Slot()
    def _test_endpoints(self):
        """Manual endpoint tests with threaded fallback."""
        cfg = self.collect_settings()
        self.log_message.emit("Testing integration endpoints...")

        def _work():
            results = []
            tests = [
                ("Server Core", cfg["integrations"]["comfyui_host"]),
                ("LM Studio", cfg["integrations"]["lmstudio_base_url"]),
                ("SillyTavern", cfg["integrations"]["sillytavern_host"]),
            ]
            for name, url in tests:
                try:
                    r = requests.get(url, timeout=5)
                    results.append(f"{name}: {r.status_code}")
                except Exception as e:
                    results.append(f"{name} FAIL: {e}")
            self.log_message.emit("\n".join(results))

        threading.Thread(target=_work, daemon=True).start()

    # ===============================================================
    # File + Signal Operations
    # ===============================================================
    @Slot()
    def _emit_settings_changed(self):
        cfg = self.collect_settings()
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