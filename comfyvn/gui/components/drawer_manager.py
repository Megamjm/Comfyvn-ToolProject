# comfyvn/gui/components/drawer_manager.py
# 🧠 DrawerManager — persistent open/closed state tracker for DrawerWidget
# [🎨 GUI Code Production Chat | Phase 3.6-UX]

import json
from pathlib import Path


class DrawerManager:
    """Mixin to persist DrawerWidget open/closed state between app launches."""

    def __init__(self, state_file: str = "./data/ui_state.json"):
        self._ui_state_path = Path(state_file)
        self._ui_state = {}
        self._load_ui_state()

    # ------------------------------------------------------------
    def _load_ui_state(self):
        if not self._ui_state_path.exists():
            self._ui_state = {"drawers": {}}
            return
        try:
            with open(self._ui_state_path, "r", encoding="utf-8") as f:
                self._ui_state = json.load(f)
        except Exception:
            self._ui_state = {"drawers": {}}

    def _save_ui_state(self):
        self._ui_state_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._ui_state_path, "w", encoding="utf-8") as f:
                json.dump(self._ui_state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[DrawerManager] Failed to save UI state: {e}")

    # ------------------------------------------------------------
    def register_drawer_widget(self, drawer_widget):
        """Attach to a DrawerWidget instance."""
        self._drawer_widget = drawer_widget
        self._restore_state()
        # Watch headers for toggle changes
        for section in drawer_widget.sections:
            header = section["header"]
            header.toggled.connect(
                lambda checked, name=header.text(): self._record_state(name, checked)
            )

    def _record_state(self, name: str, checked: bool):
        self._ui_state.setdefault("drawers", {})[name] = checked
        self._save_ui_state()

    def _restore_state(self):
        """Reapply saved open/closed states."""
        if not hasattr(self, "_drawer_widget"):
            return
        saved = self._ui_state.get("drawers", {})
        for section in self._drawer_widget.sections:
            header = section["header"]
            if header.text() in saved:
                header.setChecked(saved[header.text()])
