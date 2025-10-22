import json
import logging
import os
import socket
from pathlib import Path
from typing import Dict, Mapping, Optional
from urllib.parse import urlparse

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

# comfyvn/gui/panels/settings_panel.py  [Studio-090]
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
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

from comfyvn.accessibility import AccessibilityState, accessibility_manager
from comfyvn.accessibility import filters as accessibility_filters
from comfyvn.accessibility.input_map import InputBinding, input_map_manager
from comfyvn.config import feature_flags
from comfyvn.config import ports as ports_config
from comfyvn.config.baseurl_authority import current_authority, default_base_url
from comfyvn.core.compute_registry import ComputeProviderRegistry
from comfyvn.core.notifier import notifier
from comfyvn.core.settings_manager import SettingsManager
from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.gui.widgets.drawer import Drawer, DrawerContainer
from comfyvn.gui.widgets.shortcut_capture import ShortcutCapture

logger = logging.getLogger(__name__)


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
        self._accessibility_manager = accessibility_manager
        self._accessibility_token: str | None = None
        self._accessibility_updating = False
        self._input_token: str | None = None
        self._input_rows: dict[
            str, tuple[ShortcutCapture, ShortcutCapture, QComboBox]
        ] = {}

        w = QWidget()
        root = QVBoxLayout(w)

        (
            self._comfy_config_combined,
            self._comfy_config_payload,
            self._comfy_config_path,
        ) = self._load_comfy_config()
        basics_widget = QWidget()
        form = QFormLayout(basics_widget)
        cfg_snapshot = self.settings_manager.load()
        server_cfg = cfg_snapshot.get("server", {})
        authority = current_authority()
        port_config = ports_config.get_config()
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
        port_candidates = port_config.get("ports", [])
        default_port = authority.port
        if isinstance(port_candidates, (list, tuple)):
            for item in port_candidates:
                try:
                    default_port = int(item)
                except (TypeError, ValueError):
                    continue
                else:
                    break
        if "local_port" in server_cfg:
            try:
                default_port = int(server_cfg.get("local_port"))
            except (TypeError, ValueError):
                pass
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
        st_cfg = dict(cfg_snapshot.get("integrations", {}).get("sillytavern", {}))
        self.st_host = QLineEdit(st_cfg.get("host", "127.0.0.1"))
        st_port_value = 8000
        try:
            st_port_value = int(st_cfg.get("port", st_port_value))
        except (TypeError, ValueError):
            st_port_value = 8000
        self.st_port = QSpinBox()
        self.st_port.setRange(1, 65535)
        self.st_port.setValue(st_port_value)
        plugin_base = str(
            st_cfg.get("plugin_base", "/api/plugins/comfyvn-data-exporter")
        )
        if plugin_base and not plugin_base.startswith("/"):
            plugin_base = f"/{plugin_base.lstrip('/')}"
        self.st_base_path = QLineEdit(
            plugin_base or "/api/plugins/comfyvn-data-exporter"
        )
        btn_save = QPushButton("Save UI Settings")
        btn_save.clicked.connect(self._save_settings)
        form.addRow("API Base URL:", self.api)
        form.addRow("Local Backend Port:", port_row_widget)
        form.addRow("Legacy Remote GPU Endpoints:", self.remote_list)
        form.addRow("Menu Sort Order:", self.menu_sort)
        form.addRow("SillyTavern Host:", self.st_host)
        form.addRow("SillyTavern Port:", self.st_port)
        form.addRow("SillyTavern Plugin Base:", self.st_base_path)
        form.addRow(btn_save)

        drawer_container = DrawerContainer()
        drawer_container.add_drawer(Drawer("Studio Basics", basics_widget))

        self.server_group = self._build_server_controls()
        drawer_container.add_drawer(Drawer("Compute & Server", self.server_group))

        self.audio_group = self._build_audio_settings(cfg_snapshot)
        drawer_container.add_drawer(Drawer("Audio & Music", self.audio_group))

        features_state = feature_flags.load_feature_flags()
        if features_state.get("enable_accessibility_controls", True):
            self.accessibility_group = self._build_accessibility_settings()
            drawer_container.add_drawer(
                Drawer("Accessibility", self.accessibility_group, start_open=False)
            )
            self._accessibility_token = self._accessibility_manager.subscribe(
                self._on_accessibility_state_changed
            )
            self.destroyed.connect(self._cleanup_accessibility_subscription)

        if features_state.get("enable_controller_profiles", True):
            self.input_group = self._build_input_settings()
            drawer_container.add_drawer(
                Drawer("Input & Controllers", self.input_group, start_open=False)
            )
            self._input_token = input_map_manager.subscribe(
                self._on_input_bindings_changed
            )
            self.destroyed.connect(self._cleanup_input_subscription)

        self.debug_group = self._build_debug_settings()
        drawer_container.add_drawer(
            Drawer("Debug & Feature Flags", self.debug_group, start_open=False)
        )

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

    def _build_debug_settings(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        features = dict(self._comfy_config_combined.get("features") or {})
        self.bridge_hardening_checkbox = QCheckBox(
            "Enable ComfyUI hardened bridge (override injection + LoRA)"
        )
        self.bridge_hardening_checkbox.setChecked(
            bool(features.get("enable_comfy_bridge_hardening", False))
        )
        self.bridge_hardening_checkbox.stateChanged.connect(
            self._on_bridge_hardening_toggled
        )
        layout.addWidget(self.bridge_hardening_checkbox)

        hint = QLabel(
            "When enabled, ComfyUI submissions are routed through the hardened bridge "
            "which injects prompt overrides, merges per-character LoRAs, polls for completion, "
            "and returns resolved artifact paths plus sidecar data. Requires a reachable ComfyUI instance."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666666;")
        layout.addWidget(hint)

        self.preview_stream_checkbox = QCheckBox(
            "Capture ComfyUI preview stream snapshots"
        )
        self.preview_stream_checkbox.setChecked(
            bool(features.get("enable_comfy_preview_stream", False))
        )
        self.preview_stream_checkbox.stateChanged.connect(
            lambda state: self._on_feature_flag_checkbox(
                "enable_comfy_preview_stream", state
            )
        )
        layout.addWidget(self.preview_stream_checkbox)

        preview_hint = QLabel(
            "Stores intermediate images and manifests under data/cache/comfy_previews "
            "so the VN Viewer can reflect live renders."
        )
        preview_hint.setWordWrap(True)
        preview_hint.setStyleSheet("color: #666666;")
        layout.addWidget(preview_hint)

        self.silly_bridge_checkbox = QCheckBox("Enable SillyTavern bridge integration")
        self.silly_bridge_checkbox.setChecked(
            bool(features.get("enable_sillytavern_bridge", False))
        )
        self.silly_bridge_checkbox.stateChanged.connect(
            lambda state: self._on_feature_flag_checkbox(
                "enable_sillytavern_bridge", state
            )
        )
        layout.addWidget(self.silly_bridge_checkbox)

        st_hint = QLabel(
            "Controls the SillyTavern export bridge, including world sync and asset import helpers."
        )
        st_hint.setWordWrap(True)
        st_hint.setStyleSheet("color: #666666;")
        layout.addWidget(st_hint)

        self.narrator_mode_checkbox = QCheckBox("Enable Narrator presentation mode")
        self.narrator_mode_checkbox.setChecked(
            bool(features.get("enable_narrator_mode", False))
        )
        self.narrator_mode_checkbox.stateChanged.connect(
            lambda state: self._on_feature_flag_checkbox("enable_narrator_mode", state)
        )
        layout.addWidget(self.narrator_mode_checkbox)

        narrator_hint = QLabel(
            "Adds narrator-forward overlays in the VN Viewer so directs and modders can focus on scene pacing."
        )
        narrator_hint.setWordWrap(True)
        narrator_hint.setStyleSheet("color: #666666;")
        layout.addWidget(narrator_hint)

        image_flag_default = bool(
            features.get(
                "enable_public_image_providers",
                features.get("enable_public_image_video", False),
            )
        )
        self.public_image_checkbox = QCheckBox(
            "Enable public image providers (Stability, fal.ai)"
        )
        self.public_image_checkbox.setChecked(image_flag_default)
        self.public_image_checkbox.stateChanged.connect(
            lambda state: self._on_public_media_flag("image", state)
        )
        layout.addWidget(self.public_image_checkbox)

        image_hint = QLabel(
            "Dry-run adapters for Stability and fal.ai stay active until API keys are added; "
            "payload shapes are logged for debugging."
        )
        image_hint.setWordWrap(True)
        image_hint.setStyleSheet("color: #666666;")
        layout.addWidget(image_hint)

        video_flag_default = bool(
            features.get(
                "enable_public_video_providers",
                features.get("enable_public_image_video", False),
            )
        )
        self.public_video_checkbox = QCheckBox(
            "Enable public video providers (Runway, Pika, Luma)"
        )
        self.public_video_checkbox.setChecked(video_flag_default)
        self.public_video_checkbox.stateChanged.connect(
            lambda state: self._on_public_media_flag("video", state)
        )
        layout.addWidget(self.public_video_checkbox)

        video_hint = QLabel(
            "Video endpoints remain dry-run until credentials exist; cost estimates surface in the job log."
        )
        video_hint.setWordWrap(True)
        video_hint.setStyleSheet("color: #666666;")
        layout.addWidget(video_hint)

        self.telemetry_checkbox = QCheckBox("Enable privacy-aware telemetry counters")
        telemetry_flag_default = bool(
            features.get(
                "enable_observability",
                features.get("enable_privacy_telemetry", False),
            )
        )
        self.telemetry_checkbox.setChecked(telemetry_flag_default)
        self.telemetry_checkbox.stateChanged.connect(self._on_observability_flag)
        layout.addWidget(self.telemetry_checkbox)

        telemetry_hint = QLabel(
            "Requires the enable_observability flag plus consent via Settings → Debug & Feature Flags "
            "or POST /api/telemetry/opt_in; "
            "counters stay local while telemetry dry-run remains true."
        )
        telemetry_hint.setWordWrap(True)
        telemetry_hint.setStyleSheet("color: #666666;")
        layout.addWidget(telemetry_hint)

        self.crash_upload_checkbox = QCheckBox(
            "Enable crash upload diagnostics (opt-in)"
        )
        self.crash_upload_checkbox.setChecked(
            bool(features.get("enable_crash_uploader", False))
        )
        self.crash_upload_checkbox.stateChanged.connect(
            lambda state: self._on_feature_flag_checkbox("enable_crash_uploader", state)
        )
        layout.addWidget(self.crash_upload_checkbox)

        crash_hint = QLabel(
            "Combines with telemetry consent to register crash digests and unlock /api/telemetry/diagnostics exports."
        )
        crash_hint.setWordWrap(True)
        crash_hint.setStyleSheet("color: #666666;")
        layout.addWidget(crash_hint)

        self.accessibility_controls_checkbox = QCheckBox(
            "Enable accessibility controls (UI + overlays)"
        )
        self.accessibility_controls_checkbox.setChecked(
            bool(features.get("enable_accessibility_controls", True))
        )
        self.accessibility_controls_checkbox.stateChanged.connect(
            lambda state: self._on_feature_flag_checkbox(
                "enable_accessibility_controls", state
            )
        )
        layout.addWidget(self.accessibility_controls_checkbox)

        accessibility_controls_hint = QLabel(
            "Hide the Accessibility drawer when packaging kiosk builds or running headless tests."
        )
        accessibility_controls_hint.setWordWrap(True)
        accessibility_controls_hint.setStyleSheet("color: #666666;")
        layout.addWidget(accessibility_controls_hint)

        self.accessibility_api_checkbox = QCheckBox(
            "Enable accessibility REST/WebSocket surfaces"
        )
        self.accessibility_api_checkbox.setChecked(
            bool(features.get("enable_accessibility_api", True))
        )
        self.accessibility_api_checkbox.stateChanged.connect(
            lambda state: self._on_feature_flag_checkbox(
                "enable_accessibility_api", state
            )
        )
        layout.addWidget(self.accessibility_api_checkbox)

        accessibility_api_hint = QLabel(
            "Disable when exposing the server without auth; subtitles and settings remain local-only."
        )
        accessibility_api_hint.setWordWrap(True)
        accessibility_api_hint.setStyleSheet("color: #666666;")
        layout.addWidget(accessibility_api_hint)

        self.controller_profiles_checkbox = QCheckBox(
            "Enable controller remapping profiles"
        )
        self.controller_profiles_checkbox.setChecked(
            bool(features.get("enable_controller_profiles", True))
        )
        self.controller_profiles_checkbox.stateChanged.connect(
            lambda state: self._on_feature_flag_checkbox(
                "enable_controller_profiles", state
            )
        )
        layout.addWidget(self.controller_profiles_checkbox)

        controller_hint = QLabel(
            "Required for controller/hotkey remaps exposed in the upcoming Input Mapping drawer."
        )
        controller_hint.setWordWrap(True)
        controller_hint.setStyleSheet("color: #666666;")
        layout.addWidget(controller_hint)

        layout.addStretch(1)
        return widget

    # --------------------
    # Feature config helpers
    # --------------------
    def _load_comfy_config(self) -> tuple[dict, dict, Path]:
        combined: dict = {}
        for candidate in (Path("comfyvn.json"), Path("config/comfyvn.json")):
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                combined.update(data)

        path = Path("config/comfyvn.json")
        payload: dict = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    payload = existing
            except Exception:
                payload = {}

        if not payload:
            payload = {}
            if "features" in combined:
                payload["features"] = dict(combined.get("features") or {})

        defaults = dict(feature_flags.FEATURE_DEFAULTS)
        combined_features = dict(defaults)
        combined_features.update(dict(combined.get("features") or {}))
        combined["features"] = combined_features

        payload = payload or {}
        payload_features = dict(defaults)
        payload_features.update(dict(payload.get("features") or {}))
        payload["features"] = payload_features

        return combined, payload, path

    def _persist_comfy_config(self) -> None:
        try:
            self._comfy_config_path.parent.mkdir(parents=True, exist_ok=True)
            self._comfy_config_path.write_text(
                json.dumps(self._comfy_config_payload, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Save Failed",
                f"Unable to update {self._comfy_config_path}: {exc}",
            )
            return

        # Update combined view so subsequent toggles stay in sync
        features = dict(self._comfy_config_payload.get("features") or {})
        combined_features = dict(self._comfy_config_combined.get("features") or {})
        combined_features.update(features)
        self._comfy_config_combined["features"] = combined_features
        try:
            feature_flags.refresh_cache()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to refresh feature flag cache: %s", exc)
        notifier.toast(
            "info",
            "Feature flags updated.",
            meta={"feature_flags": dict(combined_features)},
        )

    def _on_bridge_hardening_toggled(self, state: int) -> None:
        self._update_feature_flag("enable_comfy_bridge_hardening", state == Qt.Checked)

    def _on_feature_flag_checkbox(self, key: str, state: int) -> None:
        self._update_feature_flag(key, state == Qt.Checked)

    def _on_observability_flag(self, state: int) -> None:
        enabled = state == Qt.Checked
        self._update_feature_flags(
            {
                "enable_observability": enabled,
                "enable_privacy_telemetry": enabled,
            }
        )

    def _on_public_media_flag(self, kind: str, state: int) -> None:
        enabled = state == Qt.Checked
        if kind == "image":
            updates = {
                "enable_public_image_providers": enabled,
                "enable_public_image_video": enabled,
            }
        else:
            updates = {
                "enable_public_video_providers": enabled,
                "enable_public_image_video": enabled,
            }
        self._update_feature_flags(updates)

    def _update_feature_flag(self, key: str, enabled: bool) -> None:
        self._update_feature_flags({key: enabled})

    def _update_feature_flags(self, updates: Mapping[str, bool]) -> None:
        features = dict(self._comfy_config_payload.get("features") or {})
        changed = False
        for flag_key, state in updates.items():
            if features.get(flag_key) == state:
                continue
            features[flag_key] = state
            changed = True
        if not changed:
            return
        self._comfy_config_payload["features"] = features
        self._persist_comfy_config()

    def _build_accessibility_settings(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        state = self._accessibility_manager.snapshot()

        form = QFormLayout()
        form.setSpacing(8)

        self.access_font_scale_spin = QDoubleSpinBox()
        self.access_font_scale_spin.setRange(0.75, 2.5)
        self.access_font_scale_spin.setSingleStep(0.05)
        self.access_font_scale_spin.setValue(state.font_scale)
        self.access_font_scale_spin.setSuffix("×")
        self.access_font_scale_spin.valueChanged.connect(
            self._on_accessibility_widgets_changed
        )
        form.addRow("Font scale multiplier", self.access_font_scale_spin)

        ui_scale_presets = [1.0, 1.25, 1.5, 1.75, 2.0]
        self.access_ui_scale_combo = QComboBox()
        for scale in ui_scale_presets:
            percent = int(scale * 100)
            self.access_ui_scale_combo.addItem(f"{percent}%", scale)
        self._select_scale_combo(self.access_ui_scale_combo, state.ui_scale)
        self.access_ui_scale_combo.currentIndexChanged.connect(
            self._on_accessibility_widgets_changed
        )
        form.addRow("UI scale", self.access_ui_scale_combo)

        self.access_viewer_scale_combo = QComboBox()
        self.access_viewer_scale_combo.addItem("Follow global", None)
        for scale in ui_scale_presets:
            percent = int(scale * 100)
            self.access_viewer_scale_combo.addItem(f"{percent}% (Viewer)", scale)
        viewer_override = (state.view_overrides or {}).get("viewer")
        self._select_scale_combo(self.access_viewer_scale_combo, viewer_override)
        self.access_viewer_scale_combo.currentIndexChanged.connect(
            self._on_accessibility_widgets_changed
        )
        form.addRow("Viewer override", self.access_viewer_scale_combo)

        self.access_color_filter_combo = QComboBox()
        for spec in accessibility_filters.AVAILABLE_FILTERS:
            self.access_color_filter_combo.addItem(spec.label, spec.key)
        index = self.access_color_filter_combo.findData(state.color_filter)
        if index != -1:
            self.access_color_filter_combo.setCurrentIndex(index)
        self.access_color_filter_combo.currentIndexChanged.connect(
            self._on_accessibility_widgets_changed
        )
        form.addRow("Color filter", self.access_color_filter_combo)

        self.access_high_contrast_check = QCheckBox("Enable high-contrast palette")
        self.access_high_contrast_check.setChecked(state.high_contrast)
        self.access_high_contrast_check.stateChanged.connect(
            self._on_accessibility_widgets_changed
        )
        form.addRow("High contrast", self.access_high_contrast_check)

        self.access_subtitles_check = QCheckBox("Display subtitles overlay in viewer")
        self.access_subtitles_check.setChecked(state.subtitles_enabled)
        self.access_subtitles_check.stateChanged.connect(
            self._on_accessibility_widgets_changed
        )
        form.addRow("Subtitles", self.access_subtitles_check)

        layout.addLayout(form)

        hint = QLabel(
            "Changes apply instantly and persist to config/settings/accessibility."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6b7280;")
        layout.addWidget(hint)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        reset_btn = QPushButton("Reset Accessibility")
        reset_btn.clicked.connect(self._on_accessibility_reset)
        button_row.addWidget(reset_btn)
        layout.addLayout(button_row)

        layout.addStretch(1)
        return widget

    def _on_accessibility_widgets_changed(self, *_args) -> None:
        if self._accessibility_updating:
            return
        font_widget = getattr(self, "access_font_scale_spin", None)
        if font_widget is None:
            return
        font_scale = float(font_widget.value())
        ui_scale_widget = getattr(self, "access_ui_scale_combo", None)
        ui_scale = (
            float(ui_scale_widget.currentData() or 1.0) if ui_scale_widget else 1.0
        )
        viewer_scale_widget = getattr(self, "access_viewer_scale_combo", None)
        viewer_override_raw = (
            viewer_scale_widget.currentData() if viewer_scale_widget else None
        )
        overrides = {}
        if viewer_override_raw is not None:
            overrides["viewer"] = float(viewer_override_raw)
        color_data = self.access_color_filter_combo.currentData()
        color_filter = str(color_data or "none")
        high_contrast = self.access_high_contrast_check.isChecked()
        subtitles_enabled = self.access_subtitles_check.isChecked()
        self._accessibility_manager.update(
            font_scale=font_scale,
            color_filter=color_filter,
            high_contrast=high_contrast,
            subtitles_enabled=subtitles_enabled,
            ui_scale=ui_scale,
            view_overrides=overrides,
        )

    def _on_accessibility_state_changed(self, state: AccessibilityState) -> None:
        if not hasattr(self, "access_font_scale_spin"):
            return
        self._accessibility_updating = True
        try:
            self.access_font_scale_spin.setValue(state.font_scale)
            self._select_scale_combo(self.access_ui_scale_combo, state.ui_scale)
            viewer_override = (state.view_overrides or {}).get("viewer")
            self._select_scale_combo(self.access_viewer_scale_combo, viewer_override)
            index = self.access_color_filter_combo.findData(state.color_filter)
            if index != -1:
                self.access_color_filter_combo.setCurrentIndex(index)
            self.access_high_contrast_check.setChecked(state.high_contrast)
            self.access_subtitles_check.setChecked(state.subtitles_enabled)
        finally:
            self._accessibility_updating = False

    def _select_scale_combo(self, combo: QComboBox, value: Optional[float]) -> None:
        target = None if value is None else round(float(value), 3)
        for idx in range(combo.count()):
            data = combo.itemData(idx)
            if data is None and target is None:
                combo.setCurrentIndex(idx)
                return
            if data is not None and round(float(data), 3) == target:
                combo.setCurrentIndex(idx)
                return
        if target is not None:
            label = f"{int(target * 100)}%"
            combo.addItem(label, target)
            combo.setCurrentIndex(combo.count() - 1)

    def _on_accessibility_reset(self) -> None:
        self._accessibility_manager.reset()

    def _cleanup_accessibility_subscription(self, *_args) -> None:
        if self._accessibility_token:
            self._accessibility_manager.unsubscribe(self._accessibility_token)
            self._accessibility_token = None

    def _build_input_settings(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        bindings = input_map_manager.bindings()
        for action, binding in bindings.items():
            group = QGroupBox(binding.label)
            form = QFormLayout(group)
            form.setSpacing(6)

            primary_capture = ShortcutCapture()
            self._set_capture_value(primary_capture, binding.primary)
            primary_record = QPushButton("Record")
            primary_record.clicked.connect(
                lambda _=False, cap=primary_capture: cap.setFocus()
            )
            primary_clear = QPushButton("Clear")
            primary_clear.clicked.connect(
                lambda _=False, cap=primary_capture: self._clear_capture(cap)
            )
            primary_row = QWidget()
            primary_layout = QHBoxLayout(primary_row)
            primary_layout.setContentsMargins(0, 0, 0, 0)
            primary_layout.setSpacing(4)
            primary_layout.addWidget(primary_capture, 1)
            primary_layout.addWidget(primary_record)
            primary_layout.addWidget(primary_clear)
            form.addRow("Primary", primary_row)

            secondary_capture = ShortcutCapture()
            self._set_capture_value(secondary_capture, binding.secondary)
            secondary_record = QPushButton("Record")
            secondary_record.clicked.connect(
                lambda _=False, cap=secondary_capture: cap.setFocus()
            )
            secondary_clear = QPushButton("Clear")
            secondary_clear.clicked.connect(
                lambda _=False, cap=secondary_capture: self._clear_capture(cap)
            )
            secondary_row = QWidget()
            secondary_layout = QHBoxLayout(secondary_row)
            secondary_layout.setContentsMargins(0, 0, 0, 0)
            secondary_layout.setSpacing(4)
            secondary_layout.addWidget(secondary_capture, 1)
            secondary_layout.addWidget(secondary_record)
            secondary_layout.addWidget(secondary_clear)
            form.addRow("Secondary", secondary_row)

            controller_combo = QComboBox()
            for key, label in input_map_manager.available_gamepad_bindings():
                controller_combo.addItem(label, key)
            current_index = controller_combo.findData(binding.gamepad or "")
            if current_index != -1:
                controller_combo.setCurrentIndex(current_index)
            form.addRow("Controller", controller_combo)

            button_row = QWidget()
            button_layout = QHBoxLayout(button_row)
            button_layout.setContentsMargins(0, 0, 0, 0)
            button_layout.setSpacing(6)
            apply_btn = QPushButton("Apply")
            apply_btn.clicked.connect(
                lambda _=False, act=action: self._apply_input_binding(act)
            )
            reset_btn = QPushButton("Reset")
            reset_btn.clicked.connect(
                lambda _=False, act=action: self._reset_input_binding(act)
            )
            button_layout.addStretch(1)
            button_layout.addWidget(apply_btn)
            button_layout.addWidget(reset_btn)
            form.addRow("", button_row)

            layout.addWidget(group)
            self._input_rows[action] = (
                primary_capture,
                secondary_capture,
                controller_combo,
            )

        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addStretch(1)
        reset_all = QPushButton("Reset All Input Bindings")
        reset_all.clicked.connect(self._reset_all_input_bindings)
        footer_layout.addWidget(reset_all)
        layout.addWidget(footer)
        layout.addStretch(1)
        return widget

    def _set_capture_value(
        self, capture: ShortcutCapture, value: Optional[str]
    ) -> None:
        capture._seq = value  # type: ignore[attr-defined]
        capture.setText(value or "")

    def _clear_capture(self, capture: ShortcutCapture) -> None:
        capture._seq = None  # type: ignore[attr-defined]
        capture.setText("")

    def _read_capture(self, capture: ShortcutCapture) -> Optional[str]:
        seq = capture.sequence()
        if seq:
            return seq
        text = capture.text().strip()
        return text or None

    def _apply_input_binding(self, action: str) -> None:
        row = self._input_rows.get(action)
        if not row:
            return
        primary_capture, secondary_capture, controller_combo = row
        primary = self._read_capture(primary_capture)
        secondary = self._read_capture(secondary_capture)
        gamepad = controller_combo.currentData()
        input_map_manager.update_binding(
            action,
            primary=primary,
            secondary=secondary,
            gamepad=gamepad,
        )

    def _reset_input_binding(self, action: str) -> None:
        default_binding = input_map_manager.default_bindings().get(action)
        if not default_binding:
            return
        input_map_manager.update_binding(
            action,
            primary=default_binding.primary,
            secondary=default_binding.secondary,
            gamepad=default_binding.gamepad,
        )

    def _reset_all_input_bindings(self) -> None:
        input_map_manager.reset()

    def _on_input_bindings_changed(self, bindings: Dict[str, InputBinding]) -> None:
        for action, row in self._input_rows.items():
            binding = bindings.get(action)
            if not binding:
                continue
            primary_capture, secondary_capture, controller_combo = row
            self._set_capture_value(primary_capture, binding.primary)
            self._set_capture_value(secondary_capture, binding.secondary)
            index = controller_combo.findData(binding.gamepad or "")
            if index != -1:
                controller_combo.setCurrentIndex(index)

    def _cleanup_input_subscription(self, *_args) -> None:
        if self._input_token:
            input_map_manager.unsubscribe(self._input_token)
            self._input_token = None

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
    @staticmethod
    def _build_sillytavern_base(host: str, port: int) -> str:
        raw = (host or "").strip()
        if not raw:
            raw = "127.0.0.1"
        parsed = urlparse(raw if "://" in raw else f"http://{raw}")
        scheme = parsed.scheme or "http"
        hostname = parsed.hostname or parsed.path or "127.0.0.1"
        effective_port = parsed.port or int(port or 0)
        netloc = hostname
        if effective_port:
            netloc = f"{hostname}:{effective_port}"
        return f"{scheme}://{netloc}".rstrip("/")

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
        integrations_cfg = cfg.setdefault("integrations", {})
        st_cfg = integrations_cfg.setdefault("sillytavern", {})
        st_host = self.st_host.text().strip() or "127.0.0.1"
        st_port = int(self.st_port.value())
        plugin_base = (
            self.st_base_path.text().strip() or "/api/plugins/comfyvn-data-exporter"
        )
        if not plugin_base.startswith("/"):
            plugin_base = f"/{plugin_base.lstrip('/')}"
        st_cfg.update(
            {
                "host": st_host,
                "port": st_port,
                "plugin_base": plugin_base,
                "base_url": self._build_sillytavern_base(st_host, st_port),
            }
        )
        if "endpoint" not in st_cfg or not st_cfg["endpoint"]:
            st_cfg["endpoint"] = f"{self.bridge.base_url.rstrip('/')}/st/import"
        self.settings_manager.save(cfg)
        authority = current_authority(refresh=True)
        port_cfg = ports_config.get_config()
        host = str(port_cfg.get("host") or authority.host)
        public_base = port_cfg.get("public_base")
        ports = port_cfg.get("ports") or []
        normalized_ports: list[int] = []
        if isinstance(ports, (list, tuple)):
            for item in ports:
                try:
                    value = int(item)
                except (TypeError, ValueError):
                    continue
                if value not in normalized_ports:
                    normalized_ports.append(value)
        new_port = int(self.local_port.value())
        if new_port in normalized_ports:
            normalized_ports.remove(new_port)
        ports_config.set_config(
            host,
            [new_port, *normalized_ports],
            (
                str(public_base).strip()
                if isinstance(public_base, str) and public_base
                else None
            ),
        )
        ports_config.record_runtime_state(
            host=host,
            ports=[new_port, *normalized_ports],
            active_port=new_port,
            base_url=None,
            public_base=(
                str(public_base).strip()
                if isinstance(public_base, str) and public_base
                else None
            ),
        )
        os.environ["COMFYVN_SERVER_PORT"] = str(new_port)
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
