# comfyvn/gui/asset_browser.py
# Asset browser with project root, directory tree, preview list, metadata panel,
# and hooks to trigger ComfyUI renders (sprites, NPC background mode, dumps).
# [🎨 GUI Code Production Chat]

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot, QDir, QSize
from PySide6.QtGui import QStandardItemModel, QStandardItem, QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QTreeView, QFileSystemModel,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QFormLayout, QLineEdit,
    QComboBox, QCheckBox, QSpinBox, QMessageBox
)
import requests


class AssetBrowser(QWidget):
    request_log = Signal(str)
    request_settings = Signal(object)  # function returning dict
    request_settings_changed = Signal(dict)

    def __init__(self):
        super().__init__()
        self._project_root = Path(".").resolve()
        self._assets_dir = None
        self._model = None
        self._build_ui()

    # -------------------- UI --------------------

    def _build_ui(self):
        root = QHBoxLayout(self)

        # Left: directory tree
        left = QVBoxLayout()
        box_tree = QGroupBox("Project Tree")
        v = QVBoxLayout()
        self.fs_model = QFileSystemModel()
        self.fs_model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Files)
        self.fs_view = QTreeView()
        self.fs_view.setModel(self.fs_model)
        self.fs_view.setColumnWidth(0, 260)
        self.fs_view.clicked.connect(self._on_tree_clicked)
        v.addWidget(self.fs_view)
        box_tree.setLayout(v)
        left.addWidget(box_tree)

        # Right: assets + metadata + actions
        right = QVBoxLayout()

        self.assets_list = QListWidget()
        self.assets_list.setIconSize(QSize(96, 96))
        self.assets_list.itemSelectionChanged.connect(self._asset_selected)

        meta_box = QGroupBox("Metadata")
        form = QFormLayout()
        self.meta_name = QLineEdit()
        self.meta_char = QLineEdit()
        self.meta_expr = QComboBox()
        self.meta_expr.addItems(["neutral", "happy", "sad", "angry", "surprised", "tired"])
        self.meta_tag_npc = QCheckBox("Background NPC (no face)")
        form.addRow("Asset Name", self.meta_name)
        form.addRow("Character", self.meta_char)
        form.addRow("Expression", self.meta_expr)
        form.addRow(self.meta_tag_npc)
        meta_box.setLayout(form)

        actions = QHBoxLayout()
        self.btn_gen_sprite = QPushButton("Generate Sprite (ComfyUI)")
        self.btn_gen_dump = QPushButton("Render Full Character Dump")
        self.btn_refresh = QPushButton("Refresh")

        self.btn_gen_sprite.clicked.connect(self._generate_sprite)
        self.btn_gen_dump.clicked.connect(self._render_full_dump)
        self.btn_refresh.clicked.connect(self.refresh)

        actions.addWidget(self.btn_gen_sprite)
        actions.addWidget(self.btn_gen_dump)
        actions.addWidget(self.btn_refresh)

        right.addWidget(self.assets_list)
        right.addWidget(meta_box)
        right.addLayout(actions)

        root.addLayout(left, 3)
        root.addLayout(right, 5)

    # -------------------- Public API --------------------

    def set_project_root(self, directory: str):
        self._project_root = Path(directory).resolve()
        self.fs_model.setRootPath(str(self._project_root))
        self.fs_view.setRootIndex(self.fs_model.index(str(self._project_root)))
        self.refresh()
        self.request_log.emit(f"Asset Browser root set to: {self._project_root}")

    def on_settings_changed(self, cfg: dict):
        # update assets dir and refresh if necessary
        assets_dir = cfg.get("paths", {}).get("assets_dir")
        if assets_dir:
            self._assets_dir = Path(assets_dir).resolve()
            self.request_log.emit(f"Assets dir: {self._assets_dir}")
        if self._project_root.exists():
            self.refresh()

    # -------------------- Internals --------------------

    def refresh(self):
        self.assets_list.clear()
        base = self._assets_dir if self._assets_dir else self._project_root
        if not base.exists():
            self.request_log.emit(f"Assets path missing: {base}")
            return

        exts = {".png", ".jpg", ".jpeg", ".webp"}
        for p in base.rglob("*"):
            if p.suffix.lower() in exts:
                item = QListWidgetItem(p.name)
                pix = QPixmap(str(p))
                if not pix.isNull():
                    icon = QIcon(pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    item.setIcon(icon)
                item.setData(Qt.UserRole, str(p))
                self.assets_list.addItem(item)

    @Slot()
    def _on_tree_clicked(self, idx):
        path = self.fs_model.filePath(idx)
        if Path(path).is_dir():
            self._assets_dir = Path(path).resolve()
            self.refresh()

    def _asset_selected(self):
        items = self.assets_list.selectedItems()
        if not items:
            return
        p = Path(items[0].data(Qt.UserRole))
        self.meta_name.setText(p.stem)
        # Simple parse for character__expr.png
        if "__" in p.stem:
            char, expr = p.stem.split("__", 1)
            self.meta_char.setText(char)
            i = self.meta_expr.findText(expr)
            if i >= 0:
                self.meta_expr.setCurrentIndex(i)

    # -------------------- Actions --------------------

    def _read_settings(self) -> Optional[dict]:
        if not self.request_settings:
            return None
        return self.request_settings.emit()  # note: connected in MainWindow; returns via slot fetch

    @Slot()
    def _generate_sprite(self):
        # Collect current meta + call ComfyUI with a configured workflow
        items = self.assets_list.selectedItems()
        char = self.meta_char.text().strip() or "character"
        expr = self.meta_expr.currentText()
        npc = self.meta_tag_npc.isChecked()

        cfg = None
        # safer pull via MainWindow
        parent = self.parent()
        while parent and not hasattr(parent, "collect_settings"):
            parent = parent.parent()
        if parent and hasattr(parent, "collect_settings"):
            cfg = parent.collect_settings()

        if not cfg:
            QMessageBox.warning(self, "No Settings", "Settings not available.")
            return

        comfy = cfg["integrations"]["comfyui_host"]
        workflow_file = Path(cfg["integrations"]["comfyui_workflow"])
        if not workflow_file.exists():
            QMessageBox.warning(self, "Workflow Missing", f"Workflow not found: {workflow_file}")
            return

        try:
            with open(workflow_file, "r", encoding="utf-8") as f:
                workflow = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Workflow Error", str(e))
            return

        # Inject parameters (example placeholders for nodes with prompts)
        # You should align node IDs/inputs with your actual ComfyUI graph
        # e.g., workflow["nodes"]["CHARACTER_NAME"]["inputs"]["text"] = char
        #       workflow["nodes"]["EXPRESSION"]["inputs"]["text"] = expr
        # NPC/background flag might map to a negative prompt or a switch node.
        workflow = self._inject_workflow_params(workflow, char, expr, npc)

        try:
            url = comfy.rstrip("/") + "/prompt"
            r = requests.post(url, json={"prompt": workflow})
            if r.status_code == 200:
                self.request_log.emit(f"ComfyUI job dispatched for {char} [{expr}] (NPC={npc})")
            else:
                self.request_log.emit(f"ComfyUI job failed: {r.status_code} - {r.text}")
        except Exception as e:
            self.request_log.emit(f"ComfyUI connection error: {e}")

    @Slot()
    def _render_full_dump(self):
        # Iterate common expressions and dispatch a batch
        char = self.meta_char.text().strip() or "character"
        expressions = ["neutral", "happy", "sad", "angry", "surprised", "tired"]
        for expr in expressions:
            self.meta_expr.setCurrentText(expr)
            self._generate_sprite()
        QMessageBox.information(self, "Dump", f"Dispatched full dump for {char}")

    # -------------------- Helpers --------------------

    def _inject_workflow_params(self, workflow: dict, char: str, expr: str, npc: bool) -> dict:
        # This is a central place to map UI metadata into workflow fields.
        # Replace with your exact node IDs / names.
        # Below are illustrative examples:
        wf = dict(workflow)  # shallow copy
        try:
            # Example pseudo-injection:
            # Find nodes by a convention and inject text fields
            for node in wf.get("nodes", []):
                title = (node.get("title") or "").lower()
                if "character" in title and "prompt" in node.get("type", "").lower():
                    node["inputs"]["text"] = f"{char}, {expr}"
                if "negative" in title and npc:
                    node["inputs"]["text"] = (node["inputs"].get("text", "") + ", no face, low detail, background character").strip(", ")
                # Resolution injection if present
                if "image" in node.get("type","").lower():
                    # leave as default; resolutions handled by Settings panel if you wire them
                    pass
        except Exception:
            # Keep workflow as-is if mapping fails
            pass
        return wf
