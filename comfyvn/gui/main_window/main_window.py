# -------------------------------------------------------------
# 🎛️ ComfyVN Studio Main Window — modular, dynamic, efficient
# -------------------------------------------------------------
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests
from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from comfyvn.accessibility import accessibility_manager
from comfyvn.config import runtime_paths
from comfyvn.config.baseurl_authority import current_authority
from comfyvn.core.extensions_discovery import ExtensionMetadata, load_extension_metadata

# Dynamic systems
from comfyvn.core.menu_runtime_bridge import menu_registry, reload_from_extensions
from comfyvn.core.notifier import notifier
from comfyvn.core.shortcut_registry import load_shortcuts_from_folder, shortcut_registry
from comfyvn.core.theme_manager import apply_theme

# Central space
from comfyvn.gui.central import CenterRouter, VNChatPanel
from comfyvn.gui.core.dock_manager import DockManager
from comfyvn.gui.core.workspace_controller import WorkspaceController

# Menus
from comfyvn.gui.main_window.menu_bar import (
    ensure_menu_bar,
    rebuild_menus_from_registry,
    update_window_menu_state,
)
from comfyvn.gui.main_window.menu_defaults import register_core_menu_items
from comfyvn.gui.main_window.recent_projects import load_recent, touch_recent
from comfyvn.gui.panels.advisory_panel import AdvisoryPanel
from comfyvn.gui.panels.asset_browser import AssetBrowser
from comfyvn.gui.panels.audio_panel import AudioPanel
from comfyvn.gui.panels.characters_panel import CharactersPanel
from comfyvn.gui.panels.debug_integrations import DebugIntegrationsPanel
from comfyvn.gui.panels.diffmerge_graph_panel import DiffmergeGraphPanel
from comfyvn.gui.panels.export_renpy import RenPyExportPanel
from comfyvn.gui.panels.import_manager_panel import ImportManagerPanel
from comfyvn.gui.panels.imports_panel import ImportsPanel
from comfyvn.gui.panels.notify_overlay import NotifyOverlay
from comfyvn.gui.panels.player_persona_panel import PlayerPersonaPanel
from comfyvn.gui.panels.playground_panel import PlaygroundPanel
from comfyvn.gui.panels.scenes_panel import ScenesPanel
from comfyvn.gui.panels.settings_panel import SettingsPanel
from comfyvn.gui.panels.sprite_panel import SpritePanel

# Panels (lazy-instantiated)
from comfyvn.gui.panels.studio_center import StudioCenter
from comfyvn.gui.panels.telemetry_panel import TelemetryPanel
from comfyvn.gui.panels.timeline_panel import TimelinePanel
from comfyvn.gui.panels.tools_installer import ToolsInstallerPanel

# Services
from comfyvn.gui.server_boot import start_detached_server
from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.gui.statusbar_metrics import StatusBarMetrics
from comfyvn.gui.widgets.log_hub import LogHub
from comfyvn.gui.windows.settings_window import SettingsWindow
from comfyvn.studio.core import CharacterRegistry, SceneRegistry, TimelineRegistry

from .quick_access_toolbar import QuickAccessToolbarMixin

# Core studio shell & mixins
from .shell_studio import ShellStudio

logger = logging.getLogger(__name__)


