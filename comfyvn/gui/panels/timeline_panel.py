from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDockWidget, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QSizePolicy,
                               QSplitter, QTextEdit, QVBoxLayout, QWidget)

from comfyvn.studio.core.scene_registry import SceneRegistry
from comfyvn.studio.core.timeline_registry import TimelineRegistry


@dataclass
class TimelineEntry:
    scene_id: str
    title: str
    notes: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"scene_id": self.scene_id, "title": self.title, "notes": self.notes}


def _make_item(text: str, data: dict | None = None) -> QListWidgetItem:
    item = QListWidgetItem(text)
    if data is not None:
        item.setData(Qt.UserRole, data)
    item.setFlags(
        item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
    )
    return item


class TimelinePanel(QDockWidget):
    """
    Visual editor for scene timelines.

    Allows users to assemble ordered scene sequences, attach notes, and persist
    the structure via the TimelineRegistry.
    """

    def __init__(
        self,
        scene_registry: SceneRegistry,
        timeline_registry: TimelineRegistry,
        parent: Optional[QWidget] = None,
    ):
        super().__init__("Timeline", parent)
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.scene_registry = scene_registry
        self.timeline_registry = timeline_registry
        self._active_timeline_id: Optional[int] = None
        self._scene_cache: Dict[str, Dict[str, str]] = {}

        root = QWidget(self)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # Left column timelines list
        left = QVBoxLayout()
        left.addWidget(QLabel("Timelines"))
        self.timeline_list = QListWidget()
        self.timeline_list.currentItemChanged.connect(self._on_timeline_selected)
        left.addWidget(self.timeline_list, 1)

        btn_row = QHBoxLayout()
        self.btn_new = QPushButton("New…")
        self.btn_duplicate = QPushButton("Duplicate")
        self.btn_delete = QPushButton("Delete")
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_duplicate)
        btn_row.addWidget(self.btn_delete)
        left.addLayout(btn_row)

        layout.addLayout(left, 1)

        # Right column - timeline editor
        editor_container = QVBoxLayout()

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Timeline Name:"))
        self.timeline_name = QLineEdit()
        header_row.addWidget(self.timeline_name, 1)
        editor_container.addLayout(header_row)

        body_splitter = QSplitter(Qt.Horizontal)
        body_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Scene library
        scene_column = QWidget()
        scene_layout = QVBoxLayout(scene_column)
        scene_layout.addWidget(QLabel("Available Scenes"))
        self.scene_library = QListWidget()
        self.scene_library.setSelectionMode(QListWidget.SingleSelection)
        self.scene_library.itemDoubleClicked.connect(self._add_scene_to_timeline)
        scene_layout.addWidget(self.scene_library, 1)

        self.btn_refresh_scenes = QPushButton("Refresh Scenes")
        scene_layout.addWidget(self.btn_refresh_scenes)

        # Timeline sequence
        sequence_column = QWidget()
        sequence_layout = QVBoxLayout(sequence_column)
        sequence_layout.addWidget(QLabel("Timeline Sequence"))
        self.sequence_list = QListWidget()
        self.sequence_list.setDragDropMode(QListWidget.InternalMove)
        self.sequence_list.setSelectionMode(QListWidget.SingleSelection)
        sequence_layout.addWidget(self.sequence_list, 1)

        seq_buttons = QHBoxLayout()
        self.btn_add_scene = QPushButton("Add →")
        self.btn_remove_scene = QPushButton("Remove")
        self.btn_move_up = QPushButton("Move Up")
        self.btn_move_down = QPushButton("Move Down")
        seq_buttons.addWidget(self.btn_add_scene)
        seq_buttons.addWidget(self.btn_remove_scene)
        seq_buttons.addWidget(self.btn_move_up)
        seq_buttons.addWidget(self.btn_move_down)
        sequence_layout.addLayout(seq_buttons)

        self.scene_notes = QTextEdit()
        self.scene_notes.setPlaceholderText("Notes for the selected timeline entry…")
        sequence_layout.addWidget(QLabel("Entry Notes"))
        sequence_layout.addWidget(self.scene_notes, 1)

        body_splitter.addWidget(scene_column)
        body_splitter.addWidget(sequence_column)
        editor_container.addWidget(body_splitter, 1)

        # Footer
        footer = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        footer.addWidget(self.status_label, 1)
        self.btn_save = QPushButton("Save Timeline")
        footer.addWidget(self.btn_save)
        editor_container.addLayout(footer)

        layout.addLayout(editor_container, 2)

        self.setWidget(root)

        # Signals
        self.btn_new.clicked.connect(self._create_timeline)
        self.btn_duplicate.clicked.connect(self._duplicate_timeline)
        self.btn_delete.clicked.connect(self._delete_timeline)
        self.btn_refresh_scenes.clicked.connect(self._refresh_scenes)
        self.btn_add_scene.clicked.connect(self._add_selected_library_scene)
        self.btn_remove_scene.clicked.connect(self._remove_selected_sequence_scene)
        self.btn_move_up.clicked.connect(lambda: self._shift_selected_scene(-1))
        self.btn_move_down.clicked.connect(lambda: self._shift_selected_scene(1))
        self.sequence_list.currentItemChanged.connect(
            self._on_sequence_selection_changed
        )
        self.scene_notes.textChanged.connect(self._capture_notes_change)
        self.btn_save.clicked.connect(self._save_timeline)

        self._refresh_scenes()
        self._refresh_timelines()

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    def set_registries(
        self,
        *,
        scene_registry: Optional[SceneRegistry] = None,
        timeline_registry: Optional[TimelineRegistry] = None,
    ) -> None:
        if scene_registry:
            self.scene_registry = scene_registry
        if timeline_registry:
            self.timeline_registry = timeline_registry
        self._refresh_scenes()
        self._refresh_timelines(preserve_active=True)

    # ------------------------------------------------------------------ #
    # Scene library helpers                                              #
    # ------------------------------------------------------------------ #
    def _refresh_scenes(self) -> None:
        self.scene_library.clear()
        try:
            scenes = self.scene_registry.list_scenes()
        except Exception as exc:  # pragma: no cover - GUI feedback
            self._set_status(f"Failed to load scenes: {exc}", error=True)
            return
        self._scene_cache = {}
        for scene in scenes:
            scene_id = str(scene.get("id") or scene.get("uid") or scene.get("title"))
            title = scene.get("title") or scene_id
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, {"scene_id": scene_id, "title": title})
            self.scene_library.addItem(item)
            self._scene_cache[scene_id] = {"title": title}
        self._set_status(f"Loaded {len(scenes)} scenes.")

    def _add_selected_library_scene(self) -> None:
        item = self.scene_library.currentItem()
        if not item:
            return
        self._add_scene_to_timeline(item)

    def _add_scene_to_timeline(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.UserRole) or {}
        scene_id = payload.get("scene_id")
        title = payload.get("title") or scene_id
        if not scene_id:
            return
        entry = TimelineEntry(scene_id=scene_id, title=title)
        self._append_timeline_entry(entry)
        self._set_status(f"Added scene '{title}' to sequence.")

    def _append_timeline_entry(self, entry: TimelineEntry) -> None:
        display = f"{entry.title} ({entry.scene_id})"
        item = _make_item(display, entry.to_dict())
        self.sequence_list.addItem(item)
        self.sequence_list.setCurrentItem(item)

    # ------------------------------------------------------------------ #
    # Sequence editing helpers                                          #
    # ------------------------------------------------------------------ #
    def _remove_selected_sequence_scene(self) -> None:
        item = self.sequence_list.currentItem()
        if not item:
            return
        row = self.sequence_list.row(item)
        self.sequence_list.takeItem(row)
        self.scene_notes.clear()
        self._set_status("Removed timeline entry.")

    def _shift_selected_scene(self, offset: int) -> None:
        item = self.sequence_list.currentItem()
        if not item:
            return
        row = self.sequence_list.row(item)
        target = row + offset
        if target < 0 or target >= self.sequence_list.count():
            return
        self.sequence_list.takeItem(row)
        self.sequence_list.insertItem(target, item)
        self.sequence_list.setCurrentRow(target)
        self._set_status("Reordered timeline entry.")

    def _on_sequence_selection_changed(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],
    ) -> None:
        if previous:
            self._write_notes(previous)
        if not current:
            self.scene_notes.clear()
            return
        data = current.data(Qt.UserRole) or {}
        self.scene_notes.blockSignals(True)
        self.scene_notes.setPlainText(data.get("notes", ""))
        self.scene_notes.blockSignals(False)

    def _capture_notes_change(self) -> None:
        item = self.sequence_list.currentItem()
        if not item:
            return
        self._write_notes(item, silent=True)

    def _write_notes(self, item: QListWidgetItem, silent: bool = False) -> None:
        data = item.data(Qt.UserRole) or {}
        notes = self.scene_notes.toPlainText().strip()
        data["notes"] = notes
        item.setData(Qt.UserRole, data)
        display = f"{data.get('title', data.get('scene_id'))} ({data.get('scene_id')})"
        item.setText(display)
        if not silent:
            self._set_status("Updated entry notes.")

    # ------------------------------------------------------------------ #
    # Timeline list helpers                                             #
    # ------------------------------------------------------------------ #
    def _refresh_timelines(self, preserve_active: bool = False) -> None:
        active_id = self._active_timeline_id if preserve_active else None
        self.timeline_list.clear()
        try:
            timelines = self.timeline_registry.list_timelines()
        except Exception as exc:  # pragma: no cover - GUI feedback
            self._set_status(f"Failed to load timelines: {exc}", error=True)
            return
        for timeline in timelines:
            item = QListWidgetItem(timeline.get("name") or f"Timeline {timeline['id']}")
            item.setData(Qt.UserRole, timeline)
            self.timeline_list.addItem(item)
            if active_id and timeline["id"] == active_id:
                self.timeline_list.setCurrentItem(item)
        self._set_status(f"Loaded {len(timelines)} timelines.")
        if self.timeline_list.count() and not self.timeline_list.currentItem():
            self.timeline_list.setCurrentRow(0)

    def _on_timeline_selected(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],
    ) -> None:
        if previous:
            self._maybe_prompt_save(previous)
        if not current:
            self._active_timeline_id = None
            self.timeline_name.clear()
            self.sequence_list.clear()
            self.scene_notes.clear()
            return
        payload = current.data(Qt.UserRole) or {}
        self._active_timeline_id = payload.get("id")
        self.timeline_name.setText(payload.get("name", ""))
        self.sequence_list.clear()
        for entry in payload.get("scene_order", []):
            title = entry.get("title") or entry.get("scene_id")
            display = f"{title} ({entry.get('scene_id')})"
            item = _make_item(display, entry)
            self.sequence_list.addItem(item)
        self.scene_notes.clear()
        self._set_status(f"Loaded timeline '{payload.get('name', 'Untitled')}'.")

    def _maybe_prompt_save(self, item: QListWidgetItem) -> None:
        # Placeholder for future unsaved-change detection.
        _ = item

    def _create_timeline(self) -> None:
        name, ok = QInputDialog.getText(self, "New Timeline", "Name")
        if not ok or not name.strip():
            return
        record_id = self.timeline_registry.save_timeline(
            name=name.strip(),
            scene_order=[],
            meta={"description": ""},
        )
        self._set_status(f"Created timeline '{name.strip()}'")
        self._refresh_timelines()
        items = self.timeline_list.findItems(name.strip(), Qt.MatchExactly)
        if items:
            self.timeline_list.setCurrentItem(items[0])

    def _duplicate_timeline(self) -> None:
        current = self.timeline_list.currentItem()
        if not current:
            return
        payload = current.data(Qt.UserRole) or {}
        new_name, ok = QInputDialog.getText(
            self,
            "Duplicate Timeline",
            "Name for duplicate:",
            text=f"{payload.get('name', 'Timeline')} (Copy)",
        )
        if not ok or not new_name.strip():
            return
        record_id = self.timeline_registry.save_timeline(
            name=new_name.strip(),
            scene_order=payload.get("scene_order", []),
            meta=payload.get("meta", {}),
        )
        self._set_status(f"Duplicated timeline to '{new_name.strip()}'")
        self._refresh_timelines()
        items = self.timeline_list.findItems(new_name.strip(), Qt.MatchExactly)
        if items:
            self.timeline_list.setCurrentItem(items[0])

    def _delete_timeline(self) -> None:
        current = self.timeline_list.currentItem()
        if not current:
            return
        payload = current.data(Qt.UserRole) or {}
        timeline_id = payload.get("id")
        name = payload.get("name", "Untitled")
        confirm = QMessageBox.question(
            self,
            "Delete Timeline",
            f"Delete timeline '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        if timeline_id is not None:
            self.timeline_registry.delete_timeline(timeline_id)
        row = self.timeline_list.row(current)
        self.timeline_list.takeItem(row)
        self.sequence_list.clear()
        self.timeline_name.clear()
        self._active_timeline_id = None
        self._set_status(f"Deleted timeline '{name}'.")

    # ------------------------------------------------------------------ #
    # Persistence                                                        #
    # ------------------------------------------------------------------ #
    def _serialize_sequence(self) -> List[Dict[str, str]]:
        entries: List[Dict[str, str]] = []
        for row in range(self.sequence_list.count()):
            item = self.sequence_list.item(row)
            payload = item.data(Qt.UserRole) or {}
            if payload.get("scene_id"):
                entries.append(
                    {
                        "scene_id": payload.get("scene_id"),
                        "title": payload.get("title") or payload.get("scene_id"),
                        "notes": payload.get("notes", ""),
                    }
                )
        return entries

    def _save_timeline(self) -> None:
        name = self.timeline_name.text().strip()
        if not name:
            QMessageBox.warning(
                self, "Missing Name", "Provide a timeline name before saving."
            )
            return
        entries = self._serialize_sequence()
        meta = {"entry_count": len(entries)}
        record_id = self.timeline_registry.save_timeline(
            name=name,
            scene_order=entries,
            meta=meta,
            timeline_id=self._active_timeline_id,
        )
        self._active_timeline_id = record_id
        self._set_status(f"Saved timeline '{name}' with {len(entries)} entries.")
        self._refresh_timelines(preserve_active=True)

    # ------------------------------------------------------------------ #
    # Status helpers                                                     #
    # ------------------------------------------------------------------ #
    def _set_status(self, text: str, *, error: bool = False) -> None:
        self.status_label.setText(text)
        palette = self.status_label.palette()
        color = "#c62828" if error else "#2e7d32"
        palette.setColor(self.status_label.foregroundRole(), color)
        self.status_label.setPalette(palette)
