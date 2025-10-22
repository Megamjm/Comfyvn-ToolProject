from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from comfyvn.config.baseurl_authority import default_base_url
from comfyvn.core.compute_registry import ComputeProviderRegistry


def _normalize_iso(ts: str) -> Optional[datetime]:
    raw = ts.strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _format_timestamp(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(value)
    if isinstance(value, str):
        parsed = _normalize_iso(value)
        if parsed:
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        return value
    return str(value)


class DebugIntegrationsPanel(QWidget):
    """Live diagnostics for provider integrations (health, quotas, credentials)."""

    def __init__(self, base: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.base = (base or default_base_url()).rstrip("/")
        self.registry = ComputeProviderRegistry()
        self._timer = QTimer(self)
        self._timer.setInterval(15000)
        self._timer.timeout.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        heading = QLabel(
            f"Provider diagnostics · base: <code>{self.base or 'not configured'}</code>"
        )
        heading.setTextFormat(Qt.RichText)
        layout.addWidget(heading)

        toolbar = QHBoxLayout()
        self.status_label = QLabel("Ready.")
        self.status_label.setObjectName("debugStatusLabel")
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh)
        self.toggle_auto = QPushButton("Auto Refresh")
        self.toggle_auto.setCheckable(True)
        self.toggle_auto.setChecked(True)
        self.toggle_auto.toggled.connect(self._toggle_auto_refresh)
        toolbar.addWidget(btn_refresh)
        toolbar.addWidget(self.toggle_auto)
        toolbar.addStretch(1)
        toolbar.addWidget(self.status_label)
        layout.addLayout(toolbar)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(
            [
                "Provider ID",
                "Name",
                "Status",
                "Usage / Rate",
                "Last Error",
                "Last Update",
            ]
        )
        self.tree.setUniformRowHeights(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(0, self.tree.header().ResizeToContents)
        self.tree.header().setSectionResizeMode(1, self.tree.header().Stretch)
        self.tree.header().setSectionResizeMode(2, self.tree.header().ResizeToContents)
        self.tree.header().setSectionResizeMode(3, self.tree.header().Stretch)
        self.tree.header().setSectionResizeMode(4, self.tree.header().Stretch)
        self.tree.header().setSectionResizeMode(5, self.tree.header().ResizeToContents)

        layout.addWidget(self.tree)
        self._timer.start()
        self.refresh()

    def _toggle_auto_refresh(self, enabled: bool) -> None:
        if enabled:
            self._timer.start()
        else:
            self._timer.stop()

    def _fetch_health(self) -> Dict[str, Dict[str, Any]]:
        url = f"{self.base}/api/providers/health".rstrip("/")
        try:
            response = requests.get(url, timeout=5.0)
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("results") or []
            return {
                str(row.get("provider_id") or row.get("provider", "")): row
                for row in rows
                if isinstance(row, dict)
            }
        except Exception as exc:
            self.status_label.setText(f"Health fetch failed: {exc}")
            return {}

    def _fetch_quota(self, provider_id: str) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{self.base}/api/providers/quota",
                params={"id": provider_id},
                timeout=5.0,
            )
            if response.status_code >= 400:
                return {
                    "ok": False,
                    "status_code": response.status_code,
                    "error": response.text,
                }
            payload = response.json()
            if isinstance(payload, dict):
                return payload
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return None

    def _color_for_status(self, status: Optional[Dict[str, Any]]) -> QColor:
        if not status:
            return QColor("#607D8B")  # slate
        if status.get("ok"):
            return QColor("#2E7D32")  # green
        if status.get("error") or status.get("status_code"):
            return QColor("#C62828")  # red
        return QColor("#F9A825")  # amber

    @staticmethod
    def _format_usage(quota: Optional[Dict[str, Any]], status: Dict[str, Any]) -> str:
        if quota and quota.get("ok"):
            q = quota.get("quota")
            if isinstance(q, dict):
                fragments = []
                credits = q.get("credits") or q.get("balance")
                if credits is not None:
                    fragments.append(f"credits: {credits}")
                limit = q.get("limit") or q.get("monthly_limit")
                if limit is not None:
                    fragments.append(f"limit: {limit}")
                if q.get("currency"):
                    fragments.append(q["currency"])
                if fragments:
                    return " · ".join(str(part) for part in fragments if part)
            latency = quota.get("latency_ms")
            if latency is not None:
                return f"latency {latency:.0f} ms"
            return "ok"
        latency = status.get("latency_ms")
        if latency is not None:
            return f"latency {latency:.0f} ms"
        return "—"

    def _populate_tree(
        self,
        providers: list[Dict[str, Any]],
        health_map: Dict[str, Dict[str, Any]],
        quota_map: Dict[str, Optional[Dict[str, Any]]],
    ) -> None:
        self.tree.clear()
        for entry in providers:
            provider_id = str(entry.get("id") or "provider")
            name = entry.get("name") or provider_id
            status = health_map.get(provider_id) or {}
            last_health = entry.get("last_health") or {}
            quota = quota_map.get(provider_id)

            item = QTreeWidgetItem(self.tree)
            item.setText(0, provider_id)
            item.setText(1, name)

            state_text = "unknown"
            if status:
                state_text = "healthy" if status.get("ok") else "error"
            elif last_health:
                state_text = "healthy" if last_health.get("ok") else "degraded"
            item.setText(2, state_text)

            color = self._color_for_status(status or last_health)
            item.setForeground(2, color)

            usage_text = self._format_usage(quota, status)
            item.setText(3, usage_text)

            err_text = status.get("error") or last_health.get("error")
            if not err_text and quota and not quota.get("ok"):
                err_text = quota.get("error")
            if err_text and isinstance(err_text, dict):
                err_text = json.dumps(err_text)
            item.setText(4, (err_text or "")[:200])

            ts = (
                status.get("timestamp")
                or last_health.get("ts")
                or status.get("when")
                or quota.get("timestamp")
                if isinstance(quota, dict)
                else None
            )
            item.setText(5, _format_timestamp(ts))

            config = entry.get("config") or {}
            meta = entry.get("meta") or {}
            rate_limits = entry.get("rate_limits") or {}

            if config:
                config_parent = QTreeWidgetItem(item, ["Config", ""])
                for key, value in sorted(config.items()):
                    QTreeWidgetItem(config_parent, [key, json.dumps(value)])

            if rate_limits:
                rate_parent = QTreeWidgetItem(item, ["Rate Limits", ""])
                for key, value in sorted(rate_limits.items()):
                    QTreeWidgetItem(rate_parent, [key, json.dumps(value)])

            if meta:
                meta_parent = QTreeWidgetItem(item, ["Meta", ""])
                for key, value in sorted(meta.items()):
                    if isinstance(value, (dict, list)):
                        display = json.dumps(value)
                    else:
                        display = str(value)
                    QTreeWidgetItem(meta_parent, [key, display])

        self.tree.expandAll()

    def refresh(self) -> None:
        providers = self.registry.list()
        if not providers:
            self.status_label.setText("No providers configured.")
            self.tree.clear()
            return

        health_map = self._fetch_health()
        quota_map: Dict[str, Optional[Dict[str, Any]]] = {}
        for entry in providers:
            provider_id = str(entry.get("id") or "")
            if not provider_id:
                continue
            kind = (entry.get("kind") or entry.get("service") or "").lower()
            if provider_id == "local" or kind in {"local"}:
                quota_map[provider_id] = None
                continue
            quota_map[provider_id] = self._fetch_quota(provider_id)

        self._populate_tree(providers, health_map, quota_map)
        self.status_label.setText(
            f"Last refresh: {_format_timestamp(datetime.utcnow())} (providers: {len(providers)})"
        )
