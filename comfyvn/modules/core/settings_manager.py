# comfyvn/modules/core/settings_manager.py
# ⚙️ 3. Server Core Production Chat — Settings Manager
# Version: 1.0 | Date: 2025-10-11

from __future__ import annotations
import os, json
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# -----------------------------------------------------
# CONFIG STRUCTURE
# -----------------------------------------------------
class ComfyVNSettings(BaseSettings):
    """
    Global ComfyVN settings model.
    Loads from .env or system environment.
    """

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # Core server
    APP_NAME: str = "ComfyVN Server Core"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # External system endpoints
    COMFYUI_URL: str = "http://127.0.0.1:8188"
    LMSTUDIO_URL: str = "http://127.0.0.1:1234"
    SILLYTAVERN_URL: str = "http://127.0.0.1:8000"

    # Paths
    PROJECT_ROOT: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])
    DATA_DIR: Path = Field(default_factory=lambda: Path("./data").resolve())
    EXPORTS_DIR: Path = Field(default_factory=lambda: Path("./exports").resolve())
    LOGS_DIR: Path = Field(default_factory=lambda: Path("./logs").resolve())
    TEMP_DIR: Path = Field(default_factory=lambda: Path("./tmp").resolve())

    # Rendering and pipeline
    DEFAULT_MODEL: str = "gpt-4o-mini"
    DEFAULT_STYLE: str = "realistic"
    DEFAULT_RESOLUTION: str = "1024x768"

    # Integration flags
    ENABLE_RENPY_EXPORT: bool = True
    ENABLE_COMFYUI_RENDER: bool = True
    ENABLE_LMSTUDIO_CHAT: bool = True

    # Authentication (for GUI connections)
    API_TOKEN: Optional[str] = None

    # Validators
    @field_validator("DATA_DIR", "EXPORTS_DIR", "LOGS_DIR", "TEMP_DIR", mode="before")
    def _resolve_paths(cls, v: Any) -> Path:
        return Path(v).expanduser().resolve()

# -----------------------------------------------------
# SETTINGS MANAGER CLASS
# -----------------------------------------------------
class SettingsManager:
    """
    Provides global access to settings with reload and export features.
    """

    def __init__(self):
        self._settings = ComfyVNSettings()
        self._cache_file = Path(self._settings.DATA_DIR, "config_cache.json")
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Ensure required directories exist."""
        for p in [
            self._settings.DATA_DIR,
            self._settings.EXPORTS_DIR,
            self._settings.LOGS_DIR,
            self._settings.TEMP_DIR,
        ]:
            p.mkdir(parents=True, exist_ok=True)

    # ------------------------------
    # PUBLIC INTERFACE
    # ------------------------------
    def get(self, key: str) -> Any:
        """Get a setting by key (dot-path supported)."""
        if "." in key:
            parts = key.split(".")
            val = self._settings
            for p in parts:
                val = getattr(val, p, None)
                if val is None:
                    break
            return val
        return getattr(self._settings, key, None)

    def to_dict(self) -> Dict[str, Any]:
        """Return settings as dictionary."""
        return self._settings.model_dump()

    def reload(self) -> Dict[str, Any]:
        """Reload settings from .env and refresh cache."""
        self._settings = ComfyVNSettings()
        self._ensure_dirs()
        self._save_cache()
        return self._settings.model_dump()

    def _save_cache(self):
        """Save current settings snapshot to cache."""
        with open(self._cache_file, "w", encoding="utf-8") as f:
            json.dump(self._settings.model_dump(), f, indent=2, ensure_ascii=False)

    def export(self, out_path: Optional[Path] = None):
        """Export settings to JSON for debugging or GUI display."""
        path = out_path or self._cache_file
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._settings.model_dump(), f, indent=2, ensure_ascii=False)
        return str(path)

# -----------------------------------------------------
# SINGLETON INSTANCE
# -----------------------------------------------------
settings_manager = SettingsManager()
settings = settings_manager._settings

# -----------------------------------------------------
# CLI TEST
# -----------------------------------------------------
if __name__ == "__main__":
    print(json.dumps(settings_manager.to_dict(), indent=2, ensure_ascii=False))
# [⚙️ 3. Server Core Production Chat]