class MainWindow(ShellStudio, QuickAccessToolbarMixin):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyVN Studio")
        self.resize(1280, 800)
        accessibility_manager.ensure_applied()

        # Services & controllers
        self.bridge = ServerBridge()
        if hasattr(self.bridge, "status_updated"):
            try:
                self.bridge.status_updated.connect(self._handle_bridge_status)
            except AttributeError:
                logger.debug("ServerBridge stub missing status_updated signal")
        self.dockman = DockManager(self)
        self._tools_import_menu_action = None
        workspace_store = runtime_paths.workspace_dir()
        self.workspace = WorkspaceController(self, workspace_store)
        self._recent_projects = load_recent()
        self._current_project_path: Path | None = None
        self._scene_registry = SceneRegistry()
        self._character_registry = CharacterRegistry()
        self._timeline_registry = TimelineRegistry()
        self._extension_metadata: list[ExtensionMetadata] = []

        # Central canvas — view-state router for viewer & designer
        self.central_router = CenterRouter(
            bridge=self.bridge,
            character_registry=self._character_registry,
            open_assets=self.open_asset_browser,
            open_timeline=self.open_timeline,
            open_logs=self.open_log_hub,
            parent=self,
        )
        self.setCentralWidget(self.central_router)
        self.central_viewer = self.central_router.viewer_widget()
        self.character_designer = self.central_router.designer_widget()
        self.central_router.set_project_context(None)

        # Status bar (bottom, best practice) with server + script status
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status_label = QLabel("🔴 Server: Unknown")
        self._status.addPermanentWidget(self._status_label, 1)
        self._reconnect_button = QPushButton("Reconnect now")
        self._reconnect_button.setVisible(False)
        self._reconnect_button.clicked.connect(self._manual_reconnect)
        self._status.addPermanentWidget(self._reconnect_button, 0)
        self._metrics_display = StatusBarMetrics(self.bridge.base_url, parent=self)
        self._status.addPermanentWidget(self._metrics_display.widget, 1)
        self._script_status_label = QLabel("🟢 Scripts: Idle")
        self._script_status_label.setToolTip("Latest script execution status.")
        self._status.addPermanentWidget(self._script_status_label, 1)
        self._set_script_status(True, "No scripts executed yet.")
        self._metrics_display.start()
        self._status.showMessage(
            "Start the VN viewer to preview scenes. Tools → Import to ingest assets."
        )

        self._notify_overlay = NotifyOverlay(self)
        self._notify_overlay.attach(self)
        self._warning_log: list[dict[str, Any]] = []
        self._extension_messages_seen: set[str] = set()
        notifier.attach(self._on_notifier_event)

        self._menus_built = False

        # Toolbars (Quick Access) are dynamic via shortcut registry
        self._rebuild_shortcuts_toolbar()
        self._restore_layout()

        # Menus are dynamic via extension folder
        ensure_menu_bar(self)
        self.reload_menus()

        # Background server: start if not reachable
        self.bridge.start_polling()
        self._update_server_status({"ok": False, "state": "waiting"})
        QTimer.singleShot(400, self._ensure_server_online)
        # Periodic server heartbeat to status bar
        self._heartbeat = QTimer(self)
        self._heartbeat.timeout.connect(self._poll_server_status)
        self._heartbeat.start(2500)
        if hasattr(self.bridge, "warnings_updated"):
            try:
                self.bridge.warnings_updated.connect(self._handle_backend_warnings)
            except AttributeError:
                logger.debug("ServerBridge stub missing warnings_updated signal")

    # --------------------
    # Dynamic systems
    # --------------------
    def reload_menus(self):
        """Reload menus from the on-disk extensions folder -> menu registry -> menubar."""
        if getattr(self, "_reloading_menus", False):
            logger.debug("Menu reload already in progress; ignoring duplicate trigger")
            return
        self._reloading_menus = True
        try:
            menu_registry.clear()
            register_core_menu_items(menu_registry)
            base_folder = Path("extensions")
            self._extension_metadata = load_extension_metadata(base_folder)
            active_metadata = [
                meta for meta in self._extension_metadata if meta.compatible
            ]
            reload_from_extensions(
                menu_registry,
                base_folder=base_folder,
                clear=False,
                metadata=active_metadata,
            )
            for meta in self._extension_metadata:
                for warning in meta.warnings:
                    logger.warning("Extension %s: %s", meta.id, warning)
                    key = f"{meta.id}:{warning}"
                    if key not in self._extension_messages_seen:
                        self._extension_messages_seen.add(key)
                        notifier.toast("warn", f"Extension {meta.name}: {warning}")
                for error in meta.errors:
                    logger.error("Extension %s: %s", meta.id, error)
                    key = f"{meta.id}:{error}"
                    if key not in self._extension_messages_seen:
                        self._extension_messages_seen.add(key)
                        notifier.toast("error", f"Extension {meta.name}: {error}")
        except Exception as e:
            print("[Menu] reload error:", e)
            logger.exception("Menu reload failed: %s", e)
        finally:
            try:
                menubar = self.menuBar()
                rebuild_menus_from_registry(self, menu_registry)
                self._inject_import_submenu()
                self._populate_extensions_menu()
                self._menus_built = True
                logger.debug("Menus rebuilt with %d items", len(menu_registry.items))
            finally:
                self._reloading_menus = False

    def _rebuild_shortcuts_toolbar(self):
        """Rebuild Quick Access toolbar from shortcuts folder."""
        try:
            load_shortcuts_from_folder(shortcut_registry, Path("shortcuts"))
        except Exception as e:
            print("[Shortcuts] load error:", e)
        # QuickAccessToolbarMixin expects items on self via registry
        self.build_quick_access_toolbar(shortcut_registry.iter_actions())

    def _inject_import_submenu(self) -> None:
        menubar = self.menuBar()
        if menubar is None:
            return
        tools_menu = None
        for action in menubar.actions():
            if not isValid(action):
                continue
            if action.text().replace("&", "") == "Tools":
                tools_menu = action.menu()
                break
        if tools_menu is not None and not isValid(tools_menu):
            tools_menu = None
        if tools_menu is None or not isValid(tools_menu):
            return
        previous_action = getattr(self, "_tools_import_menu_action", None)
        if previous_action is not None and isValid(previous_action):
            try:
                tools_menu.removeAction(previous_action)
            except RuntimeError:
                logger.debug("Previous import menu action already removed by Qt")
            self._tools_import_menu_action = None

        import_menu = QMenu("Import", tools_menu)
        import_menu.setObjectName("tools_import_submenu")

        from_file_action = import_menu.addAction("From File…")
        from_file_action.triggered.connect(self.import_from_file)
        import_menu.addSeparator()
        import_menu.addAction("SillyTavern Chat…", self.open_import_sillytavern_chat)
        import_menu.addAction("Persona JSON…", self.open_import_persona)
        import_menu.addAction("Lore JSON…", self.open_import_lore)
        import_menu.addAction("FurAffinity Export…", self.open_import_furaffinity)
        import_menu.addAction("Roleplay Transcript…", self.open_import_roleplay)

        actions = tools_menu.actions()
        insert_index = None
        for idx, action in enumerate(actions):
            if not isValid(action):
                continue
            if str(action.property("_sourceLabel") or "") == "Import Assets":
                insert_index = idx + 1
                break
        if insert_index is not None and insert_index < len(actions):
            before_action = actions[insert_index]
            if before_action is None or not isValid(before_action):
                tools_menu.addMenu(import_menu)
            else:
                try:
                    tools_menu.insertMenu(before_action, import_menu)
                except RuntimeError:
                    logger.debug(
                        "Tools menu insertMenu failed; falling back to addMenu",
                        exc_info=True,
                    )
                    tools_menu.addMenu(import_menu)
        else:
            tools_menu.addMenu(import_menu)
        self._tools_import_menu_action = import_menu.menuAction()
        self._tools_import_menu = import_menu

    def import_from_file(self) -> None:
        caption = "Select Import Payload"
        filters = (
            "Bundle Files (*.json *.jsonl *.zip *.stbundle *.txt);;"
            "JSON Files (*.json *.jsonl);;"
            "Archive Files (*.zip *.stbundle);;"
            "All Files (*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self, caption, str(Path.home()), filters
        )
        if not file_path:
            return

        path = Path(file_path)
        focus_action: str | None = None
        try:
            if path.suffix.lower() in {".zip", ".stbundle"}:
                self._import_vnpack_bundle(path)
            else:
                focus_action = self._import_json_payload(path)
        except RuntimeError as exc:
            notifier.toast("warn", str(exc))
            return
        except Exception as exc:  # pragma: no cover - GUI safeguard
            notifier.toast("error", f"Import failed: {exc}")
            logger.exception("Import from file failed: %s", exc)
            return

        notifier.toast("success", f"Queued import for {path.name}")
        if focus_action:
            self.open_import_manager(focus_action)
        self.open_imports_panel()

    def _import_json_payload(self, path: Path) -> str | None:
        with path.open("r", encoding="utf-8") as handle:
            try:
                data = json.load(handle)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSON payload: {exc}") from exc

        route = "/st/import"
        payload: dict[str, Any]
        focus_action: str | None = None

        if isinstance(data, dict):
            if {"type", "data"} <= data.keys():
                payload = {"type": data["type"], "data": data["data"]}
            elif "personas" in data:
                payload = {"type": "personas", "data": data["personas"]}
            elif "worlds" in data:
                payload = {"type": "worlds", "data": data["worlds"]}
            elif "chats" in data:
                payload = {"type": "chats", "data": data["chats"]}
            elif "entries" in data:
                route = "/api/imports/roleplay"
                payload = {"entries": data["entries"]}
                focus_action = "Import Roleplay Archive"
            elif "collection" in data:
                route = "/api/imports/furaffinity"
                payload = {"collection": data["collection"]}
                focus_action = "Import FurAffinity Gallery"
            else:
                raise RuntimeError(
                    "Unsupported JSON payload shape – add type/data keys."
                )
        elif isinstance(data, list):
            route, payload, focus_action = self._prompt_list_import(data)
        else:
            raise RuntimeError("Unsupported JSON payload structure.")

        if route == "/st/import":
            payload_type = str(payload.get("type", "")).lower()
            focus_action = {
                "personas": "Import Persona Bundle",
                "worlds": "Import Lore Library",
                "chats": "Import Chat Transcript",
            }.get(payload_type, focus_action)

        response = self.bridge.post_json(route, payload, timeout=15.0)
        if not isinstance(response, dict) or not response.get("ok"):
            detail = ""
            if isinstance(response, dict):
                detail = str(response.get("data") or response.get("error") or "")
            raise RuntimeError(f"Server rejected payload. {detail}".strip())
        return focus_action

    def _prompt_list_import(
        self, data: list[Any]
    ) -> tuple[str, dict[str, Any], str | None]:
        options = [
            ("Persona JSON", "/st/import", "personas", "Import Persona Bundle"),
            ("Lore JSON", "/st/import", "worlds", "Import Lore Library"),
            (
                "SillyTavern Chat Transcript",
                "/st/import",
                "chats",
                "Import Chat Transcript",
            ),
            (
                "Roleplay Transcript",
                "/api/imports/roleplay",
                None,
                "Import Roleplay Archive",
            ),
        ]
        labels = [label for label, *_ in options]
        choice, ok = QInputDialog.getItem(
            self,
            "Select Import Type",
            "Detected JSON array. Choose how to import these records:",
            labels,
            0,
            False,
        )
        if not ok:
            raise RuntimeError("Import cancelled.")
        for label, route, import_type, focus_action in options:
            if label == choice:
                if import_type:
                    return route, {"type": import_type, "data": data}, focus_action
                return route, {"entries": data}, focus_action
        raise RuntimeError("Unsupported import selection.")

    def _import_vnpack_bundle(self, path: Path) -> None:
        base_url = self._resolve_base_url().rstrip("/")
        url = f"{base_url}/import/vnpack/extract"
        with path.open("rb") as handle:
            response = requests.post(
                url,
                files={"file": (path.name, handle)},
                timeout=60,
            )
        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:  # pragma: no cover - text fallback
                detail = response.text
            raise RuntimeError(
                f"VN pack import failed ({response.status_code}): {detail}"
            )

    # --------------------
    # Panel openers (lazy)
    # --------------------
    def open_studio_center(self):
        dock = getattr(self, "_studio_center_dock", None)
        if dock is None:
            panel = StudioCenter(self.bridge, self)
            dock = self.dockman.dock(panel, "Studio Center")
            self._studio_center_dock = dock
            logger.debug("Studio Center module created")
        dock.setVisible(True)
        dock.raise_()

    def open_asset_browser(self):
        dock = getattr(self, "_asset_browser", None)
        if dock is None:
            dock = AssetBrowser(str(runtime_paths.data_dir("assets")))
            self.dockman.dock(dock, "Assets")
            self._asset_browser = dock
            logger.debug("Asset Browser module created")
        dock.setVisible(True)
        dock.raise_()

    def open_scenes_panel(self):
        dock = getattr(self, "_scenes_panel", None)
        if dock is None:
            panel = ScenesPanel(self._scene_registry, self)
            dock = self.dockman.dock(panel, "Scenes")
            self._scenes_panel = dock
            logger.debug("Scenes panel created")
        dock.setVisible(True)
        dock.raise_()
        widget = dock.widget()
        if isinstance(widget, ScenesPanel):
            widget.set_registry(self._scene_registry)

    def open_characters_panel(self):
        dock = getattr(self, "_characters_panel", None)
        if dock is None:
            panel = CharactersPanel(self._character_registry, self)
            dock = self.dockman.dock(panel, "Characters")
            self._characters_panel = dock
            logger.debug("Characters panel created")
        dock.setVisible(True)
        dock.raise_()
        widget = dock.widget()
        if isinstance(widget, CharactersPanel):
            widget.set_registry(self._character_registry)

    def open_character_designer(self):
        if hasattr(self, "central_router"):
            self.central_router.activate("Character Designer")
        if hasattr(self, "character_designer"):
            self.character_designer.refresh()

    def open_player_persona_panel(self):
        dock = getattr(self, "_player_persona_panel", None)
        if dock is None:
            dock = PlayerPersonaPanel(
                self.bridge,
                self,
                open_sprite_manager=self.open_sprite_panel,
                open_asset_manager=self.open_asset_browser,
                open_playground=self.open_playground,
            )
            self.dockman.dock(dock, "Player Persona")
            self._player_persona_panel = dock
            logger.debug("Player persona panel created")
        dock.setVisible(True)
        dock.raise_()

    def open_imports_panel(self):
        dock = getattr(self, "_imports_panel", None)
        if dock is None:
            panel = ImportsPanel(self.bridge.base)
            dock = self.dockman.dock(panel, "Imports", area=Qt.BottomDockWidgetArea)
            self._imports_panel = dock
            logger.debug("Imports panel created")
        dock.setVisible(True)
        dock.raise_()

    def open_audio_panel(self):
        dock = getattr(self, "_audio_panel", None)
        if dock is None:
            panel = AudioPanel(self.bridge.base)
            dock = self.dockman.dock(panel, "Audio", area=Qt.BottomDockWidgetArea)
            self._audio_panel = dock
            logger.debug("Audio panel created")
        dock.setVisible(True)
        dock.raise_()

    def open_advisory_panel(self):
        dock = getattr(self, "_advisory_panel", None)
        if dock is None:
            panel = AdvisoryPanel(self.bridge.base)
            dock = self.dockman.dock(panel, "Advisory")
            self._advisory_panel = dock
            logger.debug("Advisory panel created")
        dock.setVisible(True)
        dock.raise_()

    def open_playground(self):
        dock = getattr(self, "_playground", None)
        if dock is None:
            dock = PlaygroundPanel(self.bridge)
            self.dockman.dock(dock, "Playground")
            self._playground = dock
            logger.debug("Playground module created")
        dock.setVisible(True)
        dock.raise_()

    def open_vn_chat_panel(self):
        dock = getattr(self, "_vn_chat_panel", None)
        if dock is None:
            panel = VNChatPanel(self.bridge, self)
            dock = self.dockman.dock(panel, "VN Chat")
            self._vn_chat_panel = dock
            logger.debug("VN chat panel created")
        dock.setVisible(True)
        dock.raise_()

    def open_sprite_panel(self):
        dock = getattr(self, "_sprite_panel", None)
        if dock is None:
            dock = SpritePanel(self)
            self.dockman.dock(dock, "Sprites")
            self._sprite_panel = dock
            logger.debug("Sprite panel created")
        dock.setVisible(True)
        dock.raise_()

    def open_timeline(self):
        dock = getattr(self, "_timeline", None)
        if dock is None:
            dock = TimelinePanel(self._scene_registry, self._timeline_registry, self)
            self.dockman.dock(dock, "Timeline")
            self._timeline = dock
            logger.debug("Timeline module created")
        elif isinstance(dock, TimelinePanel):
            dock.set_registries(
                scene_registry=self._scene_registry,
                timeline_registry=self._timeline_registry,
            )
        dock.setVisible(True)
        dock.raise_()

    def open_diffmerge_graph(self):
        dock = getattr(self, "_diffmerge_graph", None)
        if dock is None:
            panel = DiffmergeGraphPanel(self.bridge.base_url, self)
            dock = self.dockman.dock(panel, "Worldline Graph")
            self._diffmerge_graph = dock
            logger.debug("DiffMerge Graph panel created")
        else:
            widget = dock.widget()
            if isinstance(widget, DiffmergeGraphPanel):
                widget._load_worlds()
        dock.setVisible(True)
        dock.raise_()

    def open_telemetry(self):
        dock = getattr(self, "_telemetry_dock", None)
        if dock is None:
            panel = TelemetryPanel(self.bridge.base)
            dock = self.dockman.dock(panel, "System Status")
            self._telemetry_dock = dock
            logger.debug("Telemetry module created")
        dock.setVisible(True)
        dock.raise_()

    def open_log_hub(self):
        dock = getattr(self, "_loghub_dock", None)
        if dock is None:
            panel = LogHub()
            dock = self.dockman.dock(panel, "Log Hub")
            self._loghub_dock = dock
            logger.debug("Log Hub module created")
        dock.setVisible(True)
        dock.raise_()

    def open_debug_integrations(self):
        dock = getattr(self, "_debug_integrations", None)
        if dock is None:
            panel = DebugIntegrationsPanel(self.bridge.base)
            dock = self.dockman.dock(panel, "Debug Integrations")
            self._debug_integrations = dock
            logger.debug("Debug Integrations panel created")
        dock.setVisible(True)
        dock.raise_()
        widget = dock.widget()
        if isinstance(widget, DebugIntegrationsPanel):
            widget.refresh()

    def open_settings_panel(self):
        dock = getattr(self, "_settings_panel", None)
        if dock is None:
            dock = SettingsPanel(self.bridge)
            self.dockman.dock(dock, "Settings")
            self._settings_panel = dock
            logger.debug("Settings module created")
        dock.setVisible(True)
        dock.raise_()

    def _restore_layout(self) -> None:
        settings = QSettings("ComfyVN", "StudioWindow")
        geometry = settings.value("geometry")
        state = settings.value("windowState")
        if geometry:
            self.restoreGeometry(geometry)
        if state:
            self.restoreState(state)

    def closeEvent(self, event):  # type: ignore[override]
        settings = QSettings("ComfyVN", "StudioWindow")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        if hasattr(self, "_metrics_display"):
            self._metrics_display.stop()
        super().closeEvent(event)

    # --------------------
    # Utility helpers
    # --------------------
    def _resolve_base_url(self) -> str:
        authority = current_authority(refresh=True)
        return authority.base_url

    def launch_detached_server(self):
        authority = current_authority(refresh=True)
        start_detached_server(authority.host, authority.port)
        self._status.showMessage(
            f"Launching detached server on {authority.host}:{authority.port}", 5000
        )

    def open_projects_folder(self):
        self._open_folder(Path("data/projects"))

    def open_data_folder(self):
        self._open_folder(Path("data"))

    def open_logs_folder(self):
        self._open_folder(runtime_paths.logs_dir())

    def open_extensions_folder(self):
        self._open_folder(Path("extensions"))

    def _open_folder(self, folder: Path):
        path = Path(folder).resolve()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_import_manager(self, action_label: str | None = None):
        dock = getattr(self, "_import_manager_dock", None)
        if dock is None:
            panel = ImportManagerPanel(self._resolve_base_url(), parent=self)
            dock = self.dockman.dock(panel, "Import Manager")
            self._import_manager_dock = dock
            logger.debug("Import Manager panel created")
        dock.setVisible(True)
        dock.raise_()
        widget = dock.widget()
        if isinstance(widget, ImportManagerPanel) and action_label:
            widget.select_action(action_label)

    def open_import_sillytavern_chat(self):
        self.open_import_manager("Import Chat Transcript")

    def open_import_persona(self):
        self.open_import_manager("Import Persona Bundle")

    def open_import_lore(self):
        self.open_import_manager("Import Lore Library")

    def open_import_furaffinity(self):
        self.open_import_manager("Import FurAffinity Gallery")

    def open_import_roleplay(self):
        self.open_import_manager("Import Roleplay Archive")

    def open_renpy_exporter(self):
        dock = getattr(self, "_renpy_exporter_dock", None)
        if dock is None:
            panel = RenPyExportPanel(self._resolve_base_url(), parent=self)
            dock = self.dockman.dock(panel, "Ren'Py Exporter")
            self._renpy_exporter_dock = dock
            logger.debug("Ren'Py exporter panel created")
        dock.setVisible(True)
        dock.raise_()

    def open_tools_installer(self):
        dock = getattr(self, "_tools_installer_dock", None)
        if dock is None:
            panel = ToolsInstallerPanel(self._resolve_base_url(), parent=self)
            dock = self.dockman.dock(panel, "Tools Installer")
            self._tools_installer_dock = dock
            logger.debug("Tools Installer panel created")
        dock.setVisible(True)
        dock.raise_()

    def open_settings_window(self):
        window = getattr(self, "_settings_window", None)
        if window is None:
            window = SettingsWindow(self.bridge, parent=self)
            self._settings_window = window
            window.finished.connect(self._clear_settings_window)
        window.show()
        window.raise_()
        window.activateWindow()

    def _clear_settings_window(self):
        self._settings_window = None

    # --------------------
    # Project workflows
    # --------------------
    def new_project(self):
        print("[Studio] TODO: new_project()")

    def close_project(self) -> None:
        if not self._current_project_path:
            logger.info("No project currently open")
            return
        logger.info("Closing project %s", self._current_project_path)
        self._current_project_path = None
        self._initialize_registries("default")
        if hasattr(self, "central_router"):
            self.central_router.set_project_context(None)
        if hasattr(self, "central_viewer"):
            self.central_viewer.stop_viewer()
            self.central_viewer.show_message(
                "Project closed. Use File → New or Recent to open another project."
            )

    def open_recent_projects(self) -> None:
        logger.info("Opening recent project list")
        if not self._recent_projects:
            QMessageBox.information(
                self, "Recent Projects", "No recent projects recorded yet."
            )
            return
        project_dir = QFileDialog.getExistingDirectory(
            self, "Open Recent Project", self._recent_projects[0]
        )
        if project_dir:
            self._open_project(Path(project_dir))

    def _open_project(self, project_path: Path) -> None:
        project_path = project_path.resolve()
        if not project_path.exists():
            QMessageBox.warning(
                self, "Open Project", "Selected project path does not exist."
            )
            return
        project_id = project_path.name
        logger.info("Opening project %s at %s", project_id, project_path)
        self._current_project_path = project_path
        self._initialize_registries(project_id)

        scenes_dir = project_path / "scenes"
        if scenes_dir.exists():
            for payload_file in scenes_dir.glob("*.json"):
                try:
                    payload = payload_file.read_text(encoding="utf-8")
                    self._scene_registry.upsert_scene(payload_file.stem, payload, {})
                except Exception as exc:
                    logger.warning("Failed to load scene %s: %s", payload_file, exc)

        touch_recent(str(project_path))
        self._recent_projects = load_recent()
        if hasattr(self, "central_router"):
            self.central_router.set_project_context(project_path, project_id=project_id)
        if hasattr(self, "central_viewer"):
            self.central_viewer.show_message(f"Opened project: {project_id}")
        self._refresh_project_panels()

    def _initialize_registries(self, project_id: str) -> None:
        logger.info("Initializing registries for project %s", project_id)
        self._scene_registry = SceneRegistry(project_id=project_id)
        self._character_registry = CharacterRegistry(project_id=project_id)
        self._timeline_registry = TimelineRegistry(project_id=project_id)
        self._refresh_project_panels()

    def _refresh_project_panels(self) -> None:
        dock = getattr(self, "_scenes_panel", None)
        if dock is not None and isinstance(dock.widget(), ScenesPanel):
            dock.widget().set_registry(self._scene_registry)
        dock = getattr(self, "_characters_panel", None)
        if dock is not None and isinstance(dock.widget(), CharactersPanel):
            dock.widget().set_registry(self._character_registry)
        dock = getattr(self, "_timeline", None)
        if dock is not None and isinstance(dock, TimelinePanel):
            dock.set_registries(
                scene_registry=self._scene_registry,
                timeline_registry=self._timeline_registry,
            )

    # --------------------
    # Server monitoring
    # --------------------
    def _ensure_server_online(self):
        ok = self.bridge.ensure_online(autostart=True)
        if not ok:
            logger.warning(
                "Server auto-start attempted but did not report healthy status."
            )

    def _handle_bridge_status(self, payload: dict) -> None:
        self._update_server_status(payload)

    def _manual_reconnect(self) -> None:
        logger.info("Manual reconnect triggered from status bar")
        self.bridge.reconnect()
        self._update_server_status({"ok": False, "state": "waiting", "retry_in": 0.0})

    def manual_reconnect(self) -> None:
        self._manual_reconnect()

    def _poll_server_status(self):
        self._update_server_status()

    def _update_server_status(self, payload: dict | None = None) -> None:
        data = payload if isinstance(payload, dict) else self.bridge.latest()
        self._metrics_display.update_payload(data if isinstance(data, dict) else None)
        show_reconnect = True
        if isinstance(data, dict):
            show_reconnect = self._has_reconnect_action(data.get("actions"))
        if not isinstance(data, dict) or not data:
            self._status_label.setText("🟡 Server: Waiting for server…")
            self._reconnect_button.setVisible(show_reconnect)
            return

        state = str(data.get("state") or "")
        retry = data.get("retry_in")
        error = data.get("error")

        is_online = state == "online" and bool(data.get("ok"))
        if is_online:
            self._status_label.setText("🟢 Server: Online")
            self._reconnect_button.setVisible(False)
            return

        if isinstance(error, str) and error:
            logger.debug("Bridge error reported: %s", error)

        if isinstance(retry, (int, float)) and retry > 0.05:
            self._status_label.setText(
                f"🟡 Server: Waiting for server… retry in {retry:.0f}s"
            )
        else:
            self._status_label.setText("🟡 Server: Waiting for server…")
        self._reconnect_button.setVisible(show_reconnect)

    def _set_script_status(self, ok: bool, message: str) -> None:
        icon = "🟢" if ok else "🔴"
        label = "Scripts: Ready" if ok else "Scripts: Error"
        self._script_status_label.setText(f"{icon} {label}")
        self._script_status_label.setToolTip(message)
        if ok:
            logger.info("Script sequence completed: %s", message)
        else:
            logger.warning("Script sequence failed: %s", message)

    @staticmethod
    def _has_reconnect_action(actions: object) -> bool:
        if isinstance(actions, (list, tuple)):
            for action in actions:
                if isinstance(action, dict) and action.get("command") == "reconnect":
                    return True
        return False

    # --------------------
    # Notifications
    # --------------------
    def _on_notifier_event(self, event: dict) -> None:
        msg = str(event.get("msg") or "")
        level = str(event.get("level") or "info")
        if not msg:
            return
        icon = {
            "error": "❗",
            "warn": "⚠",
            "warning": "⚠",
            "success": "✅",
            "info": "ℹ️",
        }.get(level.lower(), "ℹ️")
        if hasattr(self, "_notify_overlay") and self._notify_overlay:
            self._notify_overlay.toast(f"{icon} {msg}", level=level)

    def _handle_backend_warnings(self, warnings: list[dict]) -> None:
        for payload in warnings:
            message = str(
                payload.get("message") or payload.get("detail") or "Backend warning"
            )
            level = str(payload.get("level") or "warning")
            meta = {
                "source": payload.get("source"),
                "details": payload.get("details"),
                "timestamp": payload.get("timestamp"),
                "id": payload.get("id"),
            }
            self._warning_log.append(meta)
            self._warning_log = self._warning_log[-100:]
            notifier.toast(level, message, meta={"warning": meta})

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "_notify_overlay") and self._notify_overlay:
            self._notify_overlay._reposition()

    def moveEvent(self, event):  # type: ignore[override]
        super().moveEvent(event)
        if hasattr(self, "_notify_overlay") and self._notify_overlay:
            self._notify_overlay._reposition()

    def _populate_extensions_menu(self) -> None:
        menubar = self.menuBar()
        target_menu = None
        for action in menubar.actions():
            menu = action.menu()
            if menu and action.text().replace("&", "") == "Extensions":
                target_menu = menu
                break
        if not target_menu:
            return

        # Remove previously injected entries
        for act in list(target_menu.actions()):
            if act.property("extensionEntry"):
                target_menu.removeAction(act)

        if not self._extension_metadata:
            return

        official = sorted(
            (m for m in self._extension_metadata if m.official),
            key=lambda m: m.name.lower(),
        )
        community = sorted(
            (m for m in self._extension_metadata if not m.official),
            key=lambda m: m.name.lower(),
        )

        def add_group(title: str, items: list[ExtensionMetadata]) -> None:
            if not items:
                return
            target_menu.addSeparator()
            header = QAction(title, self)
            header.setEnabled(False)
            header.setProperty("extensionEntry", True)
            target_menu.addAction(header)
            for meta in items:
                label_text = meta.name if meta.compatible else f"⚠ {meta.name}"
                action = QAction(label_text, self)
                action.setProperty("extensionEntry", True)
                tooltip_parts = []
                if meta.description:
                    tooltip_parts.append(meta.description)
                tooltip_parts.append(str(meta.path))
                if meta.errors:
                    tooltip_parts.append("Errors: " + "; ".join(meta.errors))
                elif meta.warnings:
                    tooltip_parts.append("Warnings: " + "; ".join(meta.warnings))
                action.setToolTip("\n".join(tooltip_parts))
                action.triggered.connect(
                    lambda _, info=meta: self._show_extension_info(info)
                )
                if not meta.compatible:
                    action.setEnabled(False)
                target_menu.addAction(action)

        add_group("Official Extensions", official)
        add_group("Imported Extensions", community)

    def _show_extension_info(self, meta: ExtensionMetadata) -> None:
        lines = [
            f"ID: {meta.id}",
            f"Version: {meta.version or 'n/a'}",
            f"Origin: {'Official' if meta.official else 'Imported'}",
            f"Location: {meta.path}",
        ]
        if meta.author:
            lines.append(f"Author: {meta.author}")
        if meta.homepage:
            lines.append(f"Homepage: {meta.homepage}")
        if meta.description:
            lines.append("")
            lines.append(meta.description)
        if meta.required_spec:
            lines.append(f"Requires: {meta.required_spec}")
        if meta.api_version:
            lines.append(f"Studio API: {meta.api_version}")
        if meta.errors:
            lines.append("")
            lines.append("Compatibility Issues:")
            for err in meta.errors:
                lines.append(f"  • {err}")
        elif meta.warnings:
            lines.append("")
            lines.append("Warnings:")
            for warn in meta.warnings:
                lines.append(f"  • {warn}")
        if meta.hooks:
            lines.append("")
            lines.append("Menu Hooks:")
            for hook in meta.hooks:
                label = hook.get("label") or "Unnamed action"
                menu = hook.get("menu") or "Extensions"
                lines.append(f"  • {label} (menu: {menu})")

        msg = QMessageBox(self)
        msg.setWindowTitle(meta.name)
        msg.setText("\n".join(lines))
        open_btn = msg.addButton("Open Folder", QMessageBox.ActionRole)
        msg.addButton(QMessageBox.Ok)
        msg.exec()
        if msg.clickedButton() == open_btn:
            target = meta.path if meta.path.is_dir() else meta.path.parent
            self._open_folder(target)

    # --------------------
    # Setup utilities
    # --------------------
    def install_base_scripts(self):
        script_path = Path("setup/install_defaults.py").resolve()
        if not script_path.exists():
            QMessageBox.warning(self, "Install Base Scripts", "Setup script not found.")
            self._set_script_status(False, "Install defaults: setup script missing.")
            return

        confirm = QMessageBox.question(
            self,
            "Install Base Scripts",
            "Install default assets and configuration stubs?\n"
            "Existing files remain untouched unless you rerun with --force.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                cwd=Path(__file__).resolve().parents[3],
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Install Base Scripts", f"Failed to launch installer:\n{exc}"
            )
            self._set_script_status(False, f"Installer launch failed: {exc}")
            return

        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        output = output.strip() or "No output."

        if proc.returncode == 0:
            QMessageBox.information(
                self,
                "Install Base Scripts",
                "Defaults installed successfully.\n\n" + output,
            )
            self._set_script_status(True, "Install defaults completed successfully.")
        else:
            QMessageBox.critical(
                self,
                "Install Base Scripts",
                f"Installer exited with code {proc.returncode}.\n\n{output}",
            )
            self._set_script_status(
                False, f"Installer exited with code {proc.returncode}."
            )


