from __future__ import annotations

import copy

from fastapi import APIRouter, Body, HTTPException

try:
    from PySide6.QtGui import QAction  # type: ignore  # pragma: no cover
except Exception:  # pragma: no cover - optional dependency
    QAction = None  # type: ignore

from comfyvn.core.settings_manager import SettingsManager

router = APIRouter(prefix="/settings", tags=["settings"])
_settings = SettingsManager()


def _merge_settings(base: dict, updates: dict) -> dict:
    """Recursively merge dictionaries, matching the launcher behaviour."""
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _merge_settings(base[key], value)
        else:
            base[key] = value
    return base


def _apply_update(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be a JSON object.")
    current = _settings.load()
    merged = _merge_settings(copy.deepcopy(current), payload)
    _settings.save(merged)
    return merged


@router.get("/get")
def get_settings():
    return _settings.load()


@router.post("/set")
def set_settings(payload: dict = Body(...)):
    merged = _apply_update(payload or {})
    return {"ok": True, "settings": merged, "saved": str(_settings.path)}


@router.post("/save")
def save_settings(payload: dict = Body(...)):
    merged = _apply_update(payload or {})
    return {"ok": True, "settings": merged, "saved": str(_settings.path)}
