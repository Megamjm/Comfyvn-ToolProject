from PySide6.QtGui import QAction

# comfyvn/gui/panels/settings_panel.py  [Studio-090]
from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QDockWidget,
    QMessageBox,
    QComboBox,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QCheckBox,
    QSpinBox,
)
from PySide6.QtCore import Qt

from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.core.settings_manager import SettingsManager
from comfyvn.core.compute_registry import ComputeProviderRegistry


class SettingsPanel(QDockWidget):
    def __init__(self, bridge: ServerBridge):
        super().__init__("Settings")
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.bridge = bridge
        self.settings_manager = SettingsManager()
        self.provider_registry = ComputeProviderRegistry()
        self._editing_provider_id: str | None = None
        self._providers_cache: dict[str, dict] = {}

        w = QWidget()
        root = QVBoxLayout(w)

        form = QFormLayout()
        self.api = QLineEdit(self.bridge.base)
        self.remote_list = QLineEdit(self.bridge.get("REMOTE_GPU_LIST", default="http://127.0.0.1:8001"))
        self.menu_sort = QComboBox()
        self.menu_sort.addItem("Load order (default)", "load_order")
        self.menu_sort.addItem("Best practice structure", "best_practice")
        self.menu_sort.addItem("Alphabetical", "alphabetical")
        current_mode = self.settings_manager.load().get("ui", {}).get("menu_sort_mode", "load_order")
        index = self.menu_sort.findData(current_mode)
        if index != -1:
            self.menu_sort.setCurrentIndex(index)
        btn_save = QPushButton("Save UI Settings")
        btn_save.clicked.connect(self._save_settings)
        form.addRow("API Base URL:", self.api)
        form.addRow("Legacy Remote GPU Endpoints:", self.remote_list)
        form.addRow("Menu Sort Order:", self.menu_sort)
        form.addRow(btn_save)
        root.addLayout(form)

        self.server_group = self._build_server_controls()
        root.addWidget(self.server_group)
        root.addStretch(1)
        self.setWidget(w)

        self._refresh_servers()

    # --------------------
    # UI construction
    # --------------------
    def _build_server_controls(self) -> QGroupBox:
        group = QGroupBox("Compute / Server Endpoints")
        layout = QHBoxLayout(group)

        # Left column — list + actions
        left = QVBoxLayout()
        left.addWidget(QLabel("Configured Providers"))
        self.server_list = QListWidget()
        self.server_list.currentItemChanged.connect(self._on_server_selected)
        left.addWidget(self.server_list)

        btn_row = QHBoxLayout()
        self.btn_server_refresh = QPushButton("Refresh")
        self.btn_server_discover = QPushButton("Discover Local")
        self.btn_server_add = QPushButton("Add")
        self.btn_server_remove = QPushButton("Remove")
        btn_row.addWidget(self.btn_server_refresh)
        btn_row.addWidget(self.btn_server_discover)
        btn_row.addWidget(self.btn_server_add)
        btn_row.addWidget(self.btn_server_remove)
        btn_row.addStretch(1)
        left.addLayout(btn_row)

        layout.addLayout(left, 1)

        # Right column — details editor
        right = QVBoxLayout()
        details = QFormLayout()
        self.server_status_label = QLabel("Select a server to view status.")
        self.server_name_edit = QLineEdit()
        self.server_url_edit = QLineEdit()
        self.server_kind_combo = QComboBox()
        self.server_kind_combo.addItems(["remote", "local"])
        self.server_service_combo = QComboBox()
        self.server_service_combo.addItems(["comfyui", "render", "lan", "custom"])
        self.server_priority_spin = QSpinBox()
        self.server_priority_spin.setRange(0, 1000)
        self.server_active_check = QCheckBox("Active")

        details.addRow(self.server_status_label)
        details.addRow("Name:", self.server_name_edit)
        details.addRow("Base URL:", self.server_url_edit)
        details.addRow("Kind:", self.server_kind_combo)
        details.addRow("Service:", self.server_service_combo)
        details.addRow("Priority:", self.server_priority_spin)
        details.addRow("", self.server_active_check)
        right.addLayout(details)

        action_row = QHBoxLayout()
        self.btn_server_save = QPushButton("Save Server")
        self.btn_server_probe = QPushButton("Probe Health")
        action_row.addWidget(self.btn_server_save)
        action_row.addWidget(self.btn_server_probe)
        action_row.addStretch(1)
        right.addLayout(action_row)
        right.addStretch(1)
        layout.addLayout(right, 2)

        # Wire up handlers
        self.btn_server_refresh.clicked.connect(self._refresh_servers)
        self.btn_server_discover.clicked.connect(self._discover_local_servers)
        self.btn_server_add.clicked.connect(self._start_add_server)
        self.btn_server_remove.clicked.connect(self._remove_selected_server)
        self.btn_server_save.clicked.connect(self._save_server_entry)
        self.btn_server_probe.clicked.connect(self._probe_selected_server)

        return group

    # --------------------
    # UI callbacks
    # --------------------
    def _save_settings(self) -> None:
        self.bridge.set_host(self.api.text().strip())
        result = self.bridge.save_settings({
            "API_BASE": self.api.text().strip(),
            "REMOTE_GPU_LIST": self.remote_list.text().strip()
        })
        ok = isinstance(result, dict) and result.get("ok")
        cfg = self.settings_manager.load()
        ui_cfg = cfg.get("ui", {})
        ui_cfg["menu_sort_mode"] = self.menu_sort.currentData()
        cfg["ui"] = ui_cfg
        self.settings_manager.save(cfg)

        parent = self.parent()
        while parent is not None and not hasattr(parent, "reload_menus"):
            parent = parent.parent()
        if parent is not None and hasattr(parent, "reload_menus"):
            try:
                parent.reload_menus()
            except Exception:
                pass
        QMessageBox.information(self, "Settings", "Saved" if ok else "Failed")

    def _start_add_server(self) -> None:
        self._editing_provider_id = None
        self.server_list.clearSelection()
        self.server_status_label.setText("Adding new provider …")
        self.server_name_edit.clear()
        self.server_url_edit.clear()
        self.server_kind_combo.setCurrentText("remote")
        self.server_service_combo.setCurrentText("lan")
        self.server_priority_spin.setValue(50)
        self.server_active_check.setChecked(True)

    def _on_server_selected(self, current: QListWidgetItem | None, _: QListWidgetItem | None = None) -> None:
        if current is None:
            self._editing_provider_id = None
            return
        provider_id = current.data(Qt.UserRole)
        entry = self._providers_cache.get(provider_id) or self.provider_registry.get(provider_id)
        if not entry:
            self.server_status_label.setText("Provider data unavailable.")
            return
        self._editing_provider_id = provider_id
        self.server_name_edit.setText(entry.get("name", provider_id))
        self.server_url_edit.setText(entry.get("base_url", ""))
        self.server_kind_combo.setCurrentText(entry.get("kind", "remote"))
        self.server_service_combo.setCurrentText(entry.get("service", "lan"))
        self.server_priority_spin.setValue(int(entry.get("priority", 50)))
        self.server_active_check.setChecked(bool(entry.get("active", True)))
        health = entry.get("last_health") or {}
        status = "Unknown"
        if isinstance(health, dict):
            if health.get("ok") is True:
                status = f"🟢 Healthy (ts={health.get('ts')})"
            elif health.get("ok") is False:
                status = f"🔴 Offline (ts={health.get('ts')})"
        self.server_status_label.setText(f"Provider ID: {provider_id} · {status}")

    def _save_server_entry(self) -> None:
        name = self.server_name_edit.text().strip()
        base_url = self.server_url_edit.text().strip()
        if not base_url:
            QMessageBox.warning(self, "Server Settings", "Base URL is required.")
            return
        payload = {
            "id": self._editing_provider_id,
            "name": name or base_url,
            "base_url": base_url,
            "kind": self.server_kind_combo.currentText(),
            "service": self.server_service_combo.currentText(),
            "priority": self.server_priority_spin.value(),
            "active": self.server_active_check.isChecked(),
        }
        try:
            entry = self.provider_registry.register(payload)
            self._providers_cache[entry["id"]] = entry
        except Exception as exc:
            QMessageBox.critical(self, "Server Settings", f"Failed to save provider: {exc}")
            return

        # Inform running server if reachable.
        try:
            self.bridge.providers_register(payload)
        except Exception:
            pass

        QMessageBox.information(self, "Server Settings", "Provider saved.")
        self._refresh_servers(select_id=entry["id"])

    def _remove_selected_server(self) -> None:
        if not self._editing_provider_id:
            QMessageBox.information(self, "Server Settings", "Select a provider to remove.")
            return
        provider_id = self._editing_provider_id
        confirm = QMessageBox.question(
            self,
            "Remove Provider",
            f"Remove provider '{provider_id}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            removed = self.provider_registry.remove(provider_id)
        except Exception as exc:
            QMessageBox.warning(self, "Server Settings", f"Unable to remove provider: {exc}")
            return
        if not removed:
            QMessageBox.warning(self, "Server Settings", "Provider not found.")
            return
        try:
            self.bridge.providers_remove(provider_id)
        except Exception:
            pass
        QMessageBox.information(self, "Server Settings", "Provider removed.")
        self._editing_provider_id = None
        self._refresh_servers()

    def _probe_selected_server(self) -> None:
        if not self._editing_provider_id:
            QMessageBox.information(self, "Server Settings", "Select a provider to probe.")
            return
        entry = self.provider_registry.get(self._editing_provider_id)
        if not entry:
            QMessageBox.warning(self, "Server Settings", "Provider definition missing.")
            return
        # Try server-side health check first
        status = self.bridge.providers_health(self._editing_provider_id)
        if status and status.get("status"):
            payload = status["status"] if "status" in status else status
            ok = payload.get("ok")
            stamp = payload.get("ts")
            msg = "🟢 Provider healthy" if ok else "🔴 Provider unreachable"
            if stamp:
                msg += f" (ts={stamp})"
            self.server_status_label.setText(f"Provider ID: {self._editing_provider_id} · {msg}")
            self._refresh_servers(select_id=self._editing_provider_id)
            return
        # Fallback: direct probe
        probe = ServerBridge(base=entry.get("base_url", ""))
        healthy = probe.ping()
        msg = "🟢 Direct probe succeeded" if healthy else "🔴 Direct probe failed"
        self.server_status_label.setText(f"Provider ID: {self._editing_provider_id} · {msg}")
        if healthy:
            self._refresh_servers(select_id=self._editing_provider_id)

    def _discover_local_servers(self) -> None:
        candidates = [8001, 8130, 8188, 9000]
        existing_urls = {entry.get("base_url") for entry in self.provider_registry.list()}
        added = []
        for port in candidates:
            base_url = f"http://127.0.0.1:{port}"
            if base_url in existing_urls:
                continue
            bridge = ServerBridge(base=base_url)
            if bridge.ping():
                payload = {
                    "name": f"Local ({port})",
                    "base_url": base_url,
                    "kind": "local",
                    "service": "comfyui",
                    "priority": port,
                    "active": True,
                }
                entry = self.provider_registry.register(payload)
                self._providers_cache[entry["id"]] = entry
                try:
                    self.bridge.providers_register(payload)
                except Exception:
                    pass
                added.append(base_url)
        if added:
            QMessageBox.information(
                self,
                "Server Discovery",
                f"Discovered and registered {len(added)} local endpoint(s).\n" + "\n".join(added),
            )
            self._refresh_servers()
        else:
            QMessageBox.information(self, "Server Discovery", "No new local servers detected.")

    # --------------------
    # Data helpers
    # --------------------
    def _refresh_servers(self, select_id: str | None = None) -> None:
        merged: dict[str, dict] = {}
        local_entries = self.provider_registry.list()
        for entry in local_entries:
            merged[entry["id"]] = entry
        payload = self.bridge.providers_list()
        if payload and isinstance(payload.get("providers"), list):
            for entry in payload["providers"]:
                pid = entry.get("id")
                if not pid:
                    continue
                merged[pid] = {**merged.get(pid, {}), **entry}
        self._providers_cache = merged
        self.server_list.blockSignals(True)
        self.server_list.clear()
        for pid, entry in sorted(merged.items(), key=lambda item: item[1].get("priority", 999)):
            health = entry.get("last_health") or {}
            symbol = "🟢" if health.get("ok") is True else "🟠" if health.get("ok") is False else "⚪"
            text = f"{symbol} {entry.get('name', pid)}  ({entry.get('base_url', 'n/a')})"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, pid)
            self.server_list.addItem(item)
            if select_id and pid == select_id:
                self.server_list.setCurrentItem(item)
        if self.server_list.count() and not self.server_list.currentItem():
            self.server_list.setCurrentRow(0)
        if not self.server_list.count():
            self.server_status_label.setText("No providers configured.")
        self.server_list.blockSignals(False)
