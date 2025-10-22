from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from comfyvn.gui.debug.runner_panel import RunnerPanel
from comfyvn.gui.editors.node_editor import NodeEditor
from comfyvn.gui.editors.timeline_editor import TimelineEditor
from comfyvn.gui.services.collab_client import CollabClient, SceneCollabAdapter
from comfyvn.gui.services.server_bridge import ServerBridge


class TimelineView(QWidget):
    """
    Integrated scenario authoring workspace.

    Combines the node editor, multi-track timeline editor, and the scenario runner
    stepper into a single Studio view.
    """

    def __init__(
        self,
        api_client: Optional[ServerBridge] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.bridge = api_client or ServerBridge()
        self.collab_client = CollabClient()
        self.collab_adapter = None
        self._timeline_cache: List[Dict[str, object]] = []
        self._scene_cache: Optional[Dict[str, object]] = None

        self.node_editor = NodeEditor(self)
        self.timeline_editor = TimelineEditor(self)
        self.runner_panel = RunnerPanel(self.bridge, self)
        # Collab adapter will be initialised after UI widgets are created
        self.runner_panel.set_scene_provider(self.node_editor.scene)

        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Scenario Workshop — Nodes · Timeline · Runner", self)
        title.setStyleSheet("font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)
        self.collab_label = QLabel("Collab: idle", self)
        self.collab_label.setObjectName("collabStatusLabel")
        self.collab_label.setStyleSheet("color: #666; font-size: 11px;")
        header.addWidget(self.collab_label)
        self.btn_refresh_nodes = QPushButton("Sync Runner", self)
        header.addWidget(self.btn_refresh_nodes)
        layout.addLayout(header)

        self.collab_adapter = SceneCollabAdapter(
            self.node_editor,
            self.collab_client,
            status_label=self.collab_label,
            parent=self,
        )

        splitter = QSplitter(Qt.Vertical, self)
        top_split = QSplitter(Qt.Horizontal, splitter)
        top_split.addWidget(self.node_editor)
        top_split.addWidget(self.timeline_editor)
        top_split.setStretchFactor(0, 3)
        top_split.setStretchFactor(1, 2)

        splitter.addWidget(top_split)
        splitter.addWidget(self.runner_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter, 1)

        self.status_label = QLabel(
            "Add nodes to begin building a scene. Import/export from each panel as needed.",
            self,
        )
        layout.addWidget(self.status_label)

    def _connect_signals(self) -> None:
        self.node_editor.sceneChanged.connect(self._on_scene_changed)
        self.node_editor.selectionChanged.connect(self._on_node_selected)
        self.timeline_editor.timelineChanged.connect(self._on_timeline_changed)
        self.timeline_editor.scrubChanged.connect(self._on_scrub_position)
        self.runner_panel.nodeFocused.connect(self._focus_node_from_runner)
        self.btn_refresh_nodes.clicked.connect(self._sync_runner_scene)

    # ------------------------------------------------------------------
    def _on_scene_changed(self, scene: Dict[str, object]) -> None:
        self._scene_cache = scene
        node_ids = self._extract_node_ids(scene.get("nodes"))
        self.timeline_editor.set_node_catalog(node_ids)
        self.runner_panel.set_node_catalog(node_ids)
        self.status_label.setText(
            f"Scene nodes: {len(node_ids)} · Start: {scene.get('start') or '<unset>'}"
        )

    def _on_node_selected(self, node_id: str) -> None:
        if not node_id:
            return
        # Jump timeline scrubber to matching dialogue event if present
        for index, event in enumerate(self._timeline_cache):
            if event.get("track") == "dialogue" and event.get("node_id") == node_id:
                seconds = float(event.get("time") or 0.0)
                self.timeline_editor.scrub_slider.setValue(int(seconds * 10))
                break

    def _on_timeline_changed(self, events: List[Dict[str, object]]) -> None:
        self._timeline_cache = events
        dialogue_count = sum(1 for ev in events if ev.get("track") == "dialogue")
        self.status_label.setText(
            f"Scene nodes: {len(self.node_editor.node_ids())} · Timeline events: {len(events)} (dialogue {dialogue_count})"
        )

    def _on_scrub_position(self, seconds: float) -> None:
        node_id = None
        for event in self._timeline_cache:
            if event.get("track") != "dialogue":
                continue
            try:
                time_value = float(event.get("time"))
            except (TypeError, ValueError):
                continue
            if time_value <= seconds + 1e-6:
                node_id = str(event.get("node_id") or "")
            else:
                break
        if node_id:
            self.node_editor.focus_node(node_id)

    def _focus_node_from_runner(self, node_id: str) -> None:
        self.node_editor.focus_node(node_id)

    def _sync_runner_scene(self) -> None:
        if not self._scene_cache:
            QMessageBox.information(
                self,
                "Scenario Workshop",
                "Create a scene first before syncing to the runner.",
            )
            return
        self.runner_panel.set_scene(self._scene_cache)
        self.status_label.setText("Runner synced with current scene.")

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_node_ids(nodes: Optional[Iterable[object]]) -> List[str]:
        output: List[str] = []
        if not nodes:
            return output
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            if isinstance(node_id, str):
                output.append(node_id)
        return sorted(output)


__all__ = ["TimelineView"]
