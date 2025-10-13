# comfyvn/gui/playground_window.py
# 🧪 Playground Window — with ComfyUI WebSocket Hook + Model Selectors
# [ComfyVN_Architect | Playground System Production Chat]  # (synced in: 🧪 8. Playground System Production Chat)

import os, json, requests, threading, asyncio, websockets
from PySide6.QtCore import Qt, Signal, QThread, QSize, Slot
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QSplitter,
    QMessageBox,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QFrame,
    QSizePolicy,
    QComboBox,  # <-- added QComboBox  # (🧪 Playground System Production Chat)
)

from comfyvn.gui.widgets.status_widget import StatusWidget
from comfyvn.gui.server_bridge import ServerBridge


# ------------------------------------------------------------
# 🔌 ComfyUI WebSocket Listener Thread
# ------------------------------------------------------------
class ComfyUIListener(QThread):
    """Background thread that listens to ComfyUI WebSocket for render updates."""

    render_finished = Signal(str)

    def __init__(self, ws_url="ws://127.0.0.1:8188/ws"):
        super().__init__()
        self.ws_url = ws_url
        self._running = True

    async def _listen(self):
        try:
            async with websockets.connect(self.ws_url) as ws:
                while self._running:
                    msg = await ws.recv()
                    if '"render_complete"' in msg or '"finished"' in msg:
                        self.render_finished.emit(msg)
        except Exception as e:
            print(f"[ComfyUIListener] Error: {e}")

    def run(self):
        asyncio.run(self._listen())

    def stop(self):
        self._running = False


