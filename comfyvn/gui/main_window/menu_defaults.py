"""Default menu registrations for the ComfyVN main window."""

from __future__ import annotations

from comfyvn.core.menu_runtime_bridge import MenuRegistry


def register_core_menu_items(registry: MenuRegistry) -> None:
    """Populate the registry with built-in menu entries."""
    # File menu
    registry.add("Open Projects Folder", "open_projects_folder", section="File", order=10)
    registry.add("Open Data Folder", "open_data_folder", section="File", order=20)
    registry.add("Open Logs Folder", "open_logs_folder", section="File", order=30)
    registry.add("Exit", "close", section="File", separator_before=True, order=100)

    # View-centric entries reflect the primary dock panels.
    registry.add("Studio Center", "open_studio_center", section="View", order=10)
    registry.add("Assets", "open_asset_browser", section="View", order=20)
    registry.add("Playground", "open_playground", section="View", order=30)
    registry.add("Timeline", "open_timeline", section="View", order=40)
    registry.add("System Status", "open_telemetry", section="View", separator_before=True, order=50)
    registry.add("Log Hub", "open_log_hub", section="View", order=60)

    # Tools and Extensions utility entries.
    registry.add("Reload Menus", "reload_menus", section="Tools", order=5)
    registry.add("Launch Detached Server", "launch_detached_server", section="Tools", order=10)
    registry.add("Install Base Scripts", "install_base_scripts", section="Tools", separator_before=True, order=100)

    registry.add("Reload Extensions", "reload_menus", section="Extensions", order=5)
    registry.add("Open Extensions Folder", "open_extensions_folder", section="Extensions", order=10)
    registry.add("Settings Panel", "open_settings_panel", section="Settings", order=10)
