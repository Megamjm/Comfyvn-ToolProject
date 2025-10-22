from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from comfyvn.config.baseurl_authority import default_base_url

LOGGER = logging.getLogger(__name__)


class TranslationPanel(QWidget):
    """Review queue for translation memory entries with export helpers."""

    def __init__(self, base: str | None = None) -> None:
        super().__init__()
        self.base = (base or default_base_url()).rstrip("/")
        self.pending: List[Dict[str, Any]] = []
        self._selected_row: int = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        controls = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        self.approve_btn = QPushButton("Approve")
        self.approve_btn.clicked.connect(self._approve_current)
        self.approve_next_btn = QPushButton("Approve + Next")
        self.approve_next_btn.clicked.connect(
            lambda: self._approve_current(advance=True)
        )
        self.export_json_btn = QPushButton("Export JSON")
        self.export_json_btn.clicked.connect(self._export_json)
        self.export_po_btn = QPushButton("Export PO")
        self.export_po_btn.clicked.connect(self._export_po)

        for btn in (
            self.refresh_btn,
            self.approve_btn,
            self.approve_next_btn,
            self.export_json_btn,
            self.export_po_btn,
        ):
            controls.addWidget(btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Lang", "Source Preview", "Confidence"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self._handle_selection_changed)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.table, 2)

        form_widget = QWidget(self)
        form_layout = QFormLayout(form_widget)
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.lang_label = QLabel("-", self)
        self.confidence_label = QLabel("-", self)
        self.source_edit = QPlainTextEdit(self)
        self.source_edit.setReadOnly(True)
        self.source_edit.setPlaceholderText("Select a pending entry to review.")

        self.target_edit = QPlainTextEdit(self)
        self.target_edit.setPlaceholderText("Proposed translation…")

        form_layout.addRow("Language:", self.lang_label)
        form_layout.addRow("Confidence:", self.confidence_label)
        form_layout.addRow("Source:", self.source_edit)
        form_layout.addRow("Translation:", self.target_edit)
        layout.addWidget(form_widget, 1)

        self.status_label = QLabel("No pending items loaded.", self)
        self.status_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(self.status_label)

        self.refresh()

    # ------------------------------------------------------------------ #
    # Network helpers
    # ------------------------------------------------------------------ #
    def _get(
        self, path: str, *, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"{self.base}{path}"
        try:
            response = requests.get(url, params=params, timeout=5)
        except Exception as exc:
            LOGGER.warning("TranslationPanel GET failed: %s", exc)
            return {}
        if response.status_code >= 400:
            LOGGER.warning(
                "TranslationPanel GET %s failed: %s", path, response.status_code
            )
            return {}
        try:
            data = response.json()
        except Exception:
            data = {}
        return data if isinstance(data, dict) else {}

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base}{path}"
        try:
            response = requests.post(url, json=payload, timeout=5)
        except Exception as exc:
            LOGGER.warning("TranslationPanel POST failed: %s", exc)
            return {}
        if response.status_code >= 400:
            LOGGER.warning(
                "TranslationPanel POST %s failed: %s", path, response.status_code
            )
            try:
                return response.json()
            except Exception:
                return {}
        try:
            data = response.json()
        except Exception:
            data = {}
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------ #
    # UI actions
    # ------------------------------------------------------------------ #
    def refresh(self, preferred_row: int | None = None) -> None:
        payload = self._get("/translate/review/pending")
        items = payload.get("items") if isinstance(payload, dict) else None
        self.pending = items if isinstance(items, list) else []
        self._render_table()

        summary = payload.get("total") if isinstance(payload, dict) else None
        if isinstance(summary, int):
            self.status_label.setText(f"{summary} pending translation(s).")
        else:
            self.status_label.setText("Review queue refreshed.")

        if preferred_row is None:
            preferred_row = 0
        if self.pending:
            row = min(max(preferred_row, 0), len(self.pending) - 1)
            self.table.blockSignals(True)
            self.table.selectRow(row)
            self.table.blockSignals(False)
            self._apply_selection(row)
        else:
            self._clear_details()

    def _render_table(self) -> None:
        self.table.setRowCount(len(self.pending))
        for row, item in enumerate(self.pending):
            lang = item.get("lang") or "-"
            source = str(item.get("source") or "")
            confidence = item.get("confidence") or 0.0
            preview = source.replace("\n", " ")
            if len(preview) > 60:
                preview = preview[:57] + "…"

            self.table.setItem(row, 0, QTableWidgetItem(lang))
            self.table.setItem(row, 1, QTableWidgetItem(preview))
            conf_item = QTableWidgetItem(f"{float(confidence):.2f}")
            conf_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, conf_item)

        self.table.resizeColumnsToContents()

    def _handle_selection_changed(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.pending):
            self._clear_details()
            return
        self._selected_row = row
        self._apply_selection(row)

    def _apply_selection(self, row: int) -> None:
        if row < 0 or row >= len(self.pending):
            self._clear_details()
            return
        self._selected_row = row
        entry = self.pending[row]
        self.lang_label.setText(str(entry.get("lang") or "-"))
        confidence = entry.get("confidence")
        self.confidence_label.setText(f"{float(confidence):.2f}")
        self.source_edit.setPlainText(str(entry.get("source") or ""))
        self.target_edit.setPlainText(str(entry.get("target") or ""))

    def _clear_details(self) -> None:
        self._selected_row = -1
        self.lang_label.setText("-")
        self.confidence_label.setText("-")
        self.source_edit.clear()
        self.target_edit.clear()

    def _approve_current(self, *, advance: bool = False) -> None:
        if self._selected_row < 0 or self._selected_row >= len(self.pending):
            QMessageBox.information(
                self, "Approve Translation", "Select an entry first."
            )
            return
        entry = self.pending[self._selected_row]
        translation = self.target_edit.toPlainText()
        payload = {"id": entry.get("id"), "translation": translation}
        response = self._post("/translate/review/approve", payload)
        if not response.get("ok"):
            QMessageBox.warning(
                self,
                "Approve Translation",
                "Server rejected the approval. Check logs.",
            )
            return
        next_row = self._selected_row if not advance else self._selected_row
        self.refresh(preferred_row=next_row)

    def _export_json(self) -> None:
        payload = self._get("/translate/export/json")
        if not payload.get("ok"):
            QMessageBox.warning(
                self, "Export JSON", "Failed to export translation memory."
            )
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Translation Memory (JSON)",
            "translations.json",
            "JSON Files (*.json);;All Files (*)",
        )
        if not filename:
            return
        try:
            Path(filename).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            QMessageBox.warning(self, "Export JSON", f"Failed to write file: {exc}")
            return
        QMessageBox.information(
            self, "Export JSON", f"Exported reviewed entries to {filename}."
        )

    def _export_po(self) -> None:
        url = f"{self.base}/translate/export/po"
        try:
            response = requests.get(url, timeout=5)
        except Exception as exc:
            QMessageBox.warning(self, "Export PO", f"Request failed: {exc}")
            return
        if response.status_code >= 400:
            QMessageBox.warning(
                self, "Export PO", f"Server returned {response.status_code}."
            )
            return
        text = response.text
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Translation Memory (PO)",
            "translations.po",
            "PO Files (*.po);;All Files (*)",
        )
        if not filename:
            return
        try:
            Path(filename).write_text(text, encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Export PO", f"Failed to write file: {exc}")
            return
        QMessageBox.information(
            self, "Export PO", f"Exported reviewed entries to {filename}."
        )
