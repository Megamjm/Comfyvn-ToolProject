from __future__ import annotations

import json
import logging
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Set

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from comfyvn.gui.services.server_bridge import ServerBridge

LOGGER = logging.getLogger(__name__)


class RunnerPanel(QWidget):
    """
    Scenario runner stepper with breakpoint and variable watch support.

    Executes `/api/scenario/run/step`, presenting state transitions and exposing
    live variable snapshots. Breakpoints can be registered on node identifiers
    to pause auto-running sequences.
    """

    nodeFocused = Signal(str)
    stateUpdated = Signal(dict)

    def __init__(
        self,
        bridge: Optional[ServerBridge] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.bridge = bridge or ServerBridge()
        self._scene: Optional[Dict[str, object]] = None
        self._scene_provider: Optional[Callable[[], Mapping[str, object]]] = None
        self._state: Optional[Dict[str, object]] = None
        self._breakpoints: Set[str] = set()
        self._node_catalog: List[str] = []
        self._auto_running = False
        self._finished = False
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        controls = QHBoxLayout()
        self.btn_reset = QPushButton("Reset", self)
        self.btn_step = QPushButton("Step", self)
        self.btn_run = QPushButton("Run", self)
        controls.addWidget(self.btn_reset)
        controls.addWidget(self.btn_step)
        controls.addWidget(self.btn_run)

        controls.addSpacing(12)
        controls.addWidget(QLabel("Seed:", self))
        self.seed_edit = QLineEdit(self)
        self.seed_edit.setFixedWidth(80)
        self.seed_edit.setPlaceholderText("auto")
        controls.addWidget(self.seed_edit)

        controls.addSpacing(12)
        controls.addWidget(QLabel("Choice:", self))
        self.choice_combo = QComboBox(self)
        self.choice_combo.addItem("Auto (weighted)", None)
        self.choice_combo.setMinimumWidth(220)
        controls.addWidget(self.choice_combo, 1)

        layout.addLayout(controls)

        splitter = QSplitter(Qt.Horizontal, self)
        layout.addWidget(splitter, 1)

        # Breakpoints column
        bp_container = QWidget(self)
        bp_layout = QVBoxLayout(bp_container)
        bp_layout.setContentsMargins(0, 0, 0, 0)
        bp_layout.addWidget(QLabel("Breakpoints", self))

        self.breakpoint_list = QListWidget(self)
        self.breakpoint_list.setSelectionMode(QListWidget.SingleSelection)
        bp_layout.addWidget(self.breakpoint_list, 1)

        bp_buttons = QHBoxLayout()
        self.btn_add_breakpoint = QPushButton("Add…", self)
        self.btn_remove_breakpoint = QPushButton("Remove", self)
        self.btn_clear_breakpoints = QPushButton("Clear", self)
        bp_buttons.addWidget(self.btn_add_breakpoint)
        bp_buttons.addWidget(self.btn_remove_breakpoint)
        bp_buttons.addWidget(self.btn_clear_breakpoints)
        bp_layout.addLayout(bp_buttons)

        splitter.addWidget(bp_container)

        # Watch column
        watch_container = QWidget(self)
        watch_layout = QVBoxLayout(watch_container)
        watch_layout.setContentsMargins(0, 0, 0, 0)
        watch_layout.addWidget(QLabel("Variables Watch", self))
        self.watch_tree = QTreeWidget(self)
        self.watch_tree.setColumnCount(2)
        self.watch_tree.setHeaderLabels(["Variable", "Value"])
        self.watch_tree.setUniformRowHeights(True)
        watch_layout.addWidget(self.watch_tree, 1)

        splitter.addWidget(watch_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)

        self.status_label = QLabel("Load a scene to begin stepping.", self)
        layout.addWidget(self.status_label)

        # Connections
        self.btn_reset.clicked.connect(self.reset)
        self.btn_step.clicked.connect(self.step_once)
        self.btn_run.clicked.connect(self.run_until_breakpoint)
        self.btn_add_breakpoint.clicked.connect(self._prompt_breakpoint)
        self.btn_remove_breakpoint.clicked.connect(self._remove_selected_breakpoint)
        self.btn_clear_breakpoints.clicked.connect(self.clear_breakpoints)

    # ------------------------------------------------------------------
    def set_scene(self, scene: Mapping[str, object]) -> None:
        """Attach a scenario payload for stepping."""
        if not isinstance(scene, Mapping):
            raise TypeError("scene payload must be a mapping")
        self._scene = json.loads(json.dumps(scene))
        self._state = None
        self._finished = False
        self.choice_combo.clear()
        self.choice_combo.addItem("Auto (weighted)", None)
        self._log("Scene loaded.")
        self.status_label.setText("Scene loaded. Ready to step.")

    def set_scene_provider(
        self, provider: Optional[Callable[[], Mapping[str, object]]]
    ) -> None:
        """Provide a callable that returns the latest scene payload on demand."""
        self._scene_provider = provider

    def set_node_catalog(self, nodes: Iterable[str]) -> None:
        self._node_catalog = sorted({str(node) for node in nodes if node})

    def add_breakpoint(self, node_id: str) -> None:
        node_id = str(node_id)
        if not node_id:
            return
        if node_id in self._breakpoints:
            return
        self._breakpoints.add(node_id)
        item = QListWidgetItem(node_id)
        item.setData(Qt.UserRole, node_id)
        self.breakpoint_list.addItem(item)

    def clear_breakpoints(self) -> None:
        self._breakpoints.clear()
        self.breakpoint_list.clear()

    def reset(self) -> None:
        self._state = None
        self._finished = False
        self.choice_combo.clear()
        self.choice_combo.addItem("Auto (weighted)", None)
        self.watch_tree.clear()
        self.status_label.setText("State reset.")
        self._log("State reset.")

    # ------------------------------------------------------------------
    def step_once(self) -> None:
        if self._auto_running:
            return
        self._perform_step()

    def run_until_breakpoint(self) -> None:
        if self._auto_running:
            return
        self._auto_running = True
        try:
            iterations = 0
            while iterations < 500:
                result = self._perform_step(auto_mode=True)
                if not result:
                    break
                if result.get("breakpoint_hit") or result.get("finished"):
                    break
                iterations += 1
            if iterations >= 500:
                self._log("Run aborted after 500 iterations (safety stop).")
        finally:
            self._auto_running = False

    # ------------------------------------------------------------------
    def _perform_step(self, *, auto_mode: bool = False) -> Optional[Dict[str, object]]:
        if not self._scene:
            if self._scene_provider:
                try:
                    scene_payload = self._scene_provider()
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.error("Scene provider failed: %s", exc)
                    QMessageBox.critical(
                        self,
                        "Scenario Runner",
                        f"Scene provider failed: {exc}",
                    )
                    return None
                if scene_payload:
                    self.set_scene(scene_payload)
            if not self._scene:
                QMessageBox.information(
                    self,
                    "Scenario Runner",
                    "Load a scene in the node editor before stepping.",
                )
                return None

        if self._scene_provider:
            try:
                scene_payload = self._scene_provider()
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.error("Scene provider failed: %s", exc)
                QMessageBox.critical(
                    self,
                    "Scenario Runner",
                    f"Scene provider failed: {exc}",
                )
                return None
            if scene_payload:
                self._scene = json.loads(json.dumps(scene_payload))

        payload: Dict[str, object] = {"scene": self._scene}

        if self._state is not None:
            payload["state"] = self._state

        seed_text = self.seed_edit.text().strip()
        if seed_text:
            try:
                payload["seed"] = int(seed_text)
            except ValueError:
                QMessageBox.warning(self, "Scenario Runner", "Seed must be an integer.")
                return None

        choice_id = self.choice_combo.currentData()
        if isinstance(choice_id, str) and choice_id:
            payload["choice_id"] = choice_id

        try:
            result = self.bridge.post_json(
                "/api/scenario/run/step", payload, timeout=6.0, default=None
            )
        except Exception as exc:  # pragma: no cover - network failure
            LOGGER.error("Scenario step failed: %s", exc)
            QMessageBox.critical(self, "Scenario Runner", f"Request failed: {exc}")
            return None

        if not isinstance(result, dict) or not result.get("ok"):
            detail = ""
            if isinstance(result, dict):
                detail = json.dumps(result.get("detail") or result, indent=2)
            QMessageBox.critical(
                self,
                "Scenario Runner",
                f"Step failed.\n{detail}",
            )
            return None

        self._state = result.get("state") or {}
        self._finished = bool(result.get("finished"))
        node = result.get("node") or {}
        node_id = str(node.get("id") or "")
        self._log_step(node, result.get("choices") or [], auto_mode=auto_mode)
        self._refresh_choice_options(result.get("choices") or [])
        self._refresh_watch()
        if node_id:
            self.nodeFocused.emit(node_id)
        self.stateUpdated.emit(dict(self._state))

        breakpoint_hit = node_id in self._breakpoints if node_id else False
        if breakpoint_hit:
            self._log(f"Breakpoint hit at node '{node_id}'.")
            self.status_label.setText(f"Breakpoint hit at {node_id}.")
        elif self._finished:
            self.status_label.setText("Scenario finished.")
        else:
            self.status_label.setText(f"Active node: {node_id or '<unknown>'}")

        return {
            "breakpoint_hit": breakpoint_hit,
            "finished": self._finished,
            "node": node,
        }

    # ------------------------------------------------------------------
    def _refresh_choice_options(self, choices: Iterable[Mapping[str, object]]) -> None:
        current_choice = self.choice_combo.currentData()
        self.choice_combo.blockSignals(True)
        self.choice_combo.clear()
        self.choice_combo.addItem("Auto (weighted)", None)
        for choice in choices:
            choice_id = str(choice.get("id") or choice.get("target") or "")
            label = choice.get("text") or choice.get("label") or choice_id
            target = choice.get("target") or ""
            display = f"{choice_id or label} → {target}"
            self.choice_combo.addItem(display, choice_id or None)
        index = 0
        if current_choice:
            idx = self.choice_combo.findData(current_choice)
            if idx >= 0:
                index = idx
        self.choice_combo.setCurrentIndex(index)
        self.choice_combo.blockSignals(False)

    def _refresh_watch(self) -> None:
        self.watch_tree.clear()
        variables = None
        if isinstance(self._state, Mapping):
            raw_vars = self._state.get("variables")
            if isinstance(raw_vars, Mapping):
                variables = raw_vars
        if not variables:
            return
        for key in sorted(variables.keys()):
            value = variables[key]
            if isinstance(value, (dict, list)):
                pretty = json.dumps(value, ensure_ascii=False)
            else:
                pretty = str(value)
            row = QTreeWidgetItem([str(key), pretty])
            self.watch_tree.addTopLevelItem(row)

    def _log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _log_step(
        self,
        node: Mapping[str, object],
        choices: Iterable[Mapping[str, object]],
        *,
        auto_mode: bool,
    ) -> None:
        node_id = node.get("id") if isinstance(node, Mapping) else None
        node_type = node.get("type") if isinstance(node, Mapping) else None
        line = (
            f"{'Auto' if auto_mode else 'Step'} → node={node_id!s} type={node_type!s}"
        )
        self._log(line)
        choice_lines = []
        for choice in choices:
            choice_id = choice.get("id") or choice.get("target")
            label = choice.get("text") or choice.get("label")
            target = choice.get("target")
            choice_lines.append(f"  - {choice_id} ({label}) → {target}")
        if choice_lines:
            self._log("\n".join(choice_lines))

    # ------------------------------------------------------------------
    def _prompt_breakpoint(self) -> None:
        if not self._node_catalog:
            QMessageBox.information(
                self,
                "Breakpoints",
                "No nodes available. Create nodes first.",
            )
            return
        node_id, ok = QInputDialog.getItem(
            self,
            "Add Breakpoint",
            "Node id:",
            self._node_catalog,
            editable=False,
        )
        if not ok or not node_id:
            return
        self.add_breakpoint(node_id)

    def _remove_selected_breakpoint(self) -> None:
        item = self.breakpoint_list.currentItem()
        if not item:
            return
        node_id = item.data(Qt.UserRole)
        if node_id in self._breakpoints:
            self._breakpoints.remove(node_id)
        row = self.breakpoint_list.row(item)
        self.breakpoint_list.takeItem(row)


__all__ = ["RunnerPanel"]
