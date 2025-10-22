"""Default menu registrations for the ComfyVN main window."""

from __future__ import annotations

from comfyvn.core.menu_runtime_bridge import MenuRegistry


def register_core_menu_items(registry: MenuRegistry) -> None:
    """Populate the registry with built-in menu entries."""
    # File menu
    registry.add("New Project", "new_project", section="File", order=10)
    registry.add("Close Project", "close_project", section="File", order=20)
    registry.add("Recent Projects", "open_recent_projects", section="File", order=30)
    registry.add(
        "Open Projects Folder",
        "open_projects_folder",
        section="File",
        separator_before=True,
        order=40,
    )
    registry.add("Open Data Folder", "open_data_folder", section="File", order=50)
    registry.add("Open Logs Folder", "open_logs_folder", section="File", order=60)
    registry.add("Exit", "close", section="File", separator_before=True, order=200)

    # Module-centric entries reflect the primary dock panels.
    registry.add("Studio Center", "open_studio_center", section="Modules", order=10)
    registry.add("Scenes", "open_scenes_panel", section="Modules", order=20)
    registry.add("Characters", "open_characters_panel", section="Modules", order=30)
    registry.add(
        "Character Designer",
        "open_character_designer",
        section="Modules",
        order=32,
    )
    registry.add(
        "Player Persona", "open_player_persona_panel", section="Modules", order=35
    )
    registry.add("Assets", "open_asset_browser", section="Modules", order=40)
    registry.add("Playground", "open_playground", section="Modules", order=50)
    registry.add("Sprites", "open_sprite_panel", section="Modules", order=55)
    registry.add("Timeline", "open_timeline", section="Modules", order=60)
    registry.add(
        "Worldline Graph",
        "open_diffmerge_graph",
        section="Modules",
        order=62,
    )
    registry.add("VN Chat", "open_vn_chat_panel", section="Modules", order=65)
    registry.add(
        "Imports",
        "open_imports_panel",
        section="Modules",
        separator_before=True,
        order=70,
    )
    registry.add("Audio", "open_audio_panel", section="Modules", order=80)
    registry.add("Advisory", "open_advisory_panel", section="Modules", order=90)
    registry.add(
        "System Status",
        "open_telemetry",
        section="Modules",
        separator_before=True,
        order=100,
    )
    registry.add("Log Hub", "open_log_hub", section="Modules", order=110)

    # Tools and Extensions utility entries.
    registry.add("Reload Menus", "reload_menus", section="Tools", order=5)
    registry.add(
        "Launch Detached Server", "launch_detached_server", section="Tools", order=10
    )
    registry.add("Reconnect Server", "manual_reconnect", section="Tools", order=15)
    registry.add(
        "Install Base Scripts",
        "install_base_scripts",
        section="Tools",
        separator_before=True,
        order=100,
    )

    registry.add("Reload Extensions", "reload_menus", section="Extensions", order=5)
    registry.add(
        "Open Extensions Folder",
        "open_extensions_folder",
        section="Extensions",
        order=10,
    )
    registry.add("Settings Panel", "open_settings_panel", section="Settings", order=10)
