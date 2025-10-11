# comfyvn/modules/audio_manager.py
# 🔊 Audio Manager – GUI Toggle Integration (Patch C)
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

from typing import Dict

class AudioManager:
    """
    Controls playback flags for sound, music, voice, ambience, and effects.
    Designed for use with the GUI Settings → Audio tab.
    """

    def __init__(self) -> None:
        self.media_settings: Dict[str, bool] = {
            "sound": True,
            "music": True,
            "voice": False,
            "ambience": True,
            "fx": True,
        }

    # -------------------------------------------------
    # Toggle and State Retrieval
    # -------------------------------------------------
    def toggle(self, key: str, state: bool) -> Dict[str, bool]:
        """
        Enable or disable a specific audio category.
        Returns the current settings dict for GUI sync.
        """
        if key in self.media_settings:
            self.media_settings[key] = bool(state)
            print(f"[AudioManager] Set {key} → {state}")
        else:
            print(f"[AudioManager] Unknown key: {key}")
        return self.media_settings

    def get(self) -> Dict[str, bool]:
        """Return a copy of the current audio configuration."""
        return dict(self.media_settings)
