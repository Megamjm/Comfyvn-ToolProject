from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass
class TimelineEvent:
    """Represents a single scheduled event on the timeline."""

    time: float
    track: str
    label: str
    node_id: Optional[str] = None
    data: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "time": self.time,
            "track": self.track,
            "label": self.label,
        }
        if self.node_id:
            payload["node_id"] = self.node_id
        if self.data:
            payload["data"] = dict(self.data)
        return payload


class TimelineEditor(QWidget):
    """
    Timeline editor with dedicated tracks for dialogue, bgm, sfx, and directives.

    Provides event management, import/export helpers, and a scrubber to preview
    the composed sequence.
    """

    tracks = ("dialogue", "bgm", "sfx", "directives")

    timelineChanged = Signal(list)
    scrubChanged = Signal(float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._events: List[TimelineEvent] = []
        self._node_choices: List[str] = []
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(QLabel("Timeline Events", self))
        header.addStretch(1)
        self.btn_import = QPushButton("Import…", self)
        self.btn_export = QPushButton("Export…", self)
        header.addWidget(self.btn_import)
        header.addWidget(self.btn_export)
        layout.addLayout(header)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Time", "Track", "Label", "Target"])
        self.tree.setSelectionMode(QTreeWidget.SingleSelection)
        self.tree.itemDoubleClicked.connect(lambda *_: self._edit_selected())
        layout.addWidget(self.tree, 1)

        controls = QHBoxLayout()
        self.btn_add_dialogue = QPushButton("Add Dialogue", self)
        self.btn_add_bgm = QPushButton("Add BGM", self)
        self.btn_add_sfx = QPushButton("Add SFX", self)
        self.btn_add_directive = QPushButton("Add Directive", self)
        self.btn_edit = QPushButton("Edit", self)
        self.btn_remove = QPushButton("Remove", self)

        controls.addWidget(self.btn_add_dialogue)
        controls.addWidget(self.btn_add_bgm)
        controls.addWidget(self.btn_add_sfx)
        controls.addWidget(self.btn_add_directive)
        controls.addWidget(self.btn_edit)
        controls.addWidget(self.btn_remove)
        layout.addLayout(controls)

        scrub_row = QHBoxLayout()
        self.scrub_label = QLabel("Position: 0.0s", self)
        self.scrub_slider = QSlider(Qt.Horizontal, self)
        self.scrub_slider.setRange(0, 100)
        self.scrub_slider.valueChanged.connect(self._on_scrub_changed)
        scrub_row.addWidget(self.scrub_label, 0)
        scrub_row.addWidget(self.scrub_slider, 1)
        layout.addLayout(scrub_row)

        # Wiring
        self.btn_add_dialogue.clicked.connect(
            lambda: self._add_event_dialog("dialogue")
        )
        self.btn_add_bgm.clicked.connect(lambda: self._add_event_dialog("bgm"))
        self.btn_add_sfx.clicked.connect(lambda: self._add_event_dialog("sfx"))
        self.btn_add_directive.clicked.connect(
            lambda: self._add_event_dialog("directives")
        )
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_import.clicked.connect(self._import_dialog)
        self.btn_export.clicked.connect(self._export_dialog)

    # ------------------------------------------------------------------
    def set_node_catalog(self, nodes: Iterable[str]) -> None:
        """Update the node selection list for dialogue events."""
        self._node_choices = sorted(str(node) for node in nodes if node)

    def timeline(self) -> List[Dict[str, object]]:
        return [event.to_dict() for event in self._events]

    def load_timeline(self, payload: Iterable[Dict[str, object]]) -> None:
        self._events.clear()
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            try:
                time = float(raw.get("time"))
            except (TypeError, ValueError):
                continue
            track = str(raw.get("track") or "")
            if track not in self.tracks:
                continue
            label = str(raw.get("label") or "")
            node = raw.get("node_id")
            node_id = str(node) if isinstance(node, str) else None
            data_raw = raw.get("data") if isinstance(raw.get("data"), dict) else {}
            data = {str(k): str(v) for k, v in data_raw.items()}
            self._events.append(
                TimelineEvent(
                    time=time,
                    track=track,
                    label=label,
                    node_id=node_id,
                    data=data,
                )
            )
        self._events.sort(key=lambda ev: ev.time)
        self._refresh_tree()
        self._emit_timeline_changed()

    # ------------------------------------------------------------------
    def _add_event_dialog(self, track: str) -> None:
        time, ok_time = QInputDialog.getDouble(
            self,
            "Event Time",
            "Timestamp (seconds):",
            minValue=0.0,
            decimals=2,
        )
        if not ok_time:
            return
        label, ok_label = QInputDialog.getText(self, "Event Label", "Label / summary:")
        if not ok_label:
            return

        node_id: Optional[str] = None
        data: Dict[str, str] = {}

        if track == "dialogue":
            node_id = self._prompt_node_id()
            if not node_id:
                QMessageBox.information(
                    self,
                    "Dialogue Event",
                    "A node id is required for dialogue events.",
                )
                return
        elif track in {"bgm", "sfx"}:
            prompt = "Asset identifier:" if track == "bgm" else "Sound effect id:"
            asset, ok_asset = QInputDialog.getText(self, "Asset", prompt)
            if not ok_asset or not asset.strip():
                return
            data["asset"] = asset.strip()
        elif track == "directives":
            directive, ok_dir = QInputDialog.getText(
                self, "Directive", "Directive payload:"
            )
            if not ok_dir:
                return
            data["directive"] = directive.strip()

        event = TimelineEvent(
            time=time,
            track=track,
            label=label.strip(),
            node_id=node_id,
            data=data,
        )
        self._events.append(event)
        self._events.sort(key=lambda ev: ev.time)
        self._refresh_tree()
        self._emit_timeline_changed()

    def _edit_selected(self) -> None:
        item = self.tree.currentItem()
        if not item:
            return
        index = item.data(0, Qt.UserRole)
        if index is None:
            return
        try:
            event = self._events[int(index)]
        except (IndexError, ValueError):
            return

        time, ok_time = QInputDialog.getDouble(
            self,
            "Event Time",
            "Timestamp (seconds):",
            value=event.time,
            minValue=0.0,
            decimals=2,
        )
        if not ok_time:
            return
        label, ok_label = QInputDialog.getText(
            self, "Event Label", "Label / summary:", text=event.label
        )
        if not ok_label:
            return

        node_id = event.node_id
        data = dict(event.data)
        if event.track == "dialogue":
            node_id = self._prompt_node_id(current=node_id)
            if not node_id:
                QMessageBox.information(
                    self, "Dialogue Event", "A node id is required for dialogue events."
                )
                return
        elif event.track in {"bgm", "sfx"}:
            key = "asset"
            asset, ok_asset = QInputDialog.getText(
                self,
                "Asset",
                "Asset identifier:",
                text=data.get(key, ""),
            )
            if not ok_asset or not asset.strip():
                return
            data[key] = asset.strip()
        elif event.track == "directives":
            directive, ok_dir = QInputDialog.getText(
                self,
                "Directive",
                "Directive payload:",
                text=data.get("directive", ""),
            )
            if not ok_dir:
                return
            data["directive"] = directive.strip()

        event.time = time
        event.label = label.strip()
        event.node_id = node_id
        event.data = data
        self._events.sort(key=lambda ev: ev.time)
        self._refresh_tree()
        self._emit_timeline_changed()

    def _remove_selected(self) -> None:
        item = self.tree.currentItem()
        if not item:
            return
        index = item.data(0, Qt.UserRole)
        if index is None:
            return
        try:
            idx = int(index)
        except ValueError:
            return
        if idx < 0 or idx >= len(self._events):
            return
        confirm = QMessageBox.question(
            self,
            "Remove Event",
            f"Remove event '{self._events[idx].label}'?",
        )
        if confirm != QMessageBox.Yes:
            return
        self._events.pop(idx)
        self._refresh_tree()
        self._emit_timeline_changed()

    def _prompt_node_id(self, current: Optional[str] = None) -> Optional[str]:
        if not self._node_choices:
            QMessageBox.information(
                self,
                "Node Selection",
                "No nodes available. Create nodes first in the node editor.",
            )
            return None
        default_index = (
            self._node_choices.index(current) if current in self._node_choices else 0
        )
        node_id, ok = QInputDialog.getItem(
            self,
            "Dialogue Node",
            "Node id:",
            self._node_choices,
            current=default_index,
            editable=False,
        )
        if not ok:
            return None
        return node_id

    # ------------------------------------------------------------------
    def _refresh_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        for index, event in enumerate(self._events):
            row = QTreeWidgetItem(
                [
                    f"{event.time:.2f}",
                    event.track,
                    event.label,
                    event.node_id
                    or event.data.get("asset", "")
                    or event.data.get("directive", ""),
                ]
            )
            row.setData(0, Qt.UserRole, index)
            self.tree.addTopLevelItem(row)
        self.tree.blockSignals(False)
        self._update_scrub_range()

    def _update_scrub_range(self) -> None:
        if not self._events:
            self.scrub_slider.blockSignals(True)
            self.scrub_slider.setRange(0, 100)
            self.scrub_slider.setValue(0)
            self.scrub_slider.blockSignals(False)
            self.scrub_label.setText("Position: 0.0s")
            return
        max_time = max(event.time for event in self._events)
        limit = int((max_time + 5.0) * 10)
        self.scrub_slider.blockSignals(True)
        self.scrub_slider.setRange(0, max(limit, 10))
        self.scrub_slider.setValue(0)
        self.scrub_slider.blockSignals(False)
        self.scrub_label.setText("Position: 0.0s")

    def _on_scrub_changed(self, value: int) -> None:
        seconds = value / 10.0
        self.scrub_label.setText(f"Position: {seconds:.1f}s")
        self.scrubChanged.emit(seconds)
        self._highlight_for_time(seconds)

    def _highlight_for_time(self, seconds: float) -> None:
        if not self._events:
            return
        target_index: Optional[int] = None
        for idx, event in enumerate(self._events):
            if event.time <= seconds:
                target_index = idx
            else:
                break
        if target_index is None:
            return
        item = self.tree.topLevelItem(target_index)
        if item:
            self.tree.setCurrentItem(item)

    # ------------------------------------------------------------------
    def _emit_timeline_changed(self) -> None:
        self.timelineChanged.emit(self.timeline())

    # Import/export -----------------------------------------------------
    def _import_dialog(self) -> None:
        path, ok = QFileDialog.getOpenFileName(
            self, "Import Timeline", "", "JSON Files (*.json);;All Files (*)"
        )
        if not ok or not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            payload = json.loads(text)
        except Exception as exc:  # pragma: no cover - GUI feedback
            QMessageBox.critical(self, "Import Timeline", f"Failed to import: {exc}")
            return
        if not isinstance(payload, list):
            QMessageBox.critical(
                self,
                "Import Timeline",
                "Timeline file must contain a JSON array of events.",
            )
            return
        self.load_timeline(payload)

    def _export_dialog(self) -> None:
        if not self._events:
            QMessageBox.information(
                self,
                "Export Timeline",
                "Add at least one event before exporting.",
            )
            return
        path, ok = QFileDialog.getSaveFileName(
            self, "Export Timeline", "timeline.json", "JSON Files (*.json)"
        )
        if not ok or not path:
            return
        try:
            data = json.dumps(self.timeline(), indent=2, ensure_ascii=False)
            Path(path).write_text(data, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - GUI feedback
            QMessageBox.critical(self, "Export Timeline", f"Failed to export: {exc}")


__all__ = ["TimelineEditor", "TimelineEvent"]
