# comfyvn/core/menu_runtime_bridge.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Callable, Optional

@dataclass
class MenuItem:
    label: str
    handler: str                 # name of bound method on MainWindow
    section: str = "View"        # File, View, Tools, GPU, Window, Spaces, Help
    separator_before: bool = False

class MenuRegistry:
    def __init__(self):
        self.items: List[MenuItem] = []
    def add(self, item: MenuItem):
        self.items.append(item)
    def extend(self, items: List[MenuItem]):
        self.items.extend(items)
    def clear_all(self):
        self.items.clear()
    def by_section(self) -> Dict[str, List[MenuItem]]:
        out: Dict[str, List[MenuItem]] = {}
        for it in self.items:
            out.setdefault(it.section, []).append(it)
        return out

menu_registry = MenuRegistry()

def _seed_defaults():
    # --- File ---
    menu_registry.extend([
        MenuItem("New Project", "new_project", "File"),
        MenuItem("Save Project", "save_project", "File"),
        MenuItem("Save Project As…", "save_project_as", "File"),
        MenuItem("Load Project", "load_project", "File"),
        MenuItem("Export → Ren’Py", "export_to_renpy", "File", separator_before=True),
        MenuItem("Import → Manga", "import_manga", "File"),
        MenuItem("Import → VN", "import_vn", "File"),
        MenuItem("Import → Assets", "import_assets", "File"),
        MenuItem("Exit", "cmd_exit", "File", separator_before=True),
    ])
    # --- View ---
    for lbl, fn in [
        ("Dashboard", "open_dashboard"),
        ("Assets", "open_assets"),
        ("Timeline", "open_timeline"),
        ("Playground", "open_playground"),
        ("Render Queue", "open_render"),
        ("Settings Panel", "open_settings_panel"),
        ("Logs Console", "toggle_log_console"),
        ("Extensions", "open_extensions"),
    ]:
        menu_registry.add(MenuItem(lbl, fn, "View"))
    # --- GPU ---
    for lbl, fn in [
        ("GPU Setup…", "open_gpu_setup"),
        ("Open Local GPU Panel", "open_gpu_local"),
        ("Open Remote GPU Panel", "open_gpu_remote"),
        ("Refresh Metrics", "refresh_server_metrics"),
    ]:
        menu_registry.add(MenuItem(lbl, fn, "GPU"))
    # --- Tools ---
    for lbl, fn in [
        ("Start Server (detached)", "start_server_manual"),
        ("Save Workspace", "save_workspace"),
        ("Load Workspace", "load_workspace"),
        ("Submit Dummy Render", "submit_dummy_render"),
        ("Extension Manager…", "open_extension_manager"),
    ]:
        menu_registry.add(MenuItem(lbl, fn, "Tools"))
    # --- Window ---
    for lbl, fn in [
        ("Reset Layout", "reset_layout"),
        ("Toggle Fullscreen", "toggle_fullscreen"),
    ]:
        menu_registry.add(MenuItem(lbl, fn, "Window"))
    # --- Spaces ---
    for lbl, fn in [
        ("Editor Space", "switch_space_editor"),
        ("Render Space", "switch_space_render"),
        ("Import Space", "switch_space_import"),
        ("GPU Space", "switch_space_gpu"),
        ("System Logs", "switch_space_system"),
    ]:
        menu_registry.add(MenuItem(lbl, fn, "Spaces"))
    # --- Help ---
    menu_registry.add(MenuItem("About ComfyVN…", "show_about", "Help"))

# Always seed baseline items; extensions can add more later
_seed_defaults()
