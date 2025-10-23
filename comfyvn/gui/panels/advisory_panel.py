from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from comfyvn.config.baseurl_authority import default_base_url

LOGGER = logging.getLogger("comfyvn.gui.advisory")


_LEVEL_COLORS = {
    "block": QColor("#f8d7da"),
    "warn": QColor("#fff3cd"),
    "info": QColor("#d1ecf1"),
}


class AdvisoryPanel(QWidget):
    """Settings panel for liability acknowledgement and advisory pre-flight checks."""

    def __init__(self, base: str | None = None) -> None:
        super().__init__()
        self.base = (base or default_base_url()).rstrip("/")
        self._findings_cache: List[Dict] = []
        self._gate_snapshot: Dict[str, Any] = {}

        root = QVBoxLayout(self)
        root.addWidget(self._build_gate_group())
        root.addWidget(self._build_preflight_group(), 1)
        root.addStretch(1)

        self._load_gate_status()
        self._refresh_findings(fetch=True)

    # ------------------------------------------------------------------
    # Gate group
    # ------------------------------------------------------------------
    def _build_gate_group(self) -> QGroupBox:
        self.gate_status_label = QLabel("Loading gate status…", self)
        self.gate_status_label.setWordWrap(True)

        self.override_checkbox = QCheckBox("Request override during evaluation", self)
        self.override_checkbox.setToolTip(
            "When checked, the evaluation request records an override intent."
        )

        ack_button = QPushButton("Acknowledge Legal Terms…", self)
        ack_button.clicked.connect(self._acknowledge)

        evaluate_button = QPushButton("Evaluate Selected Action", self)
        evaluate_button.clicked.connect(self._evaluate_action)

        status_layout = QVBoxLayout()
        status_layout.addWidget(self.gate_status_label)
        status_layout.addWidget(self.override_checkbox)

        controls = QHBoxLayout()
        controls.addWidget(ack_button)
        controls.addWidget(evaluate_button)
        controls.addStretch(1)

        status_layout.addLayout(controls)

        box = QGroupBox("Liability Gate", self)
        box.setLayout(status_layout)
        return box

    # ------------------------------------------------------------------
    # Pre-flight group
    # ------------------------------------------------------------------
    def _build_preflight_group(self) -> QGroupBox:
        self.action_combo = QComboBox(self)
        self.action_combo.addItem("Export Bundle", "export.bundle")
        self.action_combo.addItem("Import Bundle", "import.bundle")
        self.action_combo.addItem("Import Archive", "import.archive")
        self.action_combo.currentIndexChanged.connect(
            lambda _: self._refresh_findings(fetch=False)
        )

        refresh_button = QPushButton("Refresh Findings", self)
        refresh_button.clicked.connect(lambda: self._refresh_findings(fetch=True))

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Action:", self))
        header_row.addWidget(self.action_combo)
        header_row.addStretch(1)
        header_row.addWidget(refresh_button)

        self.findings_table = QTableWidget(0, 4, self)
        self.findings_table.setHorizontalHeaderLabels(
            ["Level", "Kind", "Message", "Target"]
        )
        self.findings_table.horizontalHeader().setStretchLastSection(True)
        self.findings_table.setSelectionBehavior(QTableWidget.SelectRows)

        self.preflight_status_label = QLabel("No advisory findings loaded yet.", self)
        self.preflight_status_label.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addLayout(header_row)
        layout.addWidget(self.findings_table, 1)
        layout.addWidget(self.preflight_status_label)

        box = QGroupBox("Import/Export Pre-flight", self)
        box.setLayout(layout)
        return box

    # ------------------------------------------------------------------
    # Gate handlers
    # ------------------------------------------------------------------
    def _load_gate_status(self) -> None:
        try:
            resp = requests.get(self.base + "/api/policy/status", timeout=3)
        except Exception as exc:  # pragma: no cover - GUI runtime
            LOGGER.error("Policy status request failed: %s", exc)
            self.gate_status_label.setText(f"Policy status unavailable: {exc}")
            return

        if resp.status_code >= 400:
            LOGGER.warning("Policy status failed: %s %s", resp.status_code, resp.text)
            self.gate_status_label.setText(
                f"Policy status error: {resp.status_code} {resp.text}"
            )
            return

        data = resp.json()
        self._gate_snapshot = data
        status = data.get("status", {}) or {}
        requires_ack = bool(status.get("requires_ack"))
        acknowledged = bool(data.get("ack") or status.get("ack_legal_v1"))
        name = (data.get("name") or status.get("ack_user") or "").strip()
        timestamp = data.get("at") or status.get("ack_timestamp")
        override_enabled = bool(status.get("warn_override_enabled", True))
        message = data.get("message") or (
            "Legal acknowledgement required before continuing."
            if requires_ack
            else "Legal acknowledgement recorded; continue responsibly."
        )

        summary_parts = [f"Requires acknowledgement: {'yes' if requires_ack else 'no'}"]
        if acknowledged:
            detail_bits: List[str] = []
            if name:
                detail_bits.append(f"by {name}")
            if timestamp:
                try:
                    when = datetime.fromtimestamp(float(timestamp))
                    detail_bits.append(
                        f"at {when.isoformat(sep=' ', timespec='seconds')}"
                    )
                except Exception:
                    detail_bits.append(f"at {timestamp}")
            if detail_bits:
                summary_parts.append(" • acknowledged " + " ".join(detail_bits))
        self.override_checkbox.setEnabled(override_enabled)
        self.override_checkbox.setChecked(False)
        self.gate_status_label.setText(f"{message}\n{' '.join(summary_parts)}")

    def _acknowledge(self) -> None:
        from PySide6.QtWidgets import (
            QInputDialog,
        )  # local import to avoid heavy startup

        user, ok = QInputDialog.getText(
            self,
            "Acknowledge Legal Terms",
            "Enter your name or initials:",
        )
        if not ok:
            return
        notes, ok_notes = QInputDialog.getText(
            self,
            "Optional Notes",
            "Add acknowledgement notes (optional):",
        )
        display_name = user.strip() or "anonymous"
        payload: Dict[str, str] = {"user": display_name, "name": display_name}
        waiver_snapshot = getattr(self, "_gate_snapshot", {}) or {}
        waiver_message = waiver_snapshot.get("message") or (
            "By acknowledging these terms you accept full responsibility for any "
            "imported or exported content produced with ComfyVN Studio."
        )
        waiver_details = (
            "<b>Please review before continuing:</b><br>"
            "<ul>"
            "<li>Imported chats, personas, and assets may contain third-party IP or personal data.</li>"
            "<li>You are responsible for verifying distribution rights and consent.</li>"
            "<li>Exports include provenance records for compliance; share them responsibly.</li>"
            "</ul>"
            "<p>Click “Continue” only if you agree to these terms.</p>"
        )
        waiver_box = QMessageBox(self)
        waiver_box.setWindowTitle("Review Liability Terms")
        waiver_box.setIcon(QMessageBox.Warning)
        waiver_box.setTextFormat(Qt.RichText)
        waiver_box.setText(f"{waiver_message}<br><br>{waiver_details}")
        waiver_box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        waiver_box.setDefaultButton(QMessageBox.Cancel)
        decision = waiver_box.exec()
        if decision != QMessageBox.Ok:
            return
        if ok_notes and notes.strip():
            payload["notes"] = notes.strip()
        try:
            resp = requests.post(self.base + "/api/policy/ack", json=payload, timeout=5)
        except Exception as exc:  # pragma: no cover - GUI runtime
            LOGGER.error("Policy acknowledgement failed: %s", exc)
            QMessageBox.warning(
                self,
                "Liability Gate",
                f"Acknowledgement failed: {exc}",
            )
            return
        if resp.status_code >= 400:
            LOGGER.warning(
                "Policy acknowledgement error %s: %s", resp.status_code, resp.text
            )
            QMessageBox.warning(
                self,
                "Liability Gate",
                f"Acknowledgement error: {resp.status_code} {resp.text}",
            )
            return
        QMessageBox.information(
            self,
            "Liability Gate",
            "Acknowledgement recorded. Thank you.",
        )
        self._load_gate_status()

    def _evaluate_action(self) -> None:
        action = self.action_combo.currentData()
        payload = {
            "action": action or "export.bundle",
            "override": self.override_checkbox.isChecked(),
        }
        try:
            resp = requests.post(
                self.base + "/api/policy/evaluate", json=payload, timeout=4
            )
        except Exception as exc:  # pragma: no cover - GUI runtime
            LOGGER.error("Policy evaluation failed: %s", exc)
            QMessageBox.warning(
                self,
                "Liability Gate",
                f"Evaluation failed: {exc}",
            )
            return
        if resp.status_code >= 400:
            LOGGER.warning(
                "Policy evaluation error %s: %s", resp.status_code, resp.text
            )
            QMessageBox.warning(
                self,
                "Liability Gate",
                f"Evaluation error: {resp.status_code} {resp.text}",
            )
            return
        payload = resp.json()
        warnings = payload.get("warnings") or []
        allow = payload.get("allow")
        message = "\n".join(warnings) if warnings else "No warnings reported."
        QMessageBox.information(
            self,
            "Liability Gate Evaluation",
            f"Allow: {allow}\n{message}",
        )

    # ------------------------------------------------------------------
    # Findings helpers
    # ------------------------------------------------------------------
    def _refresh_findings(self, *, fetch: bool) -> None:
        if fetch:
            self._findings_cache = self._load_findings()
        filtered = self._filter_findings(self._findings_cache)
        self._populate_table(filtered)
        self._update_status_label(filtered)

    def _load_findings(self) -> List[Dict]:
        try:
            resp = requests.get(self.base + "/api/advisory/logs", timeout=4)
        except Exception as exc:  # pragma: no cover - GUI runtime
            LOGGER.error("Advisory logs request failed: %s", exc)
            self.preflight_status_label.setText(
                f"Failed to refresh advisory logs: {exc}"
            )
            return []
        if resp.status_code >= 400:
            LOGGER.warning("Advisory logs error %s: %s", resp.status_code, resp.text)
            self.preflight_status_label.setText(
                f"Advisory logs error: {resp.status_code} {resp.text}"
            )
            return []
        payload = resp.json()
        return list(payload.get("items") or [])

    def _filter_findings(self, items: List[Dict]) -> List[Dict]:
        scope = self.action_combo.currentData() or ""
        if not scope:
            return items
        filtered: List[Dict] = []
        for item in items:
            detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
            source = str(detail.get("source") or "").lower()
            if scope.lower() in source:
                filtered.append(item)
                continue
            target = str(item.get("target_id") or "").lower()
            if scope.startswith("export") and "export" in source:
                filtered.append(item)
                continue
            if scope.startswith("import") and "import" in source:
                filtered.append(item)
                continue
            if scope.startswith("import") and "import" in target:
                filtered.append(item)
                continue
            if scope.startswith("export") and "export" in target:
                filtered.append(item)
        return filtered

    def _populate_table(self, findings: List[Dict]) -> None:
        self.findings_table.setRowCount(len(findings))
        for row, item in enumerate(findings):
            level = self._to_level(item.get("severity"))
            self._set_item(row, 0, level.upper())
            self._set_item(row, 1, item.get("kind") or "")
            self._set_item(row, 2, item.get("message") or "")
            self._set_item(row, 3, item.get("target_id") or "")
            self._color_row(row, level)

    def _set_item(self, row: int, column: int, value: str) -> None:
        item = QTableWidgetItem(str(value or ""))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.findings_table.setItem(row, column, item)

    def _color_row(self, row: int, level: str) -> None:
        color = _LEVEL_COLORS.get(level)
        if not color:
            return
        for col in range(self.findings_table.columnCount()):
            cell = self.findings_table.item(row, col)
            if cell:
                cell.setBackground(color)

    def _update_status_label(self, findings: List[Dict]) -> None:
        if not findings:
            self.preflight_status_label.setText(
                "No advisory findings recorded for this action."
            )
            return
        blockers = [f for f in findings if self._to_level(f.get("severity")) == "block"]
        warnings = [f for f in findings if self._to_level(f.get("severity")) == "warn"]
        if blockers:
            self.preflight_status_label.setText(
                f"Export blocked until blockers are resolved ({len(blockers)} finding(s))."
            )
        elif warnings:
            self.preflight_status_label.setText(
                f"Warnings present ({len(warnings)} finding(s)); review before continuing."
            )
        else:
            self.preflight_status_label.setText(
                "Only informational advisory entries recorded."
            )

    @staticmethod
    def _to_level(severity: Optional[str]) -> str:
        sev = (severity or "").lower()
        if sev in {"error", "critical", "block"}:
            return "block"
        if sev == "warn":
            return "warn"
        return "info"
