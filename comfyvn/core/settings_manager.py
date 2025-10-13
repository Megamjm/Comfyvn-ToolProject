# comfyvn/core/settings_manager.py
# Pydantic v2 settings with safe fallback if pydantic_settings is unavailable.
# [COMFYVN Architect | settings_manager fix]

from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel, Field

# Try official package. Fallback to a light shim if import fails.
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict  # v2.x

    _USING_SHIM = False
except Exception:  # package missing or broken
    _USING_SHIM = True

    class BaseSettings(BaseModel):  # very small subset
        model_config = {"extra": "ignore"}

        def model_dump(self, *a, **k):
            return super().model_dump(*a, **k)

    def SettingsConfigDict(**kwargs):
        return kwargs  # placeholder


DATA_DIR = Path("./comfyvn/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
OVERRIDES_PATH = DATA_DIR / "settings_overrides.json"


class Settings(BaseSettings):
    # Server
    APP_NAME: str = Field(default="ComfyVN Server")
    HOST: str = Field(default="127.0.0.1")
    PORT: int = Field(default=8000)

    # Integrations
    API_BASE: str = Field(default="http://127.0.0.1:8000")
    COMFYUI_NODE_PATH: str = Field(default="./comfyui/custom_nodes")
    SILLYTAVERN_URL: str = Field(default="http://127.0.0.1:8000")

    # Dev toggles
    UVICORN_RELOAD: bool = Field(default=False)

    # pydantic-settings v2 config (env_file + prefix). Shim accepts dict too.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="COMFYVN_",
        extra="ignore",
    )


def _read_overrides() -> Dict[str, Any]:
    if OVERRIDES_PATH.exists():
        try:
            with OVERRIDES_PATH.open("r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}
    return {}


def _write_overrides(data: Dict[str, Any]) -> None:
    tmp = OVERRIDES_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data or {}, f, indent=2, ensure_ascii=False)
    tmp.replace(OVERRIDES_PATH)


class SettingsManager:
    def __init__(self) -> None:
        # Base from env
        base = Settings()
        # Apply persisted overrides
        overrides = _read_overrides()
        self._settings: Settings = base.model_copy(update=overrides)

        if _USING_SHIM:
            print(
                "[Settings] pydantic_settings not found. Using shim. Install 'pydantic-settings>=2' for full features."
            )

    # Expose current effective settings
    @property
    def settings(self) -> Settings:
        return self._settings

    # Persist a set of overrides and refresh the in-memory model
    def set_many(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        cur = _read_overrides()
        cur.update(updates or {})
        _write_overrides(cur)
        # Rebuild effective settings
        self._settings = Settings().model_copy(update=cur)
        return self.dump()

    def dump(self) -> Dict[str, Any]:
        return self._settings.model_dump()

    # Convenience accessors
    def __getattr__(self, item: str) -> Any:
        # allow settings_manager.HOST style access
        if hasattr(self._settings, item):
            return getattr(self._settings, item)
        raise AttributeError(item)


# Singleton exports used by app.py
settings_manager = SettingsManager()
settings: Settings = settings_manager.settings
