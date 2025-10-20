from __future__ import annotations

import logging
from typing import Optional

import requests
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QComboBox,
    QCheckBox,
    QInputDialog,
    QMessageBox,
    QLineEdit,
    QGroupBox,
    QFormLayout,
)


LOGGER = logging.getLogger(__name__)


class AdvisoryPanel(QWidget):
    """Displays advisory, policy gate, and filter status."""

    def __init__(self, base: str = "http://127.0.0.1:8001") -> None:
        super().__init__()
        self.base = base.rstrip("/")

        # Advisory log controls
        self.filter_box = QComboBox(self)
        self.filter_box.addItems(["All", "Unresolved", "Resolved"])
        self.filter_box.currentIndexChanged.connect(self.refresh)

        refresh_btn = QPushButton("Refresh Logs", self)
        refresh_btn.clicked.connect(self.refresh)

        controls = QHBoxLayout()
        controls.addWidget(self.filter_box)
        controls.addWidget(refresh_btn)
        controls.addStretch(1)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "Target", "Severity", "Message", "Resolved"])
        self.table.horizontalHeader().setStretchLastSection(True)

        self.status_label = QLabel("Advisory scans", self)
        self.status_label.setWordWrap(True)

        # Policy gate controls
        self.policy_status_label = QLabel("Policy status unknown", self)
        self.policy_status_label.setWordWrap(True)

        self.override_checkbox = QCheckBox("Request override when evaluating exports", self)

        ack_button = QPushButton("Acknowledge Legal Terms…", self)
        ack_button.clicked.connect(self._acknowledge)

        evaluate_button = QPushButton("Evaluate Export Action", self)
        evaluate_button.clicked.connect(self._evaluate_export)

        policy_layout = QVBoxLayout()
        policy_layout.addWidget(self.policy_status_label)
        policy_layout.addWidget(self.override_checkbox)
        policy_row = QHBoxLayout()
        policy_row.addWidget(ack_button)
        policy_row.addWidget(evaluate_button)
        policy_row.addStretch(1)
        policy_layout.addLayout(policy_row)

        policy_box = QGroupBox("Liability Gate")
        policy_box.setLayout(policy_layout)

        # Filter controls
        self.filter_mode_box = QComboBox(self)
        self.filter_mode_box.addItems(["sfw", "warn", "unrestricted"])
        self.filter_mode_box.currentTextChanged.connect(self._set_filter_mode)

        self.preview_tags_input = QLineEdit(self)
        self.preview_tags_input.setPlaceholderText("Comma-separated tags (e.g. nsfw,violence)")

        self.preview_nsfw_checkbox = QCheckBox("Mark sample as NSFW", self)

        preview_button = QPushButton("Preview Filter Response", self)
        preview_button.clicked.connect(self._preview_filter)

        self.preview_result_label = QLabel("", self)
        self.preview_result_label.setWordWrap(True)

        filter_form = QFormLayout()
        filter_form.addRow("Mode", self.filter_mode_box)
        filter_form.addRow("Sample tags", self.preview_tags_input)
        filter_form.addRow("", self.preview_nsfw_checkbox)
        filter_form.addRow("", preview_button)

        filter_layout = QVBoxLayout()
        filter_layout.addLayout(filter_form)
        filter_layout.addWidget(self.preview_result_label)

        filter_box = QGroupBox("Content Filters")
        filter_box.setLayout(filter_layout)

        layout = QVBoxLayout(self)
        layout.addWidget(policy_box)
        layout.addWidget(filter_box)
        layout.addLayout(controls)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status_label)

        self._load_filter_mode()
        self._load_policy_status()
        self.refresh()

    # ── Advisory logs ──────────────────────────────────────────────
    def _get_logs(self, resolved: Optional[bool]) -> dict:
        params = {}
        if resolved is not None:
            params["resolved"] = "true" if resolved else "false"
        try:
            resp = requests.get(self.base + "/api/advisory/logs", params=params, timeout=3)
            if resp.status_code < 400:
                return resp.json()
            LOGGER.warning("Advisory logs request failed: %s %s", resp.status_code, resp.text)
        except Exception as exc:
            LOGGER.error("Advisory logs request error: %s", exc)
        return {}

    def refresh(self) -> None:
        index = self.filter_box.currentIndex()
        resolved_filter = None
        if index == 1:
            resolved_filter = False
        elif index == 2:
            resolved_filter = True

        payload = self._get_logs(resolved_filter)
        items = payload.get("items") or []
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            self.table.setItem(row, 0, QTableWidgetItem(item.get("issue_id", "")))
            self.table.setItem(row, 1, QTableWidgetItem(item.get("target_id", "")))
            self.table.setItem(row, 2, QTableWidgetItem(item.get("severity", "")))
            self.table.setItem(row, 3, QTableWidgetItem(item.get("message", "")))
            self.table.setItem(row, 4, QTableWidgetItem(str(item.get("resolved", False))))

        self.status_label.setText(f"Advisory entries: {len(items)}")
        self._load_policy_status()

    # ── Policy gate hooks ──────────────────────────────────────────
    def _load_policy_status(self) -> None:
        try:
            resp = requests.get(self.base + "/api/policy/status", timeout=3)
        except Exception as exc:
            LOGGER.error("Policy status request failed: %s", exc)
            self.policy_status_label.setText(f"Policy status unavailable: {exc}")
            return

        if resp.status_code >= 400:
            self.policy_status_label.setText(f"Policy status error: {resp.status_code} {resp.text}")
            LOGGER.warning("Policy status failed: %s %s", resp.status_code, resp.text)
            return

        data = resp.json()
        status = data.get("status", {})
        requires_ack = status.get("requires_ack", False)
        timestamp = status.get("ack_timestamp")
        message = data.get("message", "")

        details = f"Requires acknowledgement: {'yes' if requires_ack else 'no'}"
        if timestamp:
            details += f" • acknowledged at {timestamp}"
        self.policy_status_label.setText(f"{message}\n{details}")

    def _acknowledge(self) -> None:
        user, ok = QInputDialog.getText(self, "Acknowledge Legal Terms", "Enter your name or initials:")
        if not ok:
            return
        notes, _ = QInputDialog.getText(self, "Optional Notes", "Add acknowledgement notes (optional):")
        payload = {"user": user.strip() or "anonymous"}
        if notes.strip():
            payload["notes"] = notes.strip()
        try:
            resp = requests.post(self.base + "/api/policy/ack", json=payload, timeout=5)
        except Exception as exc:
            LOGGER.error("Policy ack failed: %s", exc)
            QMessageBox.warning(self, "Policy Gate", f"Acknowledgement failed: {exc}")
            return
        if resp.status_code >= 400:
            QMessageBox.warning(self, "Policy Gate", f"Acknowledgement error: {resp.status_code} {resp.text}")
            LOGGER.warning("Policy ack returned error %s: %s", resp.status_code, resp.text)
            return
        self._load_policy_status()
        QMessageBox.information(self, "Policy Gate", "Acknowledgement recorded.")

    def _evaluate_export(self) -> None:
        payload = {
            "action": "export.bundle",
            "override": self.override_checkbox.isChecked(),
        }
        try:
            resp = requests.post(self.base + "/api/policy/evaluate", json=payload, timeout=4)
        except Exception as exc:
            LOGGER.error("Policy evaluate failed: %s", exc)
            QMessageBox.warning(self, "Policy Gate", f"Evaluation failed: {exc}")
            return
        if resp.status_code >= 400:
            QMessageBox.warning(self, "Policy Gate", f"Evaluation error: {resp.status_code} {resp.text}")
            LOGGER.warning("Policy evaluate returned error %s: %s", resp.status_code, resp.text)
            return
        data = resp.json()
        warnings = data.get("warnings") or []
        allow = data.get("allow")
        message = "\n".join(warnings) if warnings else "No warnings reported."
        message = f"Allow: {allow}\n{message}"
        QMessageBox.information(self, "Policy Gate Evaluation", message)

    # ── Filter controls ────────────────────────────────────────────
    def _set_filter_mode(self, mode: str) -> None:
        if not mode:
            return
        try:
            resp = requests.post(self.base + "/api/policy/filters", json={"mode": mode}, timeout=4)
        except Exception as exc:
            LOGGER.error("Set filter mode failed: %s", exc)
            self.preview_result_label.setText(f"Failed to set mode: {exc}")
            return
        if resp.status_code >= 400:
            LOGGER.warning("Filter mode change error %s: %s", resp.status_code, resp.text)
            self.preview_result_label.setText(f"Filter mode error: {resp.status_code} {resp.text}")
            return
        self.preview_result_label.setText(f"Filter mode set to {mode}")

    def _preview_filter(self) -> None:
        tags = [t.strip() for t in self.preview_tags_input.text().split(",") if t.strip()]
        item = {
            "id": "sample",
            "meta": {
                "tags": tags,
            },
        }
        if self.preview_nsfw_checkbox.isChecked():
            item["meta"]["nsfw"] = True
        payload = {"items": [item], "mode": self.filter_mode_box.currentText()}
        try:
            resp = requests.post(self.base + "/api/policy/filter-preview", json=payload, timeout=4)
        except Exception as exc:
            LOGGER.error("Filter preview failed: %s", exc)
            self.preview_result_label.setText(f"Filter preview error: {exc}")
            return
        if resp.status_code >= 400:
            LOGGER.warning("Filter preview returned error %s: %s", resp.status_code, resp.text)
            self.preview_result_label.setText(f"Filter preview error: {resp.status_code} {resp.text}")
            return
        data = resp.json()
        warnings = data.get("warnings") or []
        flagged = data.get("flagged") or []
        self.preview_result_label.setText(
            f"Allowed: {len(data.get('allowed') or [])}, Flagged: {len(flagged)}, Warnings: {warnings}"
        )

    def _load_filter_mode(self) -> None:
        try:
            resp = requests.get(self.base + "/api/policy/filters", timeout=3)
        except Exception as exc:
            LOGGER.error("Fetch filter mode failed: %s", exc)
            return
        if resp.status_code >= 400:
            LOGGER.warning("Fetch filter mode error %s: %s", resp.status_code, resp.text)
            return
        data = resp.json()
        mode = (data.get("mode") or "sfw").lower()
        idx = self.filter_mode_box.findText(mode)
        if idx >= 0:
            self.filter_mode_box.blockSignals(True)
            self.filter_mode_box.setCurrentIndex(idx)
            self.filter_mode_box.blockSignals(False)
