# Accessibility & Input Profiles

This note documents the accessibility manager, input map subsystem, and relevant API surfaces introduced on 2025-11-29.

## Modules & Persistence

- `comfyvn/accessibility/__init__.py` exposes `accessibility_manager`: font scaling, color filters/high-contrast palettes, and subtitle overlays persist to `config/settings/accessibility.json` and write structured entries to `logs/accessibility.log`.
- Colorblind LUT overlays (`FilterOverlay`) live in `comfyvn/accessibility/filters.py`; subtitle overlays (`SubtitleOverlay`) live in `comfyvn/accessibility/subtitles.py`.
- Controller-aware input bindings are handled by `comfyvn/accessibility/input_map.py`. Bindings default to the values captured in `SettingsManager.DEFAULTS["input_map"]` and can be reset at runtime.
- New feature flags (`enable_accessibility_controls`, `enable_accessibility_api`, `enable_controller_profiles`) are persisted in `config/comfyvn.json` and surfaced through Settings → Debug & Feature Flags.

## FastAPI Surface

Accessible behind `enable_accessibility_api` (default: true):

| Route | Method | Description |
| --- | --- | --- |
| `/api/accessibility/state` | GET/POST | Retrieve or update font scale, color filter, high contrast, and subtitle toggles. |
| `/api/accessibility/filters` | GET | Enumerate available colorblind/high-contrast filter presets. |
| `/api/accessibility/subtitle` | POST/DELETE | Push or clear the runtime subtitle overlay. |
| `/api/accessibility/input-map` | GET/POST | Inspect or update keyboard/controller bindings. |
| `/api/accessibility/input/event` | POST | Trigger an input action (fires callbacks, logs, and modder hooks). |

All responses are JSON and include structured logging extras (see `comfyvn/server/routes/accessibility.py`).

## Studio Integration

- Settings → **Accessibility**: QDoubleSpinBox for font multiplier, color filter combo box, and toggles for high contrast + subtitles. Changes apply immediately.
- Settings → **Input & Controllers**: captures primary/secondary shortcuts via `ShortcutCapture`, assigns controller buttons (QtGamepad when available), and offers per-action + global reset buttons.
- VN Viewer registers with both systems: overlays update without re-rendering, and remapped inputs (keyboard or controller) trigger the viewer callback chain, emit subtitles, and post structured events.

## Modder Hooks & Logging

- `on_accessibility_settings`, `on_accessibility_subtitle`, `on_accessibility_input_map`, and `on_accessibility_input` now ship from `comfyvn/core/modder_hooks.py`.
- Accessibility manager + input map log to `logs/accessibility.log` (rotating file, 500 KB, 3 backups). Input triggers include `event=accessibility.input.trigger` extras in `server.log` as well.

## Testing Notes

- GUI shortcuts require Qt; headless runs skip shortcut registration gracefully. `python -m compileall comfyvn/accessibility` performs a quick smoke compilation.
- Controller support depends on QtGamepad; when unavailable, the adapter logs a warning and continues without raising.