# ------------------------------------------------------------
# 🧪 Playground Window
# ------------------------------------------------------------
class PlaygroundWindow(QWidget):
    """Interactive scene editor with real-time preview and LM Studio integration."""

    def __init__(
        self,
        parent=None,
        api_base="http://127.0.0.1:8000",
        comfy_ws="ws://127.0.0.1:8188/ws",
    ):
        super().__init__(parent)
        self.api_base = api_base.rstrip("/")
        self.server = ServerBridge(base_url=self.api_base)
        self.comfy_ws = comfy_ws

        self.setWindowTitle("🧪 Playground — Scene Composer")
        self.resize(1100, 720)

        # --- Layout setup ---
        main_layout = QHBoxLayout(self)
        main_split = QSplitter(Qt.Horizontal)
        left_panel, right_panel = QVBoxLayout(), QVBoxLayout()

        # ------------------------------------------------------------
        # 🧩 Roleplay Scene Categories (Raw / Converted / Ready)
        # ------------------------------------------------------------
        self.raw_box = QComboBox()
        self.converted_box = QComboBox()
        self.ready_box = QComboBox()

        self.refresh_roleplays_btn = QPushButton("🧠 Refresh Roleplays")
        self.refresh_roleplays_btn.clicked.connect(self.load_roleplay_categories)

        roleplay_layout = QVBoxLayout()
        roleplay_layout.addWidget(QLabel("🧩 Roleplay Scene Categories"))
        roleplay_layout.addWidget(QLabel("📝 Raw Logs"))
        roleplay_layout.addWidget(self.raw_box)
        roleplay_layout.addWidget(QLabel("🔧 Converted Scenes"))
        roleplay_layout.addWidget(self.converted_box)
        roleplay_layout.addWidget(QLabel("🎬 Ready Scenes"))
        roleplay_layout.addWidget(self.ready_box)
        roleplay_layout.addWidget(self.refresh_roleplays_btn)

        roleplay_frame = QFrame()
        roleplay_frame.setLayout(roleplay_layout)
        roleplay_frame.setFrameShape(QFrame.StyledPanel)

        left_panel.addWidget(roleplay_frame)

        # --- Roleplay Action Buttons ---
        self.convert_btn = QPushButton("📝 Convert Raw → Converted")
        self.promote_btn = QPushButton("🔼 Promote to Ready")
        self.revert_btn = QPushButton("⏪ Revert to Converted")

        self.convert_btn.clicked.connect(self.convert_selected_raw)
        self.promote_btn.clicked.connect(self.promote_selected_converted)
        self.revert_btn.clicked.connect(self.revert_selected_ready)

        roleplay_layout.addWidget(self.convert_btn)
        roleplay_layout.addWidget(self.promote_btn)
        roleplay_layout.addWidget(self.revert_btn)

        # --- Scene List ---
        self.scene_list = QListWidget()
        self.scene_list.itemClicked.connect(self.load_scene)
        left_panel.addWidget(QLabel("📜 Available Scenes"))
        left_panel.addWidget(self.scene_list)
        btn_reload = QPushButton("🔄 Refresh List")
        btn_reload.clicked.connect(self.refresh_scenes)
        left_panel.addWidget(btn_reload)

        # --- Scene Preview ---
        self.scene_view = QGraphicsView()
        self.scene_scene = QGraphicsScene()
        self.scene_view.setScene(self.scene_scene)

        # --- Model selectors (Checkpoint / LoRA / ControlNet) ---
        # (new)  # (🧪 Playground System Production Chat)
        self.checkpoint_box = QComboBox()
        self.lora_box = QComboBox()
        self.controlnet_box = QComboBox()
        self.refresh_models_btn = QPushButton("🔄 Refresh Models")
        self.refresh_models_btn.clicked.connect(self.load_models)
        self.checkpoint_box.currentTextChanged.connect(self.select_checkpoint)
        self.lora_box.currentTextChanged.connect(self.select_lora)
        self.controlnet_box.currentTextChanged.connect(self.select_controlnet)

        model_bar = QHBoxLayout()
        model_bar.addWidget(QLabel("Model:"))
        model_bar.addWidget(self.checkpoint_box, 1)
        model_bar.addWidget(QLabel("LoRA:"))
        model_bar.addWidget(self.lora_box, 1)
        model_bar.addWidget(QLabel("ControlNet:"))
        model_bar.addWidget(self.controlnet_box, 1)
        model_bar.addWidget(self.refresh_models_btn)
        right_panel.addLayout(model_bar)

        # --- Prompt Editor ---
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText(
            "Describe a change: 'Make it sunset, add rain, Sora smiles.'"
        )

        self.apply_btn = QPushButton("✨ Apply Prompt")
        self.apply_btn.clicked.connect(self.apply_prompt)

        # --- History ---
        self.history_list = QListWidget()

        # --- Status Bar ---
        self.status = StatusWidget()

        # --- Compose right layout ---
        right_panel.addWidget(QLabel("🎨 Scene Preview"))
        right_panel.addWidget(self.scene_view)
        right_panel.addWidget(QLabel("💬 Modify Scene"))
        right_panel.addWidget(self.prompt_input)
        right_panel.addWidget(self.apply_btn)
        right_panel.addWidget(QLabel("🕓 History"))
        right_panel.addWidget(self.history_list)
        right_panel.addWidget(self.status)

        # Frame wrapping
        left_frame, right_frame = QFrame(), QFrame()
        left_frame.setLayout(left_panel)
        right_frame.setLayout(right_panel)
        left_frame.setFrameShape(QFrame.StyledPanel)
        right_frame.setFrameShape(QFrame.StyledPanel)

        main_split.addWidget(left_frame)
        main_split.addWidget(right_frame)
        main_split.setSizes([260, 820])
        main_layout.addWidget(main_split)

        # --- State ---
        self.current_scene_id = None
        self.current_render_path = "./data/renders/"
        os.makedirs(self.current_render_path, exist_ok=True)

        # --- Load initial data ---
        self.refresh_scenes()
        self.load_models()  # (new) populate selectors on start  # (🧪 Playground System Production Chat)

        # --- Start WebSocket listener ---
        self.ws_thread = ComfyUIListener(self.comfy_ws)
        self.ws_thread.render_finished.connect(self.on_render_finished)
        self.ws_thread.start()

        # --- Roleplay Selection System ---
        self.load_roleplay_categories()
        self.connect_roleplay_selectors()

    # ------------------------------------------------------------
    # 🔄 Scene List Management
    # ------------------------------------------------------------
    def refresh_scenes(self):
        self.scene_list.clear()
        scene_dir = "./data/scenes"
        os.makedirs(scene_dir, exist_ok=True)
        for file in os.listdir(scene_dir):
            if file.endswith(".json"):
                self.scene_list.addItem(QListWidgetItem(file.replace(".json", "")))
        self.status.show_status("✅ Scene list refreshed.")

    # ------------------------------------------------------------
    # 🧩 Scene Load / History / Preview
    # ------------------------------------------------------------
    def load_scene(self, item):
        scene_id = item.text()
        self.current_scene_id = scene_id
        self.status.show_status(f"Loading scene {scene_id} ...")

        def task():
            try:
                resp = requests.get(f"{self.api_base}/playground/scene/{scene_id}")
                data = resp.json()
                self.update_preview(data)
                self.load_history(scene_id)
                self.status.show_status(f"✅ Scene '{scene_id}' loaded.")
            except Exception as e:
                self.status.show_status(f"❌ Failed to load: {e}")

        threading.Thread(target=task).start()

    def load_history(self, scene_id):
        self.history_list.clear()
        try:
            r = requests.get(f"{self.api_base}/playground/history/{scene_id}")
            hist = r.json()
            for entry in hist:
                self.history_list.addItem(
                    QListWidgetItem(f"{entry['timestamp']}: {entry['prompt']}")
                )
        except Exception:
            self.history_list.addItem(QListWidgetItem("⚠️ No history found."))

    def update_preview(self, scene):
        """Refresh scene preview image (background or rendered output)."""
        self.scene_scene.clear()
        bg_path = scene.get("background")
        render_meta = scene.get("metadata", {}).get("last_render", {})

        # Try latest render output first
        img_path = None
        if isinstance(render_meta, dict):
            resp_data = render_meta.get("response", {})
            if isinstance(resp_data, dict) and "output" in resp_data:
                img_path = resp_data["output"]

        if not img_path and bg_path:
            img_path = f"./data/assets/{bg_path}"

        if img_path and os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            item = QGraphicsPixmapItem(pixmap)
            self.scene_scene.addItem(item)
            self.scene_view.fitInView(item, Qt.KeepAspectRatio)
        else:
            # Default placeholder
            placeholder = QImage(512, 384, QImage.Format_RGB32)
            placeholder.fill(Qt.gray)
            self.scene_scene.addPixmap(QPixmap.fromImage(placeholder))

    # ------------------------------------------------------------
    # 🧠 Apply Prompt
    # ------------------------------------------------------------
    def apply_prompt(self):
        if not self.current_scene_id:
            QMessageBox.warning(
                self, "No Scene Selected", "Please select a scene first."
            )
            return
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Empty Prompt", "Please enter a prompt.")
            return

        self.status.show_status("🚀 Sending prompt to LM Studio...")

        def task():
            try:
                r = requests.post(
                    f"{self.api_base}/playground/apply/{self.current_scene_id}",
                    json={"prompt": prompt},
                )
                res = r.json()
                if res.get("status") == "ok":
                    self.status.show_status("✅ Scene updated and render triggered.")
                else:
                    self.status.show_status(f"⚠️ Failed: {res.get('result')}")
                self.load_history(self.current_scene_id)
            except Exception as e:
                self.status.show_status(f"❌ Prompt failed: {e}")

        threading.Thread(target=task).start()

    # ------------------------------------------------------------
    # 🧩 Model Selectors — API hooks
    # ------------------------------------------------------------
    # (new)  # (🧪 Playground System Production Chat)
    def load_models(self):
        """Fetch checkpoints, LoRAs, and ControlNets from backend (ComfyUI pass-through)."""
        try:
            ckpts = requests.get(
                f"{self.api_base}/playground/checkpoints", timeout=10
            ).json()
            loras = requests.get(f"{self.api_base}/playground/loras", timeout=10).json()
            cnets = requests.get(
                f"{self.api_base}/playground/controlnets", timeout=10
            ).json()

            def fill(combo: QComboBox, data):
                combo.clear()
                if isinstance(data, list):
                    for name in data:
                        combo.addItem(str(name))
                elif isinstance(data, dict):
                    # Support { "models": ["a", "b"] } or {"name": {...}} shapes
                    if "models" in data and isinstance(data["models"], list):
                        for name in data["models"]:
                            combo.addItem(str(name))
                    else:
                        for k in data.keys():
                            combo.addItem(str(k))

            fill(self.checkpoint_box, ckpts)
            fill(self.lora_box, loras)
            fill(self.controlnet_box, cnets)
            self.status.show_status("✅ Models refreshed.")
        except Exception as e:
            self.status.show_status(f"❌ Failed to refresh models: {e}")

    def select_checkpoint(self, name: str):
        try:
            requests.post(
                f"{self.api_base}/playground/select/checkpoint",
                json={"name": name},
                timeout=10,
            )
            self.status.show_status(f"🧠 Using checkpoint: {name}")
        except Exception as e:
            self.status.show_status(f"❌ Failed to set checkpoint: {e}")

    def select_lora(self, name: str):
        try:
            requests.post(
                f"{self.api_base}/playground/select/loras",
                json={"names": [name]},
                timeout=10,
            )
            self.status.show_status(f"🎨 LoRA selected: {name}")
        except Exception as e:
            self.status.show_status(f"❌ Failed to set LoRA: {e}")

    def select_controlnet(self, name: str):
        try:
            requests.post(
                f"{self.api_base}/playground/select/controlnets",
                json={"names": [name]},
                timeout=10,
            )
            self.status.show_status(f"🧩 ControlNet selected: {name}")
        except Exception as e:
            self.status.show_status(f"❌ Failed to set ControlNet: {e}")

    def load_roleplay_categories(self):
        """Fetch categorized roleplay files from backend."""
        try:
            resp = requests.get(f"{self.api_base}/roleplay/categories", timeout=10)
            data = resp.json()
            self.raw_box.clear()
            self.converted_box.clear()
            self.ready_box.clear()

            for name in data.get("raw", []):
                self.raw_box.addItem(name)
            for name in data.get("converted", []):
                self.converted_box.addItem(name)
            for name in data.get("ready", []):
                self.ready_box.addItem(name)

            self.status.show_status("✅ Roleplay categories loaded.")
        except Exception as e:
            self.status.show_status(f"❌ Failed to load roleplays: {e}")

    def connect_roleplay_selectors(self):
        """Connect dropdowns to load corresponding scenes."""
        self.converted_box.currentTextChanged.connect(self.open_converted_scene)
        self.ready_box.currentTextChanged.connect(self.open_ready_scene)

    def open_converted_scene(self, scene_id):
        """Open converted roleplay scene into Playground."""
        if not scene_id:
            return
        try:
            resp = requests.get(f"{self.api_base}/roleplay/preview/{scene_id}")
            data = resp.json()
            self.update_preview(data)
            self.status.show_status(f"🎬 Loaded converted roleplay: {scene_id}")
        except Exception as e:
            self.status.show_status(f"❌ Failed to open roleplay: {e}")

    def open_ready_scene(self, scene_id):
        """Open ready scene (data/scenes)."""
        if not scene_id:
            return
        try:
            resp = requests.get(f"{self.api_base}/playground/scene/{scene_id}")
            data = resp.json()
            self.update_preview(data)
            self.status.show_status(f"🎬 Loaded ready scene: {scene_id}")
        except Exception as e:
            self.status.show_status(f"❌ Failed to open ready scene: {e}")

    # ------------------------------------------------------------
    # 🖼 ComfyUI Render Event Hook
    # ------------------------------------------------------------
    @Slot(str)
    def on_render_finished(self, msg):
        """Triggered when ComfyUI finishes a render."""
        print(f"[Playground] Render complete event: {msg[:100]}...")
        if self.current_scene_id:
            self.status.show_status("🖼 Render complete — refreshing preview.")
            self.load_scene(QListWidgetItem(self.current_scene_id))

    # ------------------------------------------------------------
    # 🧹 Cleanup
    # ------------------------------------------------------------
    def closeEvent(self, event):
        try:
            if hasattr(self, "ws_thread"):
                self.ws_thread.stop()
        except Exception:
            pass
        event.accept()

    # ------------------------------------------------------------
    # 🔄 Roleplay Stage Transitions
    # ------------------------------------------------------------
    def convert_selected_raw(self):
        filename = self.raw_box.currentText()
        if not filename:
            QMessageBox.warning(self, "No Raw File", "Please select a raw log first.")
            return
        try:
            resp = requests.post(
                f"{self.api_base}/roleplay/convert_raw/{filename}", timeout=30
            )
            data = resp.json()
            if data.get("status") == "ok":
                self.status.show_status(
                    f"✅ Converted raw file → scene {data['scene_id']}"
                )
                self.load_roleplay_categories()
            else:
                self.status.show_status(f"⚠️ Conversion failed: {data}")
        except Exception as e:
            self.status.show_status(f"❌ Error converting raw: {e}")

    def promote_selected_converted(self):
        scene_id = self.converted_box.currentText()
        if not scene_id:
            QMessageBox.warning(
                self, "No Converted Scene", "Please select a converted scene first."
            )
            return
        try:
            resp = requests.post(
                f"{self.api_base}/roleplay/promote/{scene_id}", timeout=20
            )
            data = resp.json()
            if data.get("status") == "ok":
                self.status.show_status(f"✅ Promoted {scene_id} to ready.")
                self.load_roleplay_categories()
            else:
                self.status.show_status(f"⚠️ Promotion failed: {data}")
        except Exception as e:
            self.status.show_status(f"❌ Promotion error: {e}")

    def revert_selected_ready(self):
        scene_id = self.ready_box.currentText()
        if not scene_id:
            QMessageBox.warning(
                self, "No Ready Scene", "Please select a ready scene first."
            )
            return
        try:
            resp = requests.post(
                f"{self.api_base}/roleplay/revert/{scene_id}", timeout=20
            )
            data = resp.json()
            if data.get("status") == "ok":
                self.status.show_status(f"✅ Reverted {scene_id} to converted.")
                self.load_roleplay_categories()
            else:
                self.status.show_status(f"⚠️ Reversion failed: {data}")
        except Exception as e:
            self.status.show_status(f"❌ Reversion error: {e}")
