import json
import os
import socket
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

# comfyvn/gui/panels/settings_panel.py  [Studio-090]
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from comfyvn.config.baseurl_authority import current_authority, default_base_url
from comfyvn.core.compute_registry import ComputeProviderRegistry
from comfyvn.core.settings_manager import SettingsManager
from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.gui.widgets.drawer import Drawer, DrawerContainer


class SettingsPanel(QDockWidget):
    def __init__(self, bridge: ServerBridge):
        super().__init__("Settings")
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.bridge = bridge
        self.settings_manager = SettingsManager()
        self.provider_registry = ComputeProviderRegistry()
        self._editing_provider_id: str | None = None
        self._providers_cache: dict[str, dict] = {}
        self._templates_cache: list[dict] = []

        w = QWidget()
        root = QVBoxLayout(w)

        basics_widget = QWidget()
        form = QFormLayout(basics_widget)
        cfg_snapshot = self.settings_manager.load()
        server_cfg = cfg_snapshot.get("server", {})
        authority = current_authority()
        self.api = QLineEdit(self.bridge.base)
        self.remote_list = QLineEdit(
            self.bridge.get(
                "REMOTE_GPU_LIST", default=default_base_url()  # legacy remote fallback
            )
        )
        self.menu_sort = QComboBox()
        self.menu_sort.addItem("Load order (default)", "load_order")
        self.menu_sort.addItem("Best practice structure", "best_practice")
        self.menu_sort.addItem("Alphabetical", "alphabetical")
        current_mode = cfg_snapshot.get("ui", {}).get("menu_sort_mode", "load_order")
        index = self.menu_sort.findData(current_mode)
        if index != -1:
            self.menu_sort.setCurrentIndex(index)
        default_port = int(server_cfg.get("local_port", authority.port))
        self.local_port = QSpinBox()
        self.local_port.setRange(1024, 65535)
        self.local_port.setValue(default_port)
        self.btn_port_scan = QPushButton("Find Open Port")
        self.btn_port_scan.clicked.connect(self._scan_local_port)
        port_row_widget = QWidget()
        port_row_layout = QHBoxLayout(port_row_widget)
        port_row_layout.setContentsMargins(0, 0, 0, 0)
        port_row_layout.addWidget(self.local_port)
        port_row_layout.addWidget(self.btn_port_scan)
        btn_save = QPushButton("Save UI Settings")
        btn_save.clicked.connect(self._save_settings)
        form.addRow("API Base URL:", self.api)
        form.addRow("Local Backend Port:", port_row_widget)
        form.addRow("Legacy Remote GPU Endpoints:", self.remote_list)
        form.addRow("Menu Sort Order:", self.menu_sort)
        form.addRow(btn_save)

        drawer_container = DrawerContainer()
        drawer_container.add_drawer(Drawer("Studio Basics", basics_widget))

        self.server_group = self._build_server_controls()
        drawer_container.add_drawer(Drawer("Compute & Server", self.server_group))

        self.audio_group = self._build_audio_settings(cfg_snapshot)
        drawer_container.add_drawer(Drawer("Audio & Music", self.audio_group))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(drawer_container)
        root.addWidget(scroll)

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

        template_row = QHBoxLayout()
        self.template_combo = QComboBox()
        self.template_combo.setEditable(False)
        self.template_combo.addItem("Template: Select…", "")
        self.btn_server_create_template = QPushButton("Create From Template")
        template_row.addWidget(self.template_combo)
        template_row.addWidget(self.btn_server_create_template)
        template_row.addStretch(1)
        left.addLayout(template_row)

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

        import_row = QHBoxLayout()
        self.btn_server_import = QPushButton("Import…")
        self.btn_server_export = QPushButton("Export…")
        import_row.addWidget(self.btn_server_import)
        import_row.addWidget(self.btn_server_export)
        import_row.addStretch(1)
        left.addLayout(import_row)

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
        self.btn_server_create_template.clicked.connect(
            self._create_provider_from_template
        )
        self.btn_server_export.clicked.connect(self._export_providers)
        self.btn_server_import.clicked.connect(self._import_providers)

        return group

    def _build_audio_settings(self, cfg_snapshot: dict) -> QGroupBox:
        group = QGroupBox("Audio & Music Pipelines")
        layout = QVBoxLayout(group)

        audio_cfg = cfg_snapshot.get("audio", {})
        tts_cfg = audio_cfg.get("tts", {})
        music_cfg = audio_cfg.get("music", {})

        # Clone provider definitions so we can mutate safely before save
        self._tts_providers = [
            dict(provider) for provider in tts_cfg.get("providers", [])
        ]
        self._music_providers = [
            dict(provider) for provider in music_cfg.get("providers", [])
        ]

        layout.addWidget(self._build_tts_settings(tts_cfg))
        layout.addWidget(self._build_music_settings(music_cfg))

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self.btn_audio_save = QPushButton("Save Audio Settings")
        self.btn_audio_save.clicked.connect(self._save_audio_settings)
        save_row.addWidget(self.btn_audio_save)
        layout.addLayout(save_row)

        return group

    def _build_tts_settings(self, tts_cfg: dict) -> QGroupBox:
        group = QGroupBox("Text-to-Speech Services")
        layout = QVBoxLayout(group)

        self.tts_provider_combo = QComboBox()
        for provider in self._tts_providers:
            label = provider.get("label") or provider.get("id") or "provider"
            kind = (provider.get("kind") or "unknown").replace("_", " ")
            self.tts_provider_combo.addItem(f"{label} ({kind})", provider.get("id"))
        active_id = tts_cfg.get("active_provider")
        index = self.tts_provider_combo.findData(active_id)
        if index != -1:
            self.tts_provider_combo.setCurrentIndex(index)

        layout.addWidget(QLabel("Active Provider:"))
        layout.addWidget(self.tts_provider_combo)

        self.tts_provider_details = QLabel()
        self.tts_provider_details.setWordWrap(True)
        layout.addWidget(self.tts_provider_details)

        self.tts_base_url = QLineEdit()
        self.tts_workflow_path = QLineEdit()
        self.tts_output_dir = QLineEdit()

        form = QFormLayout()
        form.addRow("ComfyUI Base URL:", self.tts_base_url)
        form.addRow("Workflow JSON:", self.tts_workflow_path)
        form.addRow("Output Directory:", self.tts_output_dir)
        layout.addLayout(form)

        self.tts_provider_combo.currentIndexChanged.connect(
            self._on_tts_provider_changed
        )
        self._on_tts_provider_changed()

        return group

    def _build_music_settings(self, music_cfg: dict) -> QGroupBox:
        group = QGroupBox("Music Remix Services")
        layout = QVBoxLayout(group)

        self.music_provider_combo = QComboBox()
        for provider in self._music_providers:
            label = provider.get("label") or provider.get("id") or "provider"
            kind = (provider.get("kind") or "unknown").replace("_", " ")
            self.music_provider_combo.addItem(f"{label} ({kind})", provider.get("id"))
        active_id = music_cfg.get("active_provider")
        index = self.music_provider_combo.findData(active_id)
        if index != -1:
            self.music_provider_combo.setCurrentIndex(index)

        layout.addWidget(QLabel("Active Provider:"))
        layout.addWidget(self.music_provider_combo)

        self.music_provider_details = QLabel()
        self.music_provider_details.setWordWrap(True)
        layout.addWidget(self.music_provider_details)

        self.music_base_url = QLineEdit()
        self.music_workflow_path = QLineEdit()
        self.music_output_dir = QLineEdit()

        form = QFormLayout()
        form.addRow("ComfyUI Base URL:", self.music_base_url)
        form.addRow("Workflow JSON:", self.music_workflow_path)
        form.addRow("Output Directory:", self.music_output_dir)
        layout.addLayout(form)

        self.music_provider_combo.currentIndexChanged.connect(
            self._on_music_provider_changed
        )
        self._on_music_provider_changed()

        return group

    # --------------------
    # Audio helpers
    # --------------------
    @staticmethod
    def _get_provider(
        providers: list[dict], provider_id: Optional[str]
    ) -> Optional[dict]:
        for provider in providers:
            if provider.get("id") == provider_id:
                return provider
        return None

    def _on_tts_provider_changed(self) -> None:
        provider_id = self.tts_provider_combo.currentData()
        provider = self._get_provider(self._tts_providers, provider_id)
        details_lines: list[str] = []
        if provider:
            label = provider.get("label") or provider.get("id") or "provider"
            kind = provider.get("kind") or "unknown"
            details_lines.append(label)
            details_lines.append(f"Kind: {kind}")
            portal = provider.get("portal")
            if portal:
                details_lines.append(f"Portal: {portal}")
            notes = provider.get("notes")
            if notes:
                details_lines.append(notes)
        else:
            details_lines.append("Select a provider to view details.")
        self.tts_provider_details.setText("\n".join(details_lines))

        is_comfyui = provider is not None and str(provider.get("id", "")).startswith(
            "comfyui"
        )
        self.tts_base_url.setEnabled(is_comfyui)
        self.tts_workflow_path.setEnabled(is_comfyui)
        self.tts_output_dir.setEnabled(is_comfyui)
        if provider and is_comfyui:
            self.tts_base_url.setText(provider.get("base_url", ""))
            self.tts_workflow_path.setText(provider.get("workflow", ""))
            self.tts_output_dir.setText(provider.get("output_dir", ""))
        elif provider:
            self.tts_base_url.setText(provider.get("portal", ""))
            self.tts_workflow_path.clear()
            self.tts_output_dir.clear()
        else:
            self.tts_base_url.clear()
            self.tts_workflow_path.clear()
            self.tts_output_dir.clear()

    def _on_music_provider_changed(self) -> None:
        provider_id = self.music_provider_combo.currentData()
        provider = self._get_provider(self._music_providers, provider_id)
        details_lines: list[str] = []
        if provider:
            label = provider.get("label") or provider.get("id") or "provider"
            kind = provider.get("kind") or "unknown"
            details_lines.append(label)
            details_lines.append(f"Kind: {kind}")
            portal = provider.get("portal")
            if portal:
                details_lines.append(f"Portal: {portal}")
            notes = provider.get("notes")
            if notes:
                details_lines.append(notes)
        else:
            details_lines.append("Select a provider to view details.")
        self.music_provider_details.setText("\n".join(details_lines))

        is_comfyui = provider is not None and str(provider.get("id", "")).startswith(
            "comfyui"
        )
        self.music_base_url.setEnabled(is_comfyui)
        self.music_workflow_path.setEnabled(is_comfyui)
        self.music_output_dir.setEnabled(is_comfyui)
        if provider and is_comfyui:
            self.music_base_url.setText(provider.get("base_url", ""))
            self.music_workflow_path.setText(provider.get("workflow", ""))
            self.music_output_dir.setText(provider.get("output_dir", ""))
        elif provider:
            self.music_base_url.setText(provider.get("portal", ""))
            self.music_workflow_path.clear()
            self.music_output_dir.clear()
        else:
            self.music_base_url.clear()
            self.music_workflow_path.clear()
            self.music_output_dir.clear()

    def _save_audio_settings(self) -> None:
        cfg = self.settings_manager.load()
        audio_cfg = cfg.setdefault("audio", {})

        tts_cfg = audio_cfg.setdefault("tts", {})
        tts_cfg["active_provider"] = self.tts_provider_combo.currentData()
        updated_tts = []
        for provider in self._tts_providers:
            if provider.get("id") == "comfyui_local":
                provider["base_url"] = self.tts_base_url.text().strip()
                provider["workflow"] = self.tts_workflow_path.text().strip()
                provider["output_dir"] = self.tts_output_dir.text().strip()
            updated_tts.append(dict(provider))
        tts_cfg["providers"] = updated_tts

        music_cfg = audio_cfg.setdefault("music", {})
        music_cfg["active_provider"] = self.music_provider_combo.currentData()
        updated_music = []
        for provider in self._music_providers:
            if provider.get("id") == "comfyui_local":
                provider["base_url"] = self.music_base_url.text().strip()
                provider["workflow"] = self.music_workflow_path.text().strip()
                provider["output_dir"] = self.music_output_dir.text().strip()
            updated_music.append(dict(provider))
        music_cfg["providers"] = updated_music

        self.settings_manager.save(cfg)
        QMessageBox.information(
            self, "Audio Settings", "Audio pipeline settings saved."
        )

    # --------------------
    # UI callbacks
    # --------------------
    def _save_settings(self) -> None:
        self.bridge.set_host(self.api.text().strip())
        api_base = self.api.text().strip()
        result = self.bridge.save_settings(
            {"API_BASE": api_base, "REMOTE_GPU_LIST": self.remote_list.text().strip()}
        )
        ok = isinstance(result, dict) and result.get("ok")
        cfg = self.settings_manager.load()
        ui_cfg = cfg.get("ui", {})
        ui_cfg["menu_sort_mode"] = self.menu_sort.currentData()
        cfg["ui"] = ui_cfg
        server_cfg = cfg.get("server", {})
        server_cfg["local_port"] = self.local_port.value()
        cfg["server"] = server_cfg
        self.settings_manager.save(cfg)
        os.environ["COMFYVN_SERVER_PORT"] = str(self.local_port.value())
        if api_base:
            self.bridge.set_host(api_base)

        parent = self.parent()
        while parent is not None and not hasattr(parent, "reload_menus"):
            parent = parent.parent()
        if parent is not None and hasattr(parent, "reload_menus"):
            try:
                parent.reload_menus()
            except Exception:
                pass
        message = "Settings saved."
        if not ok:
            message += "\nWarning: failed to persist settings via API."
        message += "\nLocal backend port changes take effect next launch."
        QMessageBox.information(self, "Settings", message)

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

    def _get_template(self, template_id: str) -> dict | None:
        for template in self._templates_cache:
            if template.get("id") == template_id:
                return template
        return None

    def _create_provider_from_template(self) -> None:
        template_id = self.template_combo.currentData()
        if not template_id:
            QMessageBox.information(
                self, "Provider Templates", "Select a template first."
            )
            return
        template = self._get_template(template_id)
        if not template:
            QMessageBox.warning(
                self, "Provider Templates", f"Template '{template_id}' unavailable."
            )
            return

        default_name = template.get("name", template_id)
        name, ok = QInputDialog.getText(
            self,
            "Provider Name",
            "Display name:",
            text=default_name,
        )
        if not ok:
            return
        name = name.strip() or default_name

        base_default = template.get("base_url", "")
        base_url, ok = QInputDialog.getText(
            self,
            "Provider Base URL",
            "Base URL (override if needed):",
            text=base_default,
        )
        if not ok:
            return
        base_url = base_url.strip()
        if not base_url:
            QMessageBox.warning(self, "Provider Templates", "Base URL is required.")
            return

        config: dict[str, str] = {}
        fields = (
            template.get("fields")
            or template.get("metadata", {}).get("auth_fields")
            or []
        )
        for field in fields:
            value, ok = QInputDialog.getText(
                self,
                "Provider Credential",
                f"Enter value for '{field}':",
            )
            if not ok:
                return
            value = value.strip()
            if value:
                config[field] = value

        try:
            entry = self.provider_registry.create_from_template(
                template_id,
                name=name,
                base_url=base_url,
                config=config,
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Provider Templates", f"Failed to create provider: {exc}"
            )
            return

        payload = {
            "template_id": template_id,
            "id": entry.get("id"),
            "name": name,
            "base_url": base_url,
            "config": config,
        }

        try:
            self.bridge.providers_create(payload)
        except Exception:
            # Server may be offline; local registry already updated.
            pass

        QMessageBox.information(
            self,
            "Provider Templates",
            f"Provider '{entry.get('id')}' created from template.",
        )
        self._refresh_servers(select_id=entry.get("id"))

    def _export_providers(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Providers",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        include_secrets = (
            QMessageBox.question(
                self,
                "Export Providers",
                "Include secrets (API keys, tokens)?\nSelect 'No' for safe sharing.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )
        try:
            export = self.provider_registry.export_all(mask_secrets=not include_secrets)
        except Exception as exc:
            QMessageBox.critical(
                self, "Export Providers", f"Failed to build export: {exc}"
            )
            return

        try:
            api_result = self.bridge.providers_export(include_secrets=include_secrets)
            if api_result and isinstance(api_result.get("export"), dict):
                export = api_result["export"]
        except Exception:
            pass

        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(export, handle, indent=2)
        except Exception as exc:
            QMessageBox.critical(
                self, "Export Providers", f"Failed to write file: {exc}"
            )
            return

        QMessageBox.information(
            self, "Export Providers", f"Providers exported to:\n{path}"
        )

    def _import_providers(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Providers",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            QMessageBox.critical(
                self, "Import Providers", f"Failed to read file: {exc}"
            )
            return

        replace = (
            QMessageBox.question(
                self,
                "Import Providers",
                "Replace existing providers with this import?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )
        overwrite = (
            QMessageBox.question(
                self,
                "Import Providers",
                "Overwrite providers when IDs collide?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            == QMessageBox.Yes
        )

        try:
            imported = self.provider_registry.import_data(
                data,
                replace=replace,
                overwrite=overwrite,
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Import Providers", f"Failed to import providers: {exc}"
            )
            return

        payload: dict[str, object] = {
            "replace": replace,
            "overwrite": overwrite,
        }
        if isinstance(data, dict) and isinstance(data.get("providers"), list):
            payload["providers"] = data["providers"]
        elif isinstance(data, list):
            payload["providers"] = data
        else:
            payload["providers"] = [row for row in imported if isinstance(row, dict)]

        try:
            self.bridge.providers_import(payload)
        except Exception:
            pass

        QMessageBox.information(
            self,
            "Import Providers",
            f"Imported {len(imported)} provider(s).",
        )
        self._refresh_servers()

    def _on_server_selected(
        self, current: QListWidgetItem | None, _: QListWidgetItem | None = None
    ) -> None:
        if current is None:
            self._editing_provider_id = None
            return
        provider_id = current.data(Qt.UserRole)
        entry = self._providers_cache.get(provider_id) or self.provider_registry.get(
            provider_id
        )
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
            QMessageBox.critical(
                self, "Server Settings", f"Failed to save provider: {exc}"
            )
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
            QMessageBox.information(
                self, "Server Settings", "Select a provider to remove."
            )
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
            QMessageBox.warning(
                self, "Server Settings", f"Unable to remove provider: {exc}"
            )
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
            QMessageBox.information(
                self, "Server Settings", "Select a provider to probe."
            )
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
            self.server_status_label.setText(
                f"Provider ID: {self._editing_provider_id} · {msg}"
            )
            self._refresh_servers(select_id=self._editing_provider_id)
            return
        # Fallback: direct probe
        probe = ServerBridge(base=entry.get("base_url", ""))
        healthy = probe.ping()
        msg = "🟢 Direct probe succeeded" if healthy else "🔴 Direct probe failed"
        self.server_status_label.setText(
            f"Provider ID: {self._editing_provider_id} · {msg}"
        )
        if healthy:
            self._refresh_servers(select_id=self._editing_provider_id)

    def _discover_local_servers(self) -> None:
        candidates = [8001, 8130, 8188, 9000]
        existing_urls = {
            entry.get("base_url") for entry in self.provider_registry.list()
        }
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
                f"Discovered and registered {len(added)} local endpoint(s).\n"
                + "\n".join(added),
            )
            self._refresh_servers()
        else:
            QMessageBox.information(
                self, "Server Discovery", "No new local servers detected."
            )

    def _scan_local_port(self) -> None:
        start_port = self.local_port.value()
        candidate = self._find_available_port(start_port)
        if candidate == start_port:
            QMessageBox.information(
                self, "Port Scanner", f"Port {start_port} appears to be available."
            )
        else:
            self.local_port.setValue(candidate)
            QMessageBox.information(
                self,
                "Port Scanner",
                f"Port {start_port} is in use. Suggested open port: {candidate}",
            )

    def _find_available_port(self, start: int) -> int:
        port = max(1024, start)
        while port <= 65535:
            if self._is_port_free(port):
                return port
            port += 1
        return start

    @staticmethod
    def _is_port_free(port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
        finally:
            try:
                sock.close()
            except Exception:
                pass
        return True

    # --------------------
    # Data helpers
    # --------------------
    def _populate_template_combo(self) -> None:
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        self.template_combo.addItem("Template: Select…", "")
        templates = sorted(
            self._templates_cache,
            key=lambda item: item.get("priority", 999),
        )
        for template in templates:
            template_id = template.get("id")
            if not template_id:
                continue
            display = template.get("name") or template_id
            self.template_combo.addItem(display, template_id)
        self.template_combo.blockSignals(False)

    def _refresh_servers(self, select_id: str | None = None) -> None:
        merged: dict[str, dict] = {}
        local_entries = self.provider_registry.list()
        for entry in local_entries:
            merged[entry["id"]] = entry
        payload = self.bridge.providers_list()
        templates = self.provider_registry.templates_public()
        if payload and isinstance(payload.get("templates"), list):
            templates = payload["templates"]
        self._templates_cache = templates
        if payload and isinstance(payload.get("providers"), list):
            for entry in payload["providers"]:
                pid = entry.get("id")
                if not pid:
                    continue
                merged[pid] = {**merged.get(pid, {}), **entry}
        self._providers_cache = merged
        self.server_list.blockSignals(True)
        self.server_list.clear()
        for pid, entry in sorted(
            merged.items(), key=lambda item: item[1].get("priority", 999)
        ):
            health = entry.get("last_health") or {}
            symbol = (
                "🟢"
                if health.get("ok") is True
                else "🟠" if health.get("ok") is False else "⚪"
            )
            text = (
                f"{symbol} {entry.get('name', pid)}  ({entry.get('base_url', 'n/a')})"
            )
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
        self._populate_template_combo()