def main():
    app = QApplication(sys.argv)
    try:
        apply_theme(app, "default_dark")
    except Exception:
        pass
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

    def new_project(self):
        logger.info("New project workflow started")
        project_dir = QFileDialog.getExistingDirectory(
            self, "Select Project Directory", str(Path.cwd())
        )
        if not project_dir:
            logger.info("New project cancelled by user")
            return
        project_path = Path(project_dir).resolve()
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / "scenes").mkdir(exist_ok=True)
        (project_path / "characters").mkdir(exist_ok=True)
        metadata = project_path / "project.json"
        if not metadata.exists():
            metadata.write_text('{"name": "New Project"}', encoding="utf-8")
        logger.info("Project directory prepared at %s", project_path)
        self._open_project(project_path)

    def close_project(self):
        if not self._current_project_path:
            logger.info("No project currently open")
            return
        logger.info("Closing project %s", self._current_project_path)
        self._current_project_path = None
        if hasattr(self, "central_router"):
            self.central_router.set_project_context(None)
        if hasattr(self, "central_viewer"):
            self.central_viewer.stop_viewer()
            self.central_viewer.show_message(
                "Project closed. Use File → New or Recent to open another project."
            )

    def open_recent_projects(self):
        logger.info("Opening recent project list")
        if not self._recent_projects:
            QMessageBox.information(
                self, "Recent Projects", "No recent projects recorded yet."
            )
            return
        project_dir = QFileDialog.getExistingDirectory(
            self, "Open Recent Project", self._recent_projects[0]
        )
        if project_dir:
            self._open_project(Path(project_dir))

    def _open_project(self, project_path: Path) -> None:
        project_path = project_path.resolve()
        if not project_path.exists():
            QMessageBox.warning(
                self, "Open Project", "Selected project path does not exist."
            )
            return
        logger.info("Opening project at %s", project_path)

        scenes_dir = project_path / "scenes"
        if scenes_dir.exists():
            for payload_file in scenes_dir.glob("*.json"):
                try:
                    payload = payload_file.read_text(encoding="utf-8")
                    self._scene_registry.upsert_scene(payload_file.stem, payload, {})
                except Exception as exc:
                    logger.warning("Failed to load scene %s: %s", payload_file, exc)

        touch_recent(str(project_path))
        self._recent_projects = load_recent()
        self._current_project_path = project_path
        if hasattr(self, "central_router"):
            self.central_router.set_project_context(
                project_path, project_id=project_path.name
            )
        if hasattr(self, "central_viewer"):
            self.central_viewer.show_message(f"Opened project: {project_path}")
