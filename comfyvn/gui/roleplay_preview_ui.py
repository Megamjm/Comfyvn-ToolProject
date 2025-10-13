# comfyvn/gui/roleplay_preview_ui.py
# 🎭 Roleplay Scene Preview Player — Phase 3.7
# [ComfyVN_Architect | Roleplay Import & Collaboration Chat]

import os, json, threading, time, requests
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QFileDialog,
    QTextEdit,
    QMessageBox,
    QSlider,
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QTimer, Slot
from comfyvn.gui.widgets.progress_overlay import ProgressOverlay


class RoleplayPreviewUI(QWidget):
    """Lightweight VN-style player for imported/edited roleplay scenes."""

    def __init__(self, parent=None, data_root="./data/roleplay/converted"):
        super().__init__(parent)
        self.data_root = data_root
        self.scene = None
        self.lines = []
        self.index = 0
        self.playing = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        title = QLabel("<b>Scene Preview Player</b>", alignment=Qt.AlignCenter)
        layout.addWidget(title)

        # --- background + text ---
        self.bg_label = QLabel(alignment=Qt.AlignCenter)
        self.bg_label.setMinimumHeight(240)
        layout.addWidget(self.bg_label)

        self.speaker_label = QLabel("", alignment=Qt.AlignCenter)
        self.speaker_label.setStyleSheet("font-weight:bold; font-size:14px;")
        layout.addWidget(self.speaker_label)

        self.text_box = QTextEdit(readOnly=True)
        layout.addWidget(self.text_box)

        # --- controls ---
        row = QHBoxLayout()
        self.btn_load = QPushButton("Load Scene")
        self.btn_play = QPushButton("▶ Play")
        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_next = QPushButton("⏭ Next")
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(1, 5)
        self.speed_slider.setValue(3)
        row.addWidget(self.btn_load)
        row.addWidget(self.btn_play)
        row.addWidget(self.btn_pause)
        row.addWidget(self.btn_next)
        row.addWidget(QLabel("Speed"))
        row.addWidget(self.speed_slider)
        layout.addLayout(row)

        # --- render controls ---
        render_row = QHBoxLayout()
        self.btn_render = QPushButton("🎨 Render Line")
        self.btn_batch = QPushButton("🧩 Batch Render Scene")
        render_row.addWidget(self.btn_render)
        render_row.addWidget(self.btn_batch)
        layout.addLayout(render_row)

        # --- status label ---
        self.status = QLabel("", alignment=Qt.AlignCenter)
        layout.addWidget(self.status)

        # --- overlay for progress ---
        self.overlay = ProgressOverlay(self, "Processing…")
        self.overlay.hide()

        # --- connections ---
        self.btn_load.clicked.connect(self._load_scene)
        self.btn_play.clicked.connect(self._play)
        self.btn_pause.clicked.connect(self._pause)
        self.btn_next.clicked.connect(self._advance)
        self.btn_render.clicked.connect(self._render_line)
        self.btn_batch.clicked.connect(self._batch_render)

    # ---------------- scene handling ----------------
    @Slot()
    def _load_scene(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Scene JSON", self.data_root, "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.scene = json.load(f)
            self.lines = self.scene.get("lines", [])
            self.index = 0
            self.status.setText(
                f"Loaded: {os.path.basename(path)} ({len(self.lines)} lines)"
            )
            self._render_current()
        except Exception as e:
            QMessageBox.critical(self, "Load Error", str(e))

    def _render_current(self):
        if not self.lines:
            return
        if self.index >= len(self.lines):
            self._pause()
            self.status.setText("End of scene.")
            return

        line = self.lines[self.index]
        speaker = line.get("speaker", "")
        text = line.get("text", "")
        emotion = line.get("emotion", "neutral")

        # try to load sprite or background
        sprite_path = f"./assets/characters/{speaker.lower()}.png"
        bg_path = f"./assets/backgrounds/default.png"

        if os.path.exists(bg_path):
            self.bg_label.setPixmap(
                QPixmap(bg_path).scaledToWidth(640, Qt.SmoothTransformation)
            )
        if os.path.exists(sprite_path):
            # Show sprite instead of background if available
            self.bg_label.setPixmap(
                QPixmap(sprite_path).scaledToWidth(320, Qt.SmoothTransformation)
            )

        self.speaker_label.setText(f"{speaker} ({emotion})")
        self.text_box.setPlainText(text)

    @Slot()
    def _advance(self):
        if not self.lines:
            return
        self.index += 1
        if self.index < len(self.lines):
            self._render_current()
        else:
            self._pause()
            self.status.setText("End of scene.")

    @Slot()
    def _play(self):
        if not self.lines:
            return
        self.playing = True
        interval = 6000 // self.speed_slider.value()  # ms
        self.timer.start(interval)
        self.status.setText("Playing...")

    @Slot()
    def _pause(self):
        self.playing = False
        self.timer.stop()
        self.status.setText("Paused.")

    # ---------------- line rendering ----------------
    @Slot()
    def _render_line(self):
        if not self.lines or self.index >= len(self.lines):
            QMessageBox.information(self, "Render", "No active line.")
            return

        line = self.lines[self.index]
        self.overlay.set_text("Rendering current line...")
        self.overlay.start()

        def worker():
            try:
                r = requests.post(
                    "http://127.0.0.1:8001/roleplay/render_line",
                    json={
                        "scene_id": self.scene.get("scene_id", "adhoc"),
                        "line": line,
                        "model": "anime-style-lora",
                        "endpoint": "http://127.0.0.1:8188",
                    },
                    timeout=120,
                )
                if r.status_code == 200:
                    res = r.json()
                    QTimer.singleShot(
                        0,
                        lambda: self.status.setText(
                            f"Rendered {line.get('speaker')} ✅"
                        ),
                    )
                    os.makedirs("./data/roleplay/renders", exist_ok=True)
                    with open(
                        "./data/roleplay/renders/last_prompt.txt", "w", encoding="utf-8"
                    ) as f:
                        f.write(res.get("prompt", ""))
                else:
                    QTimer.singleShot(
                        0, lambda: self.status.setText(f"Render Error {r.status_code}")
                    )
            except Exception as e:
                QTimer.singleShot(0, lambda: self.status.setText(f"Render Error: {e}"))
            finally:
                QTimer.singleShot(0, self.overlay.stop)

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- batch rendering ----------------
    @Slot()
    def _batch_render(self):
        if not self.scene or not self.lines:
            QMessageBox.information(self, "Batch", "Load a scene first.")
            return

        self.overlay.set_text("Sending batch render request...")
        self.overlay.start()

        def worker():
            try:
                r = requests.post(
                    "http://127.0.0.1:8001/roleplay/render_scene",
                    json={
                        "scene_id": self.scene.get("scene_id", "adhoc"),
                        "lines": self.lines,
                        "model": "anime-style-lora",
                        "endpoint": "http://127.0.0.1:8188",
                    },
                    timeout=600,
                )
                if r.status_code == 200:
                    data = r.json()
                    msg = f"Rendered {data.get('rendered', 0)} lines.\nLog: {data.get('log')}"
                    QTimer.singleShot(0, lambda: self.status.setText(msg))
                else:
                    QTimer.singleShot(
                        0,
                        lambda: self.status.setText(f"Error {r.status_code}: {r.text}"),
                    )
            except Exception as e:
                QTimer.singleShot(
                    0, lambda: self.status.setText(f"Batch render error: {e}")
                )
            finally:
                QTimer.singleShot(2000, self.overlay.stop)

        threading.Thread(target=worker, daemon=True).start()
