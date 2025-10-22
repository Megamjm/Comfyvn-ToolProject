from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

LOGGER = logging.getLogger(__name__)


@dataclass
class ChoiceSpec:
    """Lightweight representation of a scenario choice edge."""

    id: str
    text: str
    target: str

    def to_dict(self) -> Dict[str, str]:
        return {"id": self.id, "text": self.text, "target": self.target}


@dataclass
class NodeSpec:
    """Canonical node payload stored by the editor."""

    id: str
    type: str = "line"
    label: str = ""
    text: str = ""
    next: Optional[str] = None
    choices: List[ChoiceSpec] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "id": self.id,
            "type": self.type,
        }
        if self.label:
            payload["label"] = self.label
        if self.text:
            payload["text"] = self.text
        if self.next:
            payload["next"] = self.next
        if self.choices:
            payload["choices"] = [choice.to_dict() for choice in self.choices]
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


class _AddNodeCommand(QUndoCommand):
    def __init__(self, editor: "NodeEditor", node: NodeSpec) -> None:
        super().__init__("Add node")
        self.editor = editor
        self.node = node

    def redo(self) -> None:
        self.editor._command_insert_node(self.node)

    def undo(self) -> None:
        self.editor._command_remove_node(self.node.id)


class _RemoveNodeCommand(QUndoCommand):
    def __init__(self, editor: "NodeEditor", node_id: str) -> None:
        super().__init__("Delete node")
        self.editor = editor
        self.node_id = node_id
        self.snapshot: Optional[NodeSpec] = None
        self.removed_links: Dict[str, Dict[str, object]] = {}

    def redo(self) -> None:
        spec = self.editor._nodes.get(self.node_id)
        if spec is None:
            return
        self.snapshot = NodeSpec(
            id=spec.id,
            type=spec.type,
            label=spec.label,
            text=spec.text,
            next=spec.next,
            choices=[ChoiceSpec(c.id, c.text, c.target) for c in spec.choices],
            metadata=dict(spec.metadata),
        )
        self.removed_links = self.editor._command_remove_node(self.node_id)

    def undo(self) -> None:
        if not self.snapshot:
            return
        self.editor._command_insert_node(
            self.snapshot, restore_links=self.removed_links
        )
        self.editor._set_current_node(self.snapshot.id)


class _SetNextCommand(QUndoCommand):
    def __init__(self, editor: "NodeEditor", node_id: str, target: Optional[str]):
        super().__init__("Set next link")
        self.editor = editor
        self.node_id = node_id
        self.target = target
        self.prev: Optional[str] = None

    def redo(self) -> None:
        self.prev = self.editor._command_set_next(self.node_id, self.target)

    def undo(self) -> None:
        self.editor._command_set_next(self.node_id, self.prev, emit=False)
        self.editor._emit_scene_changed()


class _AddChoiceCommand(QUndoCommand):
    def __init__(
        self,
        editor: "NodeEditor",
        node_id: str,
        choice: ChoiceSpec,
        *,
        index: Optional[int] = None,
    ) -> None:
        super().__init__("Add choice link")
        self.editor = editor
        self.node_id = node_id
        self.choice = choice
        self.index = index

    def redo(self) -> None:
        self.editor._command_add_choice(self.node_id, self.choice, index=self.index)

    def undo(self) -> None:
        self.editor._command_remove_choice(self.node_id, self.choice.id)


class _RemoveChoiceCommand(QUndoCommand):
    def __init__(self, editor: "NodeEditor", node_id: str, choice_id: str) -> None:
        super().__init__("Delete choice link")
        self.editor = editor
        self.node_id = node_id
        self.choice_id = choice_id
        self.snapshot: Optional[ChoiceSpec] = None
        self.index: Optional[int] = None

    def redo(self) -> None:
        self.snapshot, self.index = self.editor._command_remove_choice(
            self.node_id, self.choice_id
        )

    def undo(self) -> None:
        if self.snapshot is None:
            return
        self.editor._command_add_choice(
            self.node_id, self.snapshot, index=self.index, emit=False
        )
        self.editor._emit_scene_changed()


