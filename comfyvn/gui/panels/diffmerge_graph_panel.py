from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from comfyvn.config.baseurl_authority import default_base_url


class DiffmergeGraphPanel(QWidget):
    """
    Visualises worldline timelines and fast-forward merge eligibility.
    """

    def __init__(
        self, base_url: Optional[str] = None, parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.base_url = (base_url or default_base_url()).rstrip("/")
        self._world_cache: Dict[str, Dict[str, Any]] = {}
        self._graph_cache: Dict[str, Any] = {}
        self._fast_forward: Dict[str, Any] = {}

        self._scene = QGraphicsScene(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(QLabel("Target Worldline:"))
        self.target_selector = QComboBox()
        self.target_selector.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        header.addWidget(self.target_selector, 1)

        header.addWidget(QLabel("Compare:"))
        self.world_list = QListWidget()
        self.world_list.setSelectionMode(QListWidget.MultiSelection)
        self.world_list.setMaximumHeight(120)
        self.world_list.setMinimumWidth(180)
        header.addWidget(self.world_list, 2)

        buttons = QVBoxLayout()
        self.btn_refresh = QPushButton("Render Graph")
        self.btn_refresh.clicked.connect(self.refresh_graph)
        self.btn_merge = QPushButton("Apply Merge")
        self.btn_merge.clicked.connect(self.apply_merge)
        buttons.addWidget(self.btn_refresh)
        buttons.addWidget(self.btn_merge)
        buttons.addStretch(1)
        header.addLayout(buttons)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        graph_container = QWidget()
        graph_layout = QVBoxLayout(graph_container)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        self.view = QGraphicsView(self._scene)
        self.view.setRenderHints(self.view.renderHints() & ~self.view.Antialiasing)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        graph_layout.addWidget(self.view)
        splitter.addWidget(graph_container)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(4, 0, 0, 0)
        sidebar_layout.addWidget(QLabel("Fast-Forward Preview"))
        self.fast_table = QTreeWidget()
        self.fast_table.setColumnCount(4)
        self.fast_table.setHeaderLabels(["World", "Status", "Added Nodes", "Conflicts"])
        self.fast_table.setRootIsDecorated(False)
        self.fast_table.setUniformRowHeights(True)
        sidebar_layout.addWidget(self.fast_table, 1)
        splitter.addWidget(sidebar)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter, 1)

        self.status_bar = QLabel("Ready.")
        self.status_bar.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        layout.addWidget(self.status_bar)

        self._load_worlds()

    # ------------------------------------------------------------------ fetching
    def _load_worlds(self) -> None:
        url = f"{self.base_url}/api/pov/worlds"
        try:
            response = requests.get(url, timeout=5.0)
        except Exception as exc:
            self.status_bar.setText(f"Failed to reach backend: {exc}")
            return
        if response.status_code == 403:
            self.status_bar.setText(
                "Diffmerge tooling disabled (enable_diffmerge_tools feature flag)."
            )
            self.btn_refresh.setEnabled(False)
            self.btn_merge.setEnabled(False)
            return
        if response.status_code >= 400:
            self.status_bar.setText(f"Worldline list failed: {response.status_code}")
            return
        payload = response.json()
        items = payload.get("items") or []
        self._world_cache = {
            str(entry.get("id")): entry for entry in items if isinstance(entry, dict)
        }
        self.target_selector.clear()
        self.world_list.clear()
        active_id = None
        active_payload = payload.get("active")
        if isinstance(active_payload, dict):
            active_id = str(active_payload.get("id") or "")
        target_world_id: Optional[str] = None
        for world_id, entry in self._world_cache.items():
            label = entry.get("label") or world_id
            display = f"{label} ({world_id})"
            self.target_selector.addItem(display, userData=world_id)
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, world_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.world_list.addItem(item)
            if entry.get("active") or world_id == active_id:
                index = self.target_selector.count() - 1
                self.target_selector.setCurrentIndex(index)
                target_world_id = world_id
        if target_world_id is None and self.target_selector.count() > 0:
            target_world_id = self.target_selector.currentData()
        for index in range(self.world_list.count()):
            item = self.world_list.item(index)
            world_id = item.data(Qt.UserRole)
            if target_world_id and world_id == target_world_id:
                item.setCheckState(Qt.Unchecked)
            else:
                item.setCheckState(Qt.Checked)
        self.status_bar.setText(f"Loaded {len(self._world_cache)} worldlines.")

    def _selected_worlds(self) -> List[str]:
        selected: List[str] = []
        for index in range(self.world_list.count()):
            item = self.world_list.item(index)
            if item.checkState() == Qt.Checked:
                world_id = item.data(Qt.UserRole)
                if world_id:
                    selected.append(str(world_id))
        return selected

    def refresh_graph(self) -> None:
        target = self.target_selector.currentData()
        if not target:
            self.status_bar.setText("Select a target worldline.")
            return
        payload = {
            "target": target,
            "worlds": self._selected_worlds(),
            "include_fast_forward": True,
        }
        url = f"{self.base_url}/api/diffmerge/worldlines/graph"
        try:
            response = requests.post(url, json=payload, timeout=8.0)
        except Exception as exc:
            self.status_bar.setText(f"Graph request failed: {exc}")
            return
        if response.status_code == 403:
            self.status_bar.setText(
                "Diffmerge tooling disabled (enable_diffmerge_tools feature flag)."
            )
            return
        if response.status_code >= 400:
            self.status_bar.setText(f"Graph request failed: {response.status_code}")
            return
        graph_payload = response.json()
        self._graph_cache = graph_payload
        self._fast_forward = graph_payload.get("fast_forward") or {}
        self._render_graph(graph_payload)
        self._populate_fast_forward(self._fast_forward)
        nodes = graph_payload.get("graph", {}).get("nodes") or []
        self.status_bar.setText(
            f"Graph rendered with {len(nodes)} nodes across {len(graph_payload.get('worlds') or [])} worldlines."
        )

    def apply_merge(self) -> None:
        target = self.target_selector.currentData()
        if not target:
            QMessageBox.warning(self, "DiffMerge", "Select a target worldline first.")
            return
        if not self.world_list.selectedItems():
            QMessageBox.information(
                self,
                "DiffMerge",
                "Select a worldline from the compare list (highlight) before applying.",
            )
            return
        source_item = self.world_list.selectedItems()[0]
        source = source_item.data(Qt.UserRole)
        if source == target:
            QMessageBox.information(
                self,
                "DiffMerge",
                "Select a different worldline to merge into the target.",
            )
            return
        confirm = QMessageBox.question(
            self,
            "Confirm Merge",
            f"Merge worldline '{source}' into '{target}'?\nConflicting nodes abort automatically.",
        )
        if confirm != QMessageBox.Yes:
            return
        url = f"{self.base_url}/api/diffmerge/worldlines/merge"
        payload = {"source": source, "target": target, "apply": True}
        try:
            response = requests.post(url, json=payload, timeout=10.0)
        except Exception as exc:
            QMessageBox.critical(self, "Merge Failed", str(exc))
            return
        if response.status_code == 409:
            try:
                detail = response.json()
            except Exception:
                detail = {}
            conflicts = detail.get("conflicts") or detail.get("detail", {}).get(
                "conflicts"
            )
            message = "Merge aborted due to conflicts."
            if conflicts:
                message += f"\nConflicts: {conflicts}"
            QMessageBox.warning(self, "Merge Conflict", message)
            return
        if response.status_code >= 400:
            QMessageBox.critical(
                self,
                "Merge Failed",
                f"Server returned {response.status_code}: {response.text}",
            )
            return
        QMessageBox.information(
            self,
            "Merge Applied",
            f"Merge completed. Fast-forward: {response.json().get('fast_forward')}",
        )
        self._load_worlds()
        self.refresh_graph()

    # ------------------------------------------------------------------ visuals
    def _render_graph(self, graph_payload: Dict[str, Any]) -> None:
        self._scene.clear()
        timeline = graph_payload.get("timeline") or {}
        target_payload = graph_payload.get("target") or {}
        target_id = (
            target_payload.get("id") if isinstance(target_payload, dict) else None
        )
        target_nodes = set(timeline.get(target_id, [])) if target_id else set()

        row_height = 80
        node_width = 90
        node_height = 36
        col_spacing = 100

        pen_default = QPen(QColor("#263238"))
        pen_default.setWidth(1)
        pen_edge = QPen(QColor("#607D8B"))
        pen_edge.setWidth(1)
        pen_edge.setCosmetic(True)

        positions: Dict[tuple[str, str], tuple[float, float]] = {}

        for row_index, (world_id, nodes) in enumerate(timeline.items()):
            y = row_index * row_height
            label_text = world_id
            world_meta = self._world_cache.get(world_id, {})
            if world_meta.get("label"):
                label_text = f"{world_meta['label']} ({world_id})"
            title_item = self._scene.addText(label_text)
            title_item.setPos(-140, y + node_height / 4)
            title_item.setDefaultTextColor(QColor("#37474F"))

            for col_index, node_id in enumerate(nodes):
                x = col_index * col_spacing
                positions[(world_id, node_id)] = (x, y)
                brush_color = QColor("#546E7A")
                if world_id != target_id and node_id not in target_nodes:
                    brush_color = QColor("#F9A825")
                if world_id == target_id:
                    brush_color = QColor("#26A69A")
                rect = self._scene.addRect(
                    x,
                    y,
                    node_width,
                    node_height,
                    pen_default,
                    brush_color,
                )
                rect.setToolTip(node_id)
                label = node_id
                if len(label) > 10:
                    label = f"{label[:4]}…{label[-4:]}"
                text_item: QGraphicsTextItem = self._scene.addText(label)
                text_item.setDefaultTextColor(QColor("#ECEFF1"))
                text_item.setPos(x + 6, y + 6)

        for world_id, nodes in timeline.items():
            for idx in range(len(nodes) - 1):
                start = positions[(world_id, nodes[idx])]
                end = positions[(world_id, nodes[idx + 1])]
                self._scene.addLine(
                    start[0] + node_width,
                    start[1] + node_height / 2,
                    end[0],
                    end[1] + node_height / 2,
                    pen_edge,
                )

        # Resize scene rect
        if positions:
            max_x = max(pos[0] for pos in positions.values()) + col_spacing
            max_y = max(pos[1] for pos in positions.values()) + row_height
            self._scene.setSceneRect(-160, -20, max_x + 180, max_y + 40)
        else:
            self._scene.setSceneRect(0, 0, 0, 0)

    def _populate_fast_forward(self, fast_forward: Dict[str, Any]) -> None:
        self.fast_table.clear()
        for world_id, payload in fast_forward.items():
            status = "ok" if payload.get("ok") else "conflict"
            added_nodes = payload.get("added_nodes") or []
            conflicts = payload.get("conflicts") or []
            row = QTreeWidgetItem(
                [
                    world_id,
                    "fast-forward" if payload.get("fast_forward") else status,
                    ", ".join(added_nodes) if added_nodes else "—",
                    ", ".join(str(entry) for entry in conflicts) if conflicts else "—",
                ]
            )
            if payload.get("ok") and payload.get("fast_forward"):
                row.setForeground(1, QColor("#2E7D32"))
            elif not payload.get("ok"):
                row.setForeground(1, QColor("#C62828"))
            self.fast_table.addTopLevelItem(row)
        self.fast_table.resizeColumnToContents(0)
        self.fast_table.resizeColumnToContents(1)


__all__ = ["DiffmergeGraphPanel"]
