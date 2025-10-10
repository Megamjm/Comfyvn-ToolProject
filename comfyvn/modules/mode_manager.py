# comfyvn/modules/mode_manager.py
# ⚙️ 3. Server Core Production Chat

from enum import Enum

class Modes(Enum):
    VISUAL_NOVEL = "vn"
    RPG = "rpg"
    CINEMATIC = "cinematic"
    PLAYGROUND = "playground"

class ModeManager:
    """Handles the global operational mode for ComfyVN runtime."""

    def __init__(self):
        self.current_mode = Modes.VISUAL_NOVEL

    def set_mode(self, mode_name: str):
        """Switches runtime mode."""
        try:
            self.current_mode = Modes(mode_name.lower())
        except ValueError:
            raise ValueError(f"Unknown mode: {mode_name}. Valid: {[m.value for m in Modes]}")

    def get_mode(self) -> str:
        return self.current_mode.value

    def list_modes(self):
        return [m.value for m in Modes]
