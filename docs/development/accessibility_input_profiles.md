# Accessibility & Input Profiles

This note documents the accessibility manager, UI scale controller, input map subsystem, and relevant API surfaces introduced on 2025-11-29 and extended on 2025-12-14.

## Modules & Persistence

- `comfyvn/accessibility/__init__.py` exposes `accessibility_manager`: font scaling, color filters/high-contrast palettes, UI scaling, and subtitle overlays persist to `config/settings/accessibility.json` (mirrored to the SQLite `settings` table) and write structured entries to `logs/accessibility.log`.
- `comfyvn/accessibility/ui_scale.py` owns global/per-view UI scaling. Widgets register via `ui_scale_manager.register_widget(widget, view="viewer")` and receive layout/font adjustments when global or override values change.
- Colorblind LUT overlays (`FilterOverlay`) live in `comfyvn/accessibility/filters.py`; subtitle overlays (`SubtitleOverlay`) live in `comfyvn/accessibility/subtitles.py`.
- Controller-aware input bindings are handled by `comfyvn/accessibility/input_map.py`. Bindings default to the values captured in `SettingsManager.DEFAULTS["input_map"]` and can be reset or imported at runtime.
- Feature flags (`enable_accessibility`, `enable_accessibility_controls`, `enable_accessibility_api`, `enable_controller_profiles`) are persisted in `config/comfyvn.json` and surfaced through Settings → Debug & Feature Flags.

## FastAPI Surface

Accessible when both `enable_accessibility` (default: false) and `enable_accessibility_api` (default: true) are enabled:

| Route | Method | Description |
| --- | --- | --- |
| `/api/accessibility/state` | GET/POST | Retrieve or update font scale, color filter, high contrast, subtitles, UI scale, and per-view overrides. |
| `/api/accessibility/set` | POST | Alias for `/api/accessibility/state` (POST) kept for tooling compatibility. |
| `/api/accessibility/filters` | GET | Enumerate available colorblind/high-contrast filter presets. |
| `/api/accessibility/subtitle` | POST/DELETE | Push or clear the runtime subtitle overlay. |
| `/api/accessibility/export` | GET | Export persisted accessibility settings and input bindings as JSON. |
| `/api/accessibility/import` | POST | Import accessibility settings and (optionally) input bindings. Supports merge mode for bindings. |
| `/api/accessibility/input-map` | GET/POST | Inspect or update keyboard/controller bindings. |
| `/api/accessibility/input/event` | POST | Trigger an input action (fires callbacks, logs, and modder hooks). |
| `/api/input/map` | GET/POST | Same payloads as `/api/accessibility/input-map` exposed under the new input namespace. |
| `/api/input/reset` | POST | Reset input bindings to defaults and return the refreshed map. |

All responses are JSON and include structured logging extras (see `comfyvn/server/routes/accessibility.py`).

## Studio Integration

- Settings → **Accessibility**: slider for font multiplier, UI scale presets (100–200 %), viewer-specific override (optional), color filter combo box, and toggles for high contrast + subtitles. Changes apply immediately and persist to `config/settings/accessibility.json`/SQLite `settings`.
- Settings → **Input & Controllers**: captures primary/secondary shortcuts via `ShortcutCapture`, assigns controller buttons (QtGamepad when available), and offers per-action + global reset buttons.
- VN Viewer registers with both systems: UI scale overrides (when set) apply to the viewer container, overlays update without re-rendering, and remapped inputs (keyboard, numeric choices, controller buttons) trigger the viewer callback chain, emit subtitles, and post structured events.

## Export & Import

- `accessibility_manager.export_profile()` / `import_profile()` expose persisted settings for tooling.
- `input_map_manager.export_bindings()` / `import_bindings()` support full replacement (default) or merge updates. Import paths emit `on_accessibility_input_map` events with `reason="import"` so automation can react.
- REST parity lives under `/api/accessibility/export` + `/api/accessibility/import`; input-only consumers can target `/api/input/map` + `/api/input/reset`.
- Default presets and documentation live in `docs/ACCESSIBILITY.md` and `docs/INPUT_SCHEMES.md`.

## Modder Hooks & Logging

- `on_accessibility_settings`, `on_accessibility_subtitle`, `on_accessibility_input_map`, and `on_accessibility_input` ship from `comfyvn/core/modder_hooks.py`. `on_accessibility_settings.state` now includes `ui_scale` and `view_overrides`; `on_accessibility_input_map` adds a `reason` field (`update`, `reset`, `import`).
- Accessibility manager + input map log to `logs/accessibility.log` (rotating file, 500 KB, 3 backups). Input triggers include `event=accessibility.input.trigger` extras in `server.log` as well.

## Testing Notes

- GUI shortcuts require Qt; headless runs skip shortcut registration gracefully. `python -m compileall comfyvn/accessibility` performs a quick smoke compilation.
- Controller support depends on QtGamepad; when unavailable, the adapter logs a warning and continues without raising.
