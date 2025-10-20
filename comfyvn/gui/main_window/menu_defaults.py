"""Default menu registrations for the ComfyVN main window."""

from __future__ import annotations

from comfyvn.core.menu_runtime_bridge import MenuRegistry


def register_core_menu_items(registry: MenuRegistry) -> None:
    """Populate the registry with built-in menu entries."""
    # View-centric entries reflect the original hard-coded menu layout.
    registry.add("Studio Center", "open_studio_center", section="View", order=10)
    registry.add("Assets", "open_asset_browser", section="View", order=20)
    registry.add("Playground", "open_playground", section="View", order=30)
    registry.add("Timeline", "open_timeline", section="View", order=40)
    registry.add("System Status", "open_telemetry", section="View", separator_before=True, order=50)
    registry.add("Log Hub", "open_log_hub", section="View", order=60)

    # Tools section can surface server/utility panes when available.
    registry.add("Server Console", "open_log_hub", section="Tools", order=10)
