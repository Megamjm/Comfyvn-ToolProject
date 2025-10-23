from __future__ import annotations

import html
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
        self._disclaimer_detail: Dict[str, Any] = {}
        self._banner_dismissed = False

        root = QVBoxLayout(self)
        self.disclaimer_group = self._build_disclaimer_group()
        root.addWidget(self.disclaimer_group)
        root.addWidget(self._build_preflight_group(), 1)
        root.addStretch(1)

        self._load_disclaimer()
        self._refresh_findings(fetch=True)

    def set_base_url(self, base: str) -> None:
        new_base = (base or "").rstrip("/")
        if not new_base or new_base == self.base:
            return
        self.base = new_base
        self._load_disclaimer()
        self._refresh_findings(fetch=True)

    # ------------------------------------------------------------------
    # Disclaimer group
    # ------------------------------------------------------------------
    def _build_disclaimer_group(self) -> QGroupBox:
        self.disclaimer_label = QLabel("Loading advisory disclaimer…", self)
        self.disclaimer_label.setWordWrap(True)
        self.disclaimer_label.setOpenExternalLinks(True)

        self.view_button = QPushButton("View Full Text", self)
        self.view_button.clicked.connect(self._show_disclaimer_text)

        self.ack_button = QPushButton("Acknowledge Disclaimer", self)
        self.ack_button.clicked.connect(self._acknowledge)

        self.dismiss_button = QPushButton("Dismiss Banner", self)
        self.dismiss_button.clicked.connect(self._dismiss_banner)

        button_row = QHBoxLayout()
        button_row.addWidget(self.view_button)
        button_row.addWidget(self.ack_button)
        button_row.addWidget(self.dismiss_button)
        button_row.addStretch(1)

        box = QGroupBox("Advisory Disclaimer", self)
        layout = QVBoxLayout()
        layout.addWidget(self.disclaimer_label)
        layout.addLayout(button_row)
        box.setLayout(layout)
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

        self.override_checkbox = QCheckBox("Request override during evaluation", self)
        self.override_checkbox.setToolTip(
            "Include an override hint when running the policy evaluation call."
        )

        evaluate_button = QPushButton("Evaluate Selected Action", self)
        evaluate_button.clicked.connect(self._evaluate_action)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Action:", self))
        header_row.addWidget(self.action_combo)
        header_row.addStretch(1)
        header_row.addWidget(refresh_button)

        control_row = QHBoxLayout()
        control_row.addWidget(self.override_checkbox)
        control_row.addStretch(1)
        control_row.addWidget(evaluate_button)

        self.findings_table = QTableWidget(0, 4, self)
        self.findings_table.setHorizontalHeaderLabels(
            ["Category", "Severity", "Message", "Target"]
        )
        self.findings_table.horizontalHeader().setStretchLastSection(True)
        self.findings_table.setSelectionBehavior(QTableWidget.SelectRows)

        self.preflight_status_label = QLabel("No advisory findings loaded yet.", self)
        self.preflight_status_label.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addLayout(header_row)
        layout.addLayout(control_row)
        layout.addWidget(self.findings_table, 1)
        layout.addWidget(self.preflight_status_label)

        box = QGroupBox("Import/Export Pre-flight", self)
        box.setLayout(layout)
        return box

    # ------------------------------------------------------------------
    # Gate handlers
    # ------------------------------------------------------------------
    def _load_disclaimer(self) -> None:
        try:
            resp = requests.get(self.base + "/api/advisory/disclaimer", timeout=3)
        except Exception as exc:  # pragma: no cover - GUI runtime
            LOGGER.error("Disclaimer request failed: %s", exc)
            self.disclaimer_label.setText(f"Disclaimer unavailable: {exc}")
            return

        if resp.status_code >= 400:
            LOGGER.warning(
                "Disclaimer request error %s: %s", resp.status_code, resp.text
            )
            self.disclaimer_label.setText(
                f"Disclaimer request failed: {resp.status_code} {resp.text}"
            )
            return

        data = resp.json() or {}
        self._disclaimer_detail = data
        acknowledged = bool(data.get("acknowledged"))
        message = data.get("message") or "Review the advisory disclaimer."
        ack_detail = data.get("ack") or {}
        timestamp = ack_detail.get("at") or ack_detail.get("timestamp")
        name = (ack_detail.get("name") or "").strip()

        detail_lines = [message]
        if acknowledged:
            meta: List[str] = []
            if name:
                meta.append(f"acknowledged by {name}")
            if timestamp:
                try:
                    when = datetime.fromtimestamp(float(timestamp))
                    meta.append(f"on {when.strftime('%Y-%m-%d %H:%M:%S')}")
                except Exception:  # pragma: no cover - GUI runtime
                    meta.append(f"at {timestamp}")
            if meta:
                detail_lines.append(" • " + ", ".join(meta))
        else:
            detail_lines.append(
                "Acknowledge once to store your acceptance alongside advisory logs."
            )

        links = data.get("links") or {}
        if links:
            link_parts = []
            for label, url in links.items():
                escaped_label = html.escape(str(label).title())
                escaped_url = html.escape(str(url))
                link_parts.append(f'<a href="{escaped_url}">{escaped_label}</a>')
            if link_parts:
                detail_lines.append("Resources: " + ", ".join(link_parts))

        formatted = "<br>".join(html.escape(line) for line in detail_lines)
        self.disclaimer_label.setText(formatted)

        self.ack_button.setVisible(not acknowledged)
        self.view_button.setEnabled(bool(data.get("text")))
        # Allow dismiss only after acknowledgement; keep banner visible otherwise
        self.dismiss_button.setEnabled(acknowledged)
        show_banner = not self._banner_dismissed or not acknowledged
        self.disclaimer_group.setVisible(show_banner)
        status_payload = data.get("status") or {}
        self.override_checkbox.setEnabled(
            bool(status_payload.get("warn_override_enabled", True))
        )
        self.override_checkbox.setChecked(False)

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
        disclaimer_text = (
            self._disclaimer_detail.get("text") or "Review the advisory disclaimer."
        )
        waiver_snapshot = getattr(self, "_disclaimer_detail", {}) or {}
        waiver_message = waiver_snapshot.get("message") or (
            "Acknowledge that advisory findings are informational and you remain responsible for content you import or export."
        )
        formatted_text = html.escape(disclaimer_text)
        waiver_details = f"<div style='white-space:pre-wrap;'>{formatted_text}</div>"
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
            resp = requests.post(
                self.base + "/api/advisory/ack", json=payload, timeout=5
            )
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
        self._banner_dismissed = False
        self._load_disclaimer()

    def _dismiss_banner(self) -> None:
        if not self._disclaimer_detail.get("acknowledged"):
            QMessageBox.information(
                self,
                "Advisory Disclaimer",
                "Please acknowledge the disclaimer before dismissing the banner.",
            )
            return
        self._banner_dismissed = True
        self.disclaimer_group.hide()

    def _show_disclaimer_text(self) -> None:
        text = str(self._disclaimer_detail.get("text") or "").strip()
        if not text:
            QMessageBox.information(
                self,
                "Advisory Disclaimer",
                "No additional disclaimer text available.",
            )
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Advisory Disclaimer")
        dialog.setIcon(QMessageBox.Information)
        dialog.setTextFormat(Qt.RichText)
        dialog.setText(f"<div style='white-space:pre-wrap;'>{html.escape(text)}</div>")
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.exec()

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
        disclaimer = payload.get("disclaimer") or {}
        message_parts = []
        if warnings:
            message_parts.append("\n".join(warnings))
        else:
            message_parts.append("No warnings reported.")
        if disclaimer and not disclaimer.get("acknowledged"):
            message_parts.append(
                disclaimer.get("message") or "Disclaimer pending acknowledgment."
            )
        message = "\n\n".join(message_parts)
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
            category = self._category_for(item)
            severity = self._to_level(item.get("severity"))
            self._set_item(row, 0, category.title())
            self._set_item(row, 1, severity.upper())
            self._set_item(row, 2, item.get("message") or "")
            target = item.get("target_id") or item.get("target")
            self._set_item(row, 3, target or "")
            self._color_row(row, severity)

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
                f"{len(blockers)} advisory finding(s) marked as blockers. Review before sharing outputs."
            )
        elif warnings:
            self.preflight_status_label.setText(
                f"Warnings present ({len(warnings)} finding(s)); review recommended."
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

    @staticmethod
    def _category_for(entry: Dict[str, Any]) -> str:
        kind = str(entry.get("category") or entry.get("kind") or "").lower()
        detail = entry.get("detail") if isinstance(entry.get("detail"), dict) else {}
        if any(token in kind for token in ("license", "policy", "copyright", "ip")):
            return "license"
        if any(token in kind for token in ("nsfw", "sfw", "content", "safety")):
            return "sfw"
        if isinstance(detail, dict):
            hint = str(detail.get("category") or detail.get("kind") or "").lower()
            if hint in {"license", "copyright", "policy"}:
                return "license"
            if hint in {"nsfw", "sfw", "content"}:
                return "sfw"
        return "unknown"
