from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/modules/mode_manager.py
# ⚙️ Mode Manager – Persistent Runtime Mode Handler (Patch M)
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

import json, os
from enum import Enum


class Modes(Enum):
    VISUAL_NOVEL = "vn"
    RPG = "rpg"
    CINEMATIC = "cinematic"
    PLAYGROUND = "playground"


class ModeManager:
    """
    Handles the global operational mode for the ComfyVN runtime.
    Supports in-memory switching and optional persistence to /data/config.json.
    """

    def __init__(self, config_path: str = "./data/config.json"):
        self.config_path = os.path.abspath(config_path)
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        self.current_mode = self._load_mode()

    # -------------------------------------------------
    # Mode Accessors
    # -------------------------------------------------
    def set_mode(self, mode_name: str):
        """Switch the runtime mode and persist."""
        try:
            self.current_mode = Modes(mode_name.lower())
            self._save_mode()
            print(f"[ModeManager] Mode switched → {self.current_mode.value}")
        except ValueError:
            raise ValueError(
                f"Unknown mode: {mode_name}. Valid: {[m.value for m in Modes]}"
            )

    def get_mode(self) -> str:
        """Return current runtime mode name."""
        return self.current_mode.value

    def list_modes(self):
        """Return all available mode identifiers."""
        return [m.value for m in Modes]

    # -------------------------------------------------
    # Persistence
    # -------------------------------------------------
    def _save_mode(self):
        """Write the current mode to config.json."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"mode": self.current_mode.value}, f, indent=2)
        except Exception as e:
            print(f"[ModeManager] Failed to save mode: {e}")

    def _load_mode(self) -> Modes:
        """Read last mode from config.json or default to VISUAL_NOVEL."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return Modes(data.get("mode", "vn"))
            except Exception:
                pass
        return Modes.VISUAL_NOVEL