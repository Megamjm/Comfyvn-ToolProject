from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from comfyvn.core.notifier import notifier
from comfyvn.gui.services.server_bridge import ServerBridge

_DEFAULT_PROBE_MESSAGE = (
    "Probe results appear here. Ports are checked in the order listed above."
)


class NetworkPanel(QWidget):
    """Settings panel for configuring host binding, port order, and public base URL."""

    def __init__(
        self, bridge: Optional[ServerBridge] = None, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge or ServerBridge()
        self._loading = False
        self._current_settings: Dict[str, Any] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QLabel(
            "<b>Server Binding</b><br/>"
            "Update the host/port binding used by the desktop launcher. Ports are tried in order."
        )
        header.setTextFormat(Qt.RichText)
        header.setWordWrap(True)
        root.addWidget(header)

        form = QFormLayout()
        form.setFormAlignment(Qt.AlignTop)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.host_edit = QLineEdit(self)
        self.host_edit.setPlaceholderText("127.0.0.1")

        self.ports_edit = QLineEdit(self)
        self.ports_edit.setPlaceholderText("8001,8000,8080")
        ports_hint = QLabel("CSV list, first available port becomes active.")
        ports_hint.setWordWrap(True)
        ports_hint.setObjectName("portsHintLabel")

        self.public_base_edit = QLineEdit(self)
        self.public_base_edit.setPlaceholderText("https://studio.example.com")
        public_hint = QLabel(
            "Optional public base URL for link generation (leave blank for local)."
        )
        public_hint.setWordWrap(True)

        form.addRow("Host:", self.host_edit)
        form.addRow("Ports:", self.ports_edit)
        form.addRow("", ports_hint)
        form.addRow("Public Base:", self.public_base_edit)
        form.addRow("", public_hint)
        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_refresh = QPushButton("Refresh", self)
        self.btn_probe = QPushButton("Probe", self)
        self.btn_apply = QPushButton("Apply", self)
        buttons.addWidget(self.btn_refresh)
        buttons.addWidget(self.btn_probe)
        buttons.addWidget(self.btn_apply)
        root.addLayout(buttons)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("networkPanelStatus")
        root.addWidget(self.status_label)

        self.probe_output = QTextEdit(self)
        self.probe_output.setReadOnly(True)
        self.probe_output.setPlaceholderText(_DEFAULT_PROBE_MESSAGE)
        root.addWidget(self.probe_output, 1)

        api_hint = QLabel(
            "API hooks: /api/settings/ports/get • /set • /probe (POST).\n"
            "Use for scripted setups or mod tooling."
        )
        api_hint.setWordWrap(True)
        api_hint.setObjectName("networkPanelApiHint")
        root.addWidget(api_hint)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_apply.clicked.connect(self.apply_changes)
        self.btn_probe.clicked.connect(self.probe)

        self.refresh()

    # ------------------------------------------------------------------ UI helpers
    def _set_status(self, message: str, level: str = "info") -> None:
        prefix = {"info": "ℹ️", "warn": "⚠️", "error": "❌", "success": "✅"}.get(
            level, "ℹ️"
        )
        self.status_label.setText(f"{prefix} {message}")

    def _normalise_ports(self, ports: Iterable[Any]) -> list[int]:
        normalised: list[int] = []
        for item in ports:
            try:
                port = int(str(item).strip())
            except (TypeError, ValueError):
                continue
            if port > 0:
                normalised.append(port)
        return normalised

    def _extract_payload(self, payload: Any) -> Dict[str, Any]:
        """Best-effort extraction of host/ports/public_base from varied payload layouts."""
        if not isinstance(payload, dict):
            return {}

        if "data" in payload and isinstance(payload["data"], dict):
            payload = payload["data"]
        elif "settings" in payload and isinstance(payload["settings"], dict):
            payload = payload["settings"]

        host = payload.get("host")
        ports = payload.get("ports")
        public_base = payload.get("public_base")

        if isinstance(payload.get("server"), dict):
            server_block = payload["server"]
            host = server_block.get("host", host)
            ports = server_block.get("ports", ports)
            public_base = server_block.get("public_base", public_base)

        if isinstance(host, str):
            host = host.strip()
        else:
            host = ""

        if isinstance(public_base, str):
            public_base = public_base.strip()
        else:
            public_base = ""

        ports_list: list[int] = []
        if isinstance(ports, (list, tuple)):
            ports_list = self._normalise_ports(ports)

        return {"host": host, "ports": ports_list, "public_base": public_base}

    def _build_payload(self) -> Optional[Dict[str, Any]]:
        host = self.host_edit.text().strip()
        ports_text = self.ports_edit.text().replace(" ", "")
        raw_ports = [p for p in ports_text.split(",") if p]
        ports: list[int] = []
        invalid: list[str] = []
        for raw in raw_ports:
            try:
                port = int(raw)
            except ValueError:
                invalid.append(raw)
                continue
            if port <= 0 or port > 65535:
                invalid.append(raw)
                continue
            ports.append(port)

        if invalid:
            pretty = ", ".join(invalid)
            self._set_status(f"Ignoring invalid port entries: {pretty}", "warn")

        if not ports:
            self._set_status("Provide at least one valid port.", "error")
            notifier.toast("error", "No valid ports supplied.")
            return None

        public_base = self.public_base_edit.text().strip()
        payload: Dict[str, Any] = {
            "host": host or "127.0.0.1",
            "ports": ports,
            "public_base": public_base or None,
        }
        return payload

    def _describe_restart(self, meta: Dict[str, Any]) -> str | None:
        restart_flag: Optional[bool] = None
        for key in ("restart_required", "requires_restart", "pending_restart"):
            if key in meta:
                restart_flag = bool(meta.get(key))
                break
        if restart_flag:
            return "Will apply on next server restart."
        if restart_flag is False:
            return "Changes applied immediately."
        if meta.get("ok") is False:
            return None
        if meta.get("applied") or meta.get("updated"):
            return "Changes applied immediately."
        return None

    # ------------------------------------------------------------------ Actions
    def refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        try:
            response = self._bridge.get_json(
                "/api/settings/ports/get", timeout=5.0, default=None
            )
            payload = self._extract_payload(response or {})
            if not payload:
                self._set_status(
                    "Unable to read network settings from server.", "error"
                )
                return
            self._current_settings = dict(payload)
            self.host_edit.setText(payload["host"])
            ports_text = ", ".join(str(p) for p in payload["ports"])
            self.ports_edit.setText(ports_text)
            self.public_base_edit.setText(payload["public_base"])
            self._set_status("Loaded current binding.", "success")
        finally:
            self._loading = False

    def apply_changes(self) -> None:
        payload = self._build_payload()
        if not payload:
            return
        response = self._bridge.post_json(
            "/api/settings/ports/set", payload, timeout=5.0, default=None
        )
        if not isinstance(response, dict):
            self._set_status("Failed to update settings: no response.", "error")
            notifier.toast("error", "Network settings update failed.")
            return

        if not response.get("ok", False):
            error_msg = "Network settings update failed."
            if isinstance(response.get("error"), str):
                error_msg = f"{error_msg} {response['error']}"
            self._set_status(error_msg, "error")
            notifier.toast("error", error_msg)
            return

        meta = response.get("data") if isinstance(response.get("data"), dict) else {}
        restart_note = self._describe_restart(response)
        if not restart_note and meta:
            restart_note = self._describe_restart(meta)

        message = "Network settings updated."
        if restart_note:
            message = f"{message} {restart_note}"
        notifier.toast("info", message)
        if restart_note:
            self._set_status(restart_note, "info")
        else:
            self._set_status("Settings applied.", "success")
        self.refresh()

    def probe(self) -> None:
        payload = self._build_payload()
        if not payload:
            return
        response = self._bridge.post_json(
            "/api/settings/ports/probe", payload, timeout=8.0, default=None
        )
        if not isinstance(response, dict):
            self._set_status("Probe failed: no response from server.", "error")
            notifier.toast("error", "Probe failed: no response.")
            return

        if not response.get("ok", False):
            message = "Probe failed."
            if isinstance(response.get("error"), str):
                message = f"{message} {response['error']}"
            self.probe_output.setPlainText(message)
            self._set_status(message, "error")
            notifier.toast("error", message)
            return

        data = response.get("data")
        if isinstance(data, dict):
            results = data.get("results") or data.get("probe")
        else:
            results = None

        if not results:
            message = "Probe did not return any candidates."
            if isinstance(response.get("error"), str):
                message = f"Probe failed: {response['error']}"
            self.probe_output.setPlainText(message)
            self._set_status(message, "warn")
            return

        lines = []
        for item in results:
            if not isinstance(item, dict):
                lines.append(str(item))
                continue
            host = item.get("host") or payload["host"]
            port = item.get("port")
            status = item.get("status")
            latency = item.get("latency")
            label = item.get("label") or item.get("base_url")
            prefix = "•"
            summary = f"{host}:{port}"
            if label:
                summary = f"{label} ({summary})"
            detail = []
            if status is not None:
                detail.append(f"status={status}")
            if latency is not None:
                detail.append(f"{latency}ms")
            if item.get("selected"):
                prefix = "✔"
                detail.append("selected")
            lines.append(f"{prefix} {summary} {' '.join(detail)}".strip())

        self.probe_output.setPlainText("\n".join(lines))
        self._set_status("Probe completed.", "success")
        notifier.toast("info", "Probe request completed.")


__all__ = ["NetworkPanel"]
