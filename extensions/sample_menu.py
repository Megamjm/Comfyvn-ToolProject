# Sample extension: adds a few menu items to the studio
def register(menu_registry):
    menu_registry.add("Studio Center", "open_studio_center", section="View")
    menu_registry.add("Assets", "open_asset_browser", section="View")
    menu_registry.add("Playground", "open_playground", section="View")
    menu_registry.add("Timeline", "open_timeline", section="View")
    menu_registry.add("System Status", "open_telemetry", section="View", separator_before=True)
    menu_registry.add("Log Hub", "open_log_hub", section="View")