class NodeEditor(QWidget):
    """
    Scenario node editor widget.

    Provides create/link/delete interactions, undo/redo support, JSON import/export,
    and a Ctrl+F shortcut for node lookup.
    """

    sceneChanged = Signal(dict)
    selectionChanged = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._nodes: Dict[str, NodeSpec] = {}
        self._scene_id = "scene"
        self._start_node: Optional[str] = None
        self._current_node_id: Optional[str] = None
        self._skip_changed = False

        self.undo_stack = QUndoStack(self)

        self._build_ui()
        self._register_shortcuts()

    # ------------------------------------------------------------------
    # UI construction helpers
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(QLabel("Scene ID:"))
        self.scene_id_edit = QLineEdit(self._scene_id, self)
        header.addWidget(self.scene_id_edit, 1)

        header.addWidget(QLabel("Start Node:"))
        self.start_combo = QComboBox(self)
        self.start_combo.setEditable(False)
        self.start_combo.addItem("<none>", "")
        header.addWidget(self.start_combo, 1)

        self.btn_import = QPushButton("Import…", self)
        self.btn_export = QPushButton("Export…", self)
        self.btn_undo = QPushButton("Undo", self)
        self.btn_redo = QPushButton("Redo", self)
        header.addWidget(self.btn_import)
        header.addWidget(self.btn_export)
        header.addWidget(self.btn_undo)
        header.addWidget(self.btn_redo)

        layout.addLayout(header)

        splitter = QSplitter(Qt.Horizontal, self)
        layout.addWidget(splitter, 1)

        # Node list column
        list_container = QWidget(self)
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(4)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add Node", self)
        self.btn_delete = QPushButton("Delete Node", self)
        self.btn_link = QPushButton("Link…", self)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_delete)
        btn_row.addWidget(self.btn_link)
        list_layout.addLayout(btn_row)

        self.node_list = QListWidget(self)
        self.node_list.setSelectionMode(QListWidget.SingleSelection)
        list_layout.addWidget(self.node_list, 1)

        splitter.addWidget(list_container)

        # Detail editor column
        detail_container = QWidget(self)
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(4)

        self.detail_form = QFormLayout()
        self.detail_form.setLabelAlignment(Qt.AlignRight)
        detail_layout.addLayout(self.detail_form)

        self.node_id_label = QLabel("-", self)
        self.detail_form.addRow("Node ID:", self.node_id_label)

        self.node_type_combo = QComboBox(self)
        self.node_type_combo.addItems(
            ["line", "choice", "set", "jump", "end", "directive"]
        )
        self.detail_form.addRow("Type:", self.node_type_combo)

        self.node_label_edit = QLineEdit(self)
        self.detail_form.addRow("Label:", self.node_label_edit)

        self.node_text_edit = QPlainTextEdit(self)
        self.node_text_edit.setPlaceholderText("Line text / directive payload…")
        self.node_text_edit.setMinimumHeight(120)
        detail_layout.addWidget(QLabel("Text / Payload:", self))
        detail_layout.addWidget(self.node_text_edit, 1)

        next_row = QHBoxLayout()
        self.next_label = QLabel("<none>", self)
        next_row.addWidget(QLabel("Next:", self))
        next_row.addWidget(self.next_label, 1)
        self.btn_set_next = QPushButton("Set…", self)
        self.btn_clear_next = QPushButton("Clear", self)
        next_row.addWidget(self.btn_set_next)
        next_row.addWidget(self.btn_clear_next)
        detail_layout.addLayout(next_row)

        detail_layout.addWidget(QLabel("Choices:", self))
        self.choice_list = QListWidget(self)
        self.choice_list.setSelectionMode(QListWidget.SingleSelection)
        detail_layout.addWidget(self.choice_list, 1)

        choice_row = QHBoxLayout()
        self.btn_add_choice = QPushButton("Add Choice", self)
        self.btn_edit_choice = QPushButton("Edit", self)
        self.btn_remove_choice = QPushButton("Remove", self)
        choice_row.addWidget(self.btn_add_choice)
        choice_row.addWidget(self.btn_edit_choice)
        choice_row.addWidget(self.btn_remove_choice)
        detail_layout.addLayout(choice_row)

        splitter.addWidget(detail_container)
        splitter.setStretchFactor(1, 1)

        # Signals
        self.scene_id_edit.textEdited.connect(self._on_scene_id_changed)
        self.start_combo.currentIndexChanged.connect(self._on_start_node_changed)
        self.node_list.currentItemChanged.connect(self._on_node_selection_changed)
        self.btn_add.clicked.connect(self._prompt_add_node)
        self.btn_delete.clicked.connect(self._remove_selected_node)
        self.btn_link.clicked.connect(self._link_nodes_dialog)
        self.btn_import.clicked.connect(self._import_scene_dialog)
        self.btn_export.clicked.connect(self._export_scene_dialog)
        self.btn_undo.clicked.connect(self.undo_stack.undo)
        self.btn_redo.clicked.connect(self.undo_stack.redo)
        self.node_type_combo.currentTextChanged.connect(self._on_type_changed)
        self.node_label_edit.textEdited.connect(self._on_label_changed)
        self.node_text_edit.textChanged.connect(self._on_text_changed)
        self.btn_set_next.clicked.connect(self._prompt_set_next)
        self.btn_clear_next.clicked.connect(self._clear_next_link)
        self.choice_list.itemDoubleClicked.connect(lambda _: self._edit_choice())
        self.btn_add_choice.clicked.connect(self._add_choice_dialog)
        self.btn_edit_choice.clicked.connect(self._edit_choice)
        self.btn_remove_choice.clicked.connect(self._remove_choice)

    def _register_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo_stack.undo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self.undo_stack.redo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.undo_stack.redo)
        QShortcut(QKeySequence("Delete"), self, activated=self._remove_selected_node)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._prompt_find)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def scene(self) -> Dict[str, object]:
        """Return the scenario payload represented by the editor."""
        nodes = [spec.to_dict() for spec in self._nodes.values()]
        payload: Dict[str, object] = {
            "id": self._scene_id,
            "start": self._start_node or "",
            "nodes": nodes,
        }
        return payload

    def load_scene(self, payload: Dict[str, object]) -> None:
        """Load scene payload into the editor."""
        self._skip_changed = True
        try:
            self._nodes.clear()
            if not isinstance(payload, dict):
                raise ValueError("Scene payload must be a mapping.")
            scene_id = str(payload.get("id") or "scene")
            self._scene_id = scene_id
            self.scene_id_edit.setText(scene_id)

            nodes_raw = payload.get("nodes") or []
            if not isinstance(nodes_raw, Iterable):
                raise ValueError("nodes must be a list.")
            for raw in nodes_raw:
                if not isinstance(raw, dict):
                    continue
                node_id = str(raw.get("id") or "").strip()
                if not node_id:
                    continue
                spec = NodeSpec(
                    id=node_id,
                    type=str(raw.get("type") or "line"),
                    label=str(raw.get("label") or ""),
                    text=str(raw.get("text") or ""),
                    next=str(raw.get("next") or "").strip() or None,
                    choices=[
                        ChoiceSpec(
                            id=str(
                                choice.get("id")
                                or choice.get("label")
                                or f"{node_id}_choice"
                            ),
                            text=str(choice.get("text") or choice.get("label") or ""),
                            target=str(
                                choice.get("target") or choice.get("next") or ""
                            ),
                        )
                        for choice in raw.get("choices") or []
                        if isinstance(choice, dict)
                        and str(choice.get("target") or "").strip()
                    ],
                    metadata={
                        key: str(value)
                        for key, value in (raw.get("metadata") or {}).items()
                        if isinstance(key, str)
                    },
                )
                self._nodes[node_id] = spec

            start = str(payload.get("start") or "").strip()
            self._start_node = start if start in self._nodes else None
            self._refresh_node_list()
            if self._nodes:
                first = next(iter(self._nodes))
                self._set_current_node(self._start_node or first)
            else:
                self._set_current_node(None)
            self._emit_scene_changed()
        finally:
            QTimer.singleShot(0, self._clear_skip_flag)

    def clear(self) -> None:
        self._nodes.clear()
        self._scene_id = "scene"
        self._start_node = None
        self.scene_id_edit.setText(self._scene_id)
        self._refresh_node_list()
        self._set_current_node(None)
        self.undo_stack.clear()
        self._emit_scene_changed()

    def current_node_id(self) -> Optional[str]:
        return self._current_node_id

    def node_ids(self) -> List[str]:
        return list(self._nodes.keys())

    def focus_node(self, node_id: str) -> None:
        """Select the given node in the editor if it exists."""
        if node_id in self._nodes:
            self._set_current_node(node_id)

    # ------------------------------------------------------------------
    # Internal operations invoked by undo commands
    # ------------------------------------------------------------------
    def _command_insert_node(
        self,
        node: NodeSpec,
        *,
        restore_links: Optional[Dict[str, Dict[str, object]]] = None,
        emit: bool = True,
    ) -> None:
        self._nodes[node.id] = node
        if restore_links:
            for origin_id, data in restore_links.items():
                spec = self._nodes.get(origin_id)
                if not spec:
                    continue
                if "next" in data:
                    spec.next = data["next"] or None
                if "choices" in data:
                    spec.choices = [
                        ChoiceSpec(choice["id"], choice["text"], choice["target"])
                        for choice in data["choices"]
                        if isinstance(choice, dict)
                    ]
        self._refresh_node_list()
        self._set_current_node(node.id)
        if emit:
            self._emit_scene_changed()

    def _command_remove_node(self, node_id: str) -> Dict[str, Dict[str, object]]:
        removed_links: Dict[str, Dict[str, object]] = {}
        spec = self._nodes.pop(node_id, None)
        if spec is None:
            return removed_links
        # Remove inbound references
        for other in self._nodes.values():
            if other.next == node_id:
                removed_links.setdefault(other.id, {})["next"] = other.next
                other.next = None
            filtered: List[ChoiceSpec] = []
            removed: List[ChoiceSpec] = []
            for choice in other.choices:
                if choice.target == node_id:
                    removed.append(choice)
                else:
                    filtered.append(choice)
            if removed:
                removed_links.setdefault(other.id, {})["choices"] = [
                    c.to_dict() for c in other.choices
                ]
                other.choices = filtered
        if self._start_node == node_id:
            self._start_node = None
        self._refresh_node_list()
        self._set_current_node(None)
        self._emit_scene_changed()
        return removed_links

    def _command_set_next(
        self, node_id: Optional[str], target: Optional[str], *, emit: bool = True
    ) -> Optional[str]:
        if not node_id:
            return None
        spec = self._nodes.get(node_id)
        if spec is None:
            return None
        previous = spec.next
        spec.next = target
        if emit:
            self._emit_scene_changed()
            if self._current_node_id == node_id:
                self._refresh_detail_panel(spec)
        return previous

    def _command_add_choice(
        self,
        node_id: Optional[str],
        choice: ChoiceSpec,
        *,
        index: Optional[int] = None,
        emit: bool = True,
    ) -> None:
        if not node_id:
            return
        spec = self._nodes.get(node_id)
        if spec is None:
            return
        if index is None or index >= len(spec.choices):
            spec.choices.append(choice)
        else:
            spec.choices.insert(index, choice)
        if emit:
            self._emit_scene_changed()
            if self._current_node_id == node_id:
                self._refresh_choices(spec)

    def _command_remove_choice(
        self, node_id: Optional[str], choice_id: str
    ) -> tuple[Optional[ChoiceSpec], Optional[int]]:
        if not node_id:
            return None, None
        spec = self._nodes.get(node_id)
        if spec is None:
            return None, None
        for index, choice in enumerate(spec.choices):
            if choice.id == choice_id:
                removed = spec.choices.pop(index)
                self._emit_scene_changed()
                if self._current_node_id == node_id:
                    self._refresh_choices(spec)
                return removed, index
        return None, None

    def _push_command(self, command: QUndoCommand) -> None:
        if not self._current_node_id and not isinstance(command, _AddNodeCommand):
            QMessageBox.information(
                self,
                "Node Editor",
                "Select a node first.",
            )
            return
        self.undo_stack.push(command)

    def _clear_skip_flag(self) -> None:
        self._skip_changed = False

    # ------------------------------------------------------------------
    # UI event handlers
    # ------------------------------------------------------------------
    def _refresh_node_list(self) -> None:
        self.start_combo.blockSignals(True)
        current_start = self._start_node
        self.start_combo.clear()
        self.start_combo.addItem("<none>", "")
        for node_id in sorted(self._nodes.keys()):
            self.start_combo.addItem(node_id, node_id)
        if current_start and current_start in self._nodes:
            idx = self.start_combo.findData(current_start)
            if idx >= 0:
                self.start_combo.setCurrentIndex(idx)
        else:
            self.start_combo.setCurrentIndex(0)
        self.start_combo.blockSignals(False)

        self.node_list.blockSignals(True)
        self.node_list.clear()
        for node_id, spec in sorted(self._nodes.items()):
            item = QListWidgetItem(f"{node_id}  —  {spec.type}")
            item.setData(Qt.UserRole, node_id)
            self.node_list.addItem(item)
            if node_id == self._current_node_id:
                item.setSelected(True)
        self.node_list.blockSignals(False)

    def _set_current_node(self, node_id: Optional[str]) -> None:
        self._current_node_id = node_id if node_id in self._nodes else None
        if self._current_node_id:
            spec = self._nodes[self._current_node_id]
            self._refresh_detail_panel(spec)
            for index in range(self.node_list.count()):
                item = self.node_list.item(index)
                if item.data(Qt.UserRole) == self._current_node_id:
                    self.node_list.setCurrentItem(item)
                    break
            self.selectionChanged.emit(self._current_node_id)
        else:
            self._clear_detail_panel()

    def _refresh_detail_panel(self, spec: NodeSpec) -> None:
        self.node_id_label.setText(spec.id)
        self.node_type_combo.blockSignals(True)
        index = self.node_type_combo.findText(spec.type)
        if index < 0:
            index = self.node_type_combo.findText("line")
        self.node_type_combo.setCurrentIndex(max(index, 0))
        self.node_type_combo.blockSignals(False)
        self.node_label_edit.blockSignals(True)
        self.node_label_edit.setText(spec.label)
        self.node_label_edit.blockSignals(False)
        self.node_text_edit.blockSignals(True)
        self.node_text_edit.setPlainText(spec.text)
        self.node_text_edit.blockSignals(False)
        self._refresh_next(spec)
        self._refresh_choices(spec)

    def _refresh_next(self, spec: NodeSpec) -> None:
        self.next_label.setText(spec.next or "<none>")

    def _refresh_choices(self, spec: NodeSpec) -> None:
        self.choice_list.blockSignals(True)
        self.choice_list.clear()
        for choice in spec.choices:
            label = choice.id or choice.text or choice.target
            item = QListWidgetItem(f"{label} → {choice.target}")
            item.setData(Qt.UserRole, choice.id)
            self.choice_list.addItem(item)
        self.choice_list.blockSignals(False)

    def _clear_detail_panel(self) -> None:
        self.node_id_label.setText("-")
        self.node_type_combo.blockSignals(True)
        self.node_type_combo.setCurrentIndex(0)
        self.node_type_combo.blockSignals(False)
        self.node_label_edit.blockSignals(True)
        self.node_label_edit.clear()
        self.node_label_edit.blockSignals(False)
        self.node_text_edit.blockSignals(True)
        self.node_text_edit.clear()
        self.node_text_edit.blockSignals(False)
        self.next_label.setText("<none>")
        self.choice_list.clear()

    def _on_scene_id_changed(self, text: str) -> None:
        if self._skip_changed:
            return
        self._scene_id = text.strip() or "scene"
        self._emit_scene_changed()

    def _on_start_node_changed(self, index: int) -> None:
        value = self.start_combo.itemData(index)
        self._start_node = value or None
        if not self._skip_changed:
            self._emit_scene_changed()

    def _on_node_selection_changed(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],  # noqa: ARG002
    ) -> None:
        node_id = current.data(Qt.UserRole) if current else None
        self._set_current_node(node_id)

    def _prompt_add_node(self) -> None:
        node_id, ok = QInputDialog.getText(
            self,
            "Add Node",
            "Node identifier:",
            text=f"node{len(self._nodes) + 1}",
        )
        if not ok or not node_id.strip():
            return
        node_id = node_id.strip()
        if node_id in self._nodes:
            QMessageBox.warning(
                self,
                "Add Node",
                f"Node '{node_id}' already exists.",
            )
            return
        spec = NodeSpec(id=node_id)
        self._push_command(_AddNodeCommand(self, spec))

    def _remove_selected_node(self) -> None:
        if not self._current_node_id:
            return
        confirm = QMessageBox.question(
            self,
            "Delete Node",
            f"Delete node '{self._current_node_id}'?",
        )
        if confirm != QMessageBox.Yes:
            return
        self._push_command(_RemoveNodeCommand(self, self._current_node_id))

    def _link_nodes_dialog(self) -> None:
        if not self._current_node_id:
            return
        if not self._nodes:
            return
        items = sorted(
            node_id for node_id in self._nodes if node_id != self._current_node_id
        )
        if not items:
            QMessageBox.information(
                self,
                "Link Nodes",
                "No other nodes available to link.",
            )
            return
        target, ok = QInputDialog.getItem(
            self, "Link Nodes", "Target node:", items, editable=False
        )
        if not ok or not target:
            return
        action = QMessageBox.question(
            self,
            "Link Type",
            f"Create sequential link to '{target}'?\n"
            "Choose 'No' to create a branching choice instead.",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if action == QMessageBox.Cancel:
            return
        if action == QMessageBox.Yes:
            self._push_command(_SetNextCommand(self, self._current_node_id, target))
            return
        self._add_choice_dialog(target_node=target)

    def _prompt_set_next(self) -> None:
        if not self._current_node_id:
            return
        available = sorted(
            node_id for node_id in self._nodes if node_id != self._current_node_id
        )
        target, ok = QInputDialog.getItem(
            self, "Set Next", "Next node:", available, editable=False
        )
        if not ok:
            return
        self._push_command(_SetNextCommand(self, self._current_node_id, target))

    def _add_choice_dialog(self, *, target_node: Optional[str] = None) -> None:
        if not self._current_node_id:
            return
        node_ids = sorted(
            node_id for node_id in self._nodes if node_id != self._current_node_id
        )
        if not node_ids:
            QMessageBox.information(
                self,
                "Add Choice",
                "No other nodes available to target.",
            )
            return
        if target_node is None:
            target_node, ok = QInputDialog.getItem(
                self, "Choice Target", "Target node:", node_ids, editable=False
            )
            if not ok or not target_node:
                return
        choice_id, ok_id = QInputDialog.getText(self, "Choice ID", "Choice identifier:")
        if not ok_id or not choice_id.strip():
            return
        choice_text, ok_text = QInputDialog.getText(
            self, "Choice Text", "Choice text / label:"
        )
        if not ok_text:
            return
        choice = ChoiceSpec(
            id=choice_id.strip(), text=choice_text.strip(), target=target_node
        )
        self._push_command(_AddChoiceCommand(self, self._current_node_id, choice))

    def _edit_choice(self) -> None:
        if not self._current_node_id:
            return
        item = self.choice_list.currentItem()
        if not item:
            return
        choice_id = item.data(Qt.UserRole)
        spec = self._nodes.get(self._current_node_id)
        if not spec:
            return
        for index, choice in enumerate(spec.choices):
            if choice.id == choice_id:
                new_id, ok_id = QInputDialog.getText(
                    self, "Choice ID", "Choice identifier:", text=choice.id
                )
                if not ok_id or not new_id.strip():
                    return
                new_text, ok_text = QInputDialog.getText(
                    self, "Choice Text", "Choice text:", text=choice.text
                )
                if not ok_text:
                    return
                new_target, ok_target = QInputDialog.getItem(
                    self,
                    "Choice Target",
                    "Target node:",
                    sorted(self._nodes.keys()),
                    editable=False,
                )
                if not ok_target or not new_target:
                    return
                spec.choices[index] = ChoiceSpec(
                    id=new_id.strip(), text=new_text.strip(), target=new_target
                )
                self._emit_scene_changed()
                self._refresh_choices(spec)
                return

    def _remove_choice(self) -> None:
        if not self._current_node_id:
            return
        item = self.choice_list.currentItem()
        if not item:
            return
        choice_id = item.data(Qt.UserRole)
        self._push_command(_RemoveChoiceCommand(self, self._current_node_id, choice_id))

    def _clear_next_link(self) -> None:
        if not self._current_node_id:
            return
        self._push_command(_SetNextCommand(self, self._current_node_id, None))

    def _on_type_changed(self, value: str) -> None:
        if not self._current_node_id:
            return
        spec = self._nodes.get(self._current_node_id)
        if spec:
            spec.type = value
            self._emit_scene_changed()
            self._refresh_node_list()

    def _on_label_changed(self, text: str) -> None:
        if not self._current_node_id:
            return
        spec = self._nodes.get(self._current_node_id)
        if spec:
            spec.label = text
            self._emit_scene_changed()

    def _on_text_changed(self) -> None:
        if not self._current_node_id:
            return
        spec = self._nodes.get(self._current_node_id)
        if spec:
            spec.text = self.node_text_edit.toPlainText()
            self._emit_scene_changed()

    def _prompt_find(self) -> None:
        if not self._nodes:
            return
        node_id, ok = QInputDialog.getText(self, "Find Node", "Node id:")
        if not ok or not node_id:
            return
        node_id = node_id.strip()
        if node_id not in self._nodes:
            QMessageBox.information(self, "Find Node", f"No node with id '{node_id}'.")
            return
        self._set_current_node(node_id)

    # ------------------------------------------------------------------
    # Import / export helpers
    # ------------------------------------------------------------------
    def _import_scene_dialog(self) -> None:
        path, ok = QFileDialog.getOpenFileName(
            self,
            "Import Scene",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if not ok or not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            payload = json.loads(text)
        except Exception as exc:  # pragma: no cover - user feedback
            LOGGER.error("Failed to import scene: %s", exc)
            QMessageBox.critical(self, "Import Scene", f"Failed to import: {exc}")
            return
        self.load_scene(payload)

    def _export_scene_dialog(self) -> None:
        if not self._nodes:
            QMessageBox.information(
                self, "Export Scene", "Create at least one node before exporting."
            )
            return
        path, ok = QFileDialog.getSaveFileName(
            self,
            "Export Scene",
            f"{self._scene_id or 'scene'}.json",
            "JSON Files (*.json);;All Files (*)",
        )
        if not ok or not path:
            return
        try:
            data = self.scene()
            text = json.dumps(data, indent=2, ensure_ascii=False)
            Path(path).write_text(text, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - user feedback
            LOGGER.error("Failed to export scene: %s", exc)
            QMessageBox.critical(self, "Export Scene", f"Failed to export: {exc}")

    # ------------------------------------------------------------------
    def _emit_scene_changed(self) -> None:
        if self._skip_changed:
            return
        snapshot = self.scene()
        self.sceneChanged.emit(snapshot)


__all__ = ["NodeEditor", "NodeSpec", "ChoiceSpec"]
