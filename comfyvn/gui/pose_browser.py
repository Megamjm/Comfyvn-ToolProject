# comfyvn/gui/pose_browser.py
# 🧍 Pose Browser — v0.4.3 Dual Pose Comparison Mode
# [ComfyVN_Architect | Phase 3.5]

import os, json
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QHBoxLayout,
    QTextEdit,
    QSplitter,
    QFrame,
    QMessageBox,
    QComboBox,
    QSlider,
)
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QIcon
from PySide6.QtCore import Qt, QSize, QPointF

from comfyvn.assets.pose_manager import PoseManager, PosePreviewGenerator


# ------------------------------------------------------------------
# Dual-pose aware preview widget
# ------------------------------------------------------------------
class PosePreview(QWidget):
    """Renders one or two poses in overlay or side-by-side mode."""

    def __init__(self):
        super().__init__()
        self.pose_a = {"pixmap": None, "skeleton": {}}
        self.pose_b = {"pixmap": None, "skeleton": {}}
        self.mode = "single"  # "single" | "side" | "overlay"
        self.alpha = 0.5  # overlay transparency
        self.setMinimumHeight(260)
        self.setStyleSheet("background-color:#222;border:1px solid #555;")

    def set_pose(self, pose_data: dict, slot: str = "A"):
        """Assign pose data to slot A or B."""
        pixmap = None
        if pose_data.get("preview_image") and os.path.exists(
            pose_data["preview_image"]
        ):
            pixmap = QPixmap(pose_data["preview_image"])
        elif PosePreviewGenerator:
            pixmap = PosePreviewGenerator.generate(256, 512)
        skeleton = pose_data.get("skeleton", {})
        target = self.pose_a if slot == "A" else self.pose_b
        target["pixmap"] = pixmap
        target["skeleton"] = skeleton
        self.update()

    def set_mode(self, mode: str):
        self.mode = mode
        self.update()

    def set_alpha(self, alpha: float):
        self.alpha = alpha
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        def draw_pose(pixmap, skeleton, color=QColor("#00FFAA"), alpha=1.0, offset_x=0):
            if not pixmap:
                pixmap = PosePreviewGenerator.generate(
                    w // 2 if self.mode == "side" else w, h
                )
            scaled = pixmap.scaled(
                w // 2 if self.mode == "side" else w,
                h,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            x = offset_x + ((w // 2 if self.mode == "side" else w) - scaled.width()) / 2
            y = (h - scaled.height()) / 2
            p.setOpacity(alpha)
            p.drawPixmap(x, y, scaled)
            p.setOpacity(1.0)
            if not skeleton:
                return
            vals = list(skeleton.values())
            max_x = max(p["x"] for p in vals)
            max_y = max(p["y"] for p in vals)
            if max_x <= 1.0 and max_y <= 1.0:
                for pid, pt in skeleton.items():
                    pt["x"] *= w // 2 if self.mode == "side" else w
                    pt["y"] *= h
            pen = QPen(color)
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(QBrush(color.lighter()))
            pts = {
                pid: QPointF(pt["x"] + offset_x, pt["y"])
                for pid, pt in skeleton.items()
            }
            for point in pts.values():
                p.drawEllipse(point, 4, 4)
            ids = sorted(pts.keys())
            for i in range(len(ids) - 1):
                a, b = ids[i], ids[i + 1]
                if a in pts and b in pts:
                    p.drawLine(pts[a], pts[b])

        # render modes
        if self.mode == "side":
            p.fillRect(self.rect(), QColor(20, 20, 20))
            draw_pose(
                self.pose_a["pixmap"],
                self.pose_a["skeleton"],
                QColor("#00FFAA"),
                1.0,
                0,
            )
            draw_pose(
                self.pose_b["pixmap"],
                self.pose_b["skeleton"],
                QColor("#FF4080"),
                1.0,
                w // 2,
            )
        elif self.mode == "overlay":
            p.fillRect(self.rect(), QColor(20, 20, 20))
            draw_pose(
                self.pose_a["pixmap"], self.pose_a["skeleton"], QColor("#00FFAA"), 1.0
            )
            draw_pose(
                self.pose_b["pixmap"],
                self.pose_b["skeleton"],
                QColor("#FF4080"),
                self.alpha,
            )
        else:  # single
            draw_pose(
                self.pose_a["pixmap"], self.pose_a["skeleton"], QColor("#00FFAA"), 1.0
            )
        p.end()


# ------------------------------------------------------------------
# PoseBrowser extended with comparison controls
# ------------------------------------------------------------------
class PoseBrowser(QWidget):
    """Pose Browser with dual comparison support."""

    def __init__(self, on_pose_selected=None):
        super().__init__()
        self.pose_manager = PoseManager()
        self.on_pose_selected = on_pose_selected
        self.pose_a = None
        self.pose_b = None
        self.mode = "single"

        self.setWindowTitle("🧍 Pose Browser (Compare Mode)")
        self.resize(980, 580)
        main_layout = QVBoxLayout(self)

        title = QLabel("🧍 Pose Comparison Browser")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight:bold;font-size:18px;")
        main_layout.addWidget(title)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Pose list
        self.pose_list = QListWidget()
        self.pose_list.setViewMode(QListWidget.IconMode)
        self.pose_list.setIconSize(QSize(96, 96))
        self.pose_list.setSpacing(10)
        self.pose_list.itemClicked.connect(self.on_pose_click)
        splitter.addWidget(self.pose_list)

        # Right panel
        right = QWidget()
        rlayout = QVBoxLayout(right)
        splitter.addWidget(right)

        # Compare controls
        ctrl_row = QHBoxLayout()
        rlayout.addLayout(ctrl_row)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Single", "Side-by-Side", "Overlay"])
        self.mode_combo.currentIndexChanged.connect(self.on_mode_change)
        self.alpha_slider = QSlider(Qt.Horizontal)
        self.alpha_slider.setRange(0, 100)
        self.alpha_slider.setValue(50)
        self.alpha_slider.valueChanged.connect(self.on_alpha_change)
        self.alpha_slider.setEnabled(False)
        ctrl_row.addWidget(QLabel("Compare Mode:"))
        ctrl_row.addWidget(self.mode_combo)
        ctrl_row.addWidget(QLabel("Blend:"))
        ctrl_row.addWidget(self.alpha_slider)

        # Preview
        self.preview_widget = PosePreview()
        rlayout.addWidget(self.preview_widget)

        # Metadata view
        self.meta = QTextEdit()
        self.meta.setReadOnly(True)
        rlayout.addWidget(self.meta)

        # Buttons
        btns = QHBoxLayout()
        main_layout.addLayout(btns)
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_fetch = QPushButton("🌐 Auto-Fetch")
        self.btn_select_a = QPushButton("A️⃣ Set Pose A")
        self.btn_select_b = QPushButton("B️⃣ Set Pose B")
        self.btn_assign = QPushButton("✅ Assign Pose A")
        for b in [
            self.btn_refresh,
            self.btn_fetch,
            self.btn_select_a,
            self.btn_select_b,
            self.btn_assign,
        ]:
            btns.addWidget(b)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_fetch.clicked.connect(self.auto_fetch)
        self.btn_select_a.clicked.connect(lambda: self.select_pose("A"))
        self.btn_select_b.clicked.connect(lambda: self.select_pose("B"))
        self.btn_assign.clicked.connect(self.confirm_selection)
        self.btn_export_delta = QPushButton("🧾 Export Δ Pose")
        btns.addWidget(self.btn_export_delta)
        self.btn_export_delta.clicked.connect(self.export_pose_delta)

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        self.pose_list.clear()
        poses = self.pose_manager.registry
        if not poses:
            self.pose_list.addItem("No poses available. Try Auto-Fetch.")
            return
        for pid, pose in poses.items():
            item = QListWidgetItem(pid)
            preview = pose.get("preview_image", "")
            if preview and os.path.exists(preview):
                item.setIcon(QIcon(preview))
            elif PosePreviewGenerator:
                item.setIcon(QIcon(PosePreviewGenerator.generate(96, 192)))
            self.pose_list.addItem(item)

    def on_pose_click(self, item):
        pid = item.text()
        pose = self.pose_manager.get_pose(pid)
        if not pose:
            return
        self.meta.setText(json.dumps(pose.get("metadata", {}), indent=2))

    def select_pose(self, slot):
        item = self.pose_list.currentItem()
        if not item:
            QMessageBox.warning(self, "No selection", "Please select a pose first.")
            return
        pid = item.text()
        pose = self.pose_manager.get_pose(pid)
        if not pose:
            return
        if slot == "A":
            self.pose_a = pose
            self.preview_widget.set_pose(pose, "A")
        else:
            self.pose_b = pose
            self.preview_widget.set_pose(pose, "B")

    def on_mode_change(self):
        choice = self.mode_combo.currentText()
        if choice == "Single":
            self.preview_widget.set_mode("single")
            self.alpha_slider.setEnabled(False)
        elif choice == "Side-by-Side":
            self.preview_widget.set_mode("side")
            self.alpha_slider.setEnabled(False)
        else:
            self.preview_widget.set_mode("overlay")
            self.alpha_slider.setEnabled(True)

    def on_alpha_change(self, val):
        self.preview_widget.set_alpha(val / 100.0)

    def auto_fetch(self):
        QMessageBox.information(self, "Fetch", "Fetching available pose packs...")
        self.pose_manager.auto_fetch_all()
        self.refresh()

    def confirm_selection(self):
        if not self.pose_a:
            QMessageBox.warning(
                self, "No Pose A", "Please set Pose A before assigning."
            )
            return
        if self.on_pose_selected:
            self.on_pose_selected(self.pose_a["pose_id"], self.pose_a)
        QMessageBox.information(
            self, "Assigned", f"Pose A '{self.pose_a['pose_id']}' assigned."
        )
        self.close()

    # ==============================================================
    # Pose Delta Export System
    # ==============================================================
    def export_pose_delta(self):
        """Generate a delta JSON comparing Pose A → Pose B."""
        if not self.pose_a or not self.pose_b:
            QMessageBox.warning(self, "Missing Poses", "Set both Pose A and B first.")
            return

        deltas = {}
        a_sk = self.pose_a.get("skeleton", {})
        b_sk = self.pose_b.get("skeleton", {})
        for k, p_a in a_sk.items():
            if k in b_sk:
                try:
                    dx = b_sk[k]["x"] - p_a["x"]
                    dy = b_sk[k]["y"] - p_a["y"]
                    deltas[k] = {"dx": dx, "dy": dy}
                except Exception:
                    continue

        delta = {
            "from_pose": self.pose_a["pose_id"],
            "to_pose": self.pose_b["pose_id"],
            "created_at": datetime.now().isoformat(),
            "deltas": deltas,
        }

        os.makedirs("./data/pose_deltas", exist_ok=True)
        fname = f"{self.pose_a['pose_id']}__to__{self.pose_b['pose_id']}.json"
        fpath = os.path.join("./data/pose_deltas", fname)

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(delta, f, indent=2)

        QMessageBox.information(
            self, "Delta Exported", f"Pose delta saved to:\n{fpath}"
        )
