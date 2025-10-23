# Accessibility Controls

ComfyVN ships a dedicated accessibility stack that covers UI legibility (font/UI scale), color perception (filters + high-contrast palette), and viewer subtitles. Preferences persist to `config/settings/accessibility.json`, apply live in the Studio shell, and remain scriptable through FastAPI + modder hooks.

## Feature Flags

| Flag | Default | Description |
| --- | --- | --- |
| `enable_accessibility` | `false` | Master toggle for accessibility APIs and UI scale manager. Turn on before exposing routes to automation. |
| `enable_accessibility_controls` | `true` | Shows the Accessibility & Input panels inside Studio settings. |
| `enable_accessibility_api` | `true` | Enables the `/api/accessibility/*` surface. |
| `enable_controller_profiles` | `true` | Activates QtGamepad-aware controller mapping in the input manager. |

Flip flags in `config/comfyvn.json` or via Settings → **Debug & Feature Flags**. All four must be enabled to exercise the full surface.

## Settings Panel

Settings → **Accessibility** applies changes instantly:

- **UI Scale (100–200 %)** – global preset applied to every registered widget. The viewer can opt into its own override ("Follow global" by default).
- **Font Scale (0.75–2.5×)** – multiplies the base Qt font size and pairs well with UI scale for dense or large displays.
- **Color Filter Presets** – `None`, High Contrast overlay, and protan/deutan/tritan simulations rendered by `FilterOverlay`.
- **High-Contrast Palette** – swaps the Qt palette to dark backgrounds + light text without touching content renders.
- **Subtitles Toggle** – enables the viewer subtitle overlay fed by `/api/accessibility/subtitle` or hotkeys.

Settings → **Input & Controllers** exposes matching controls for keyboard/controller bindings; see `docs/INPUT_SCHEMES.md` for details.

## Persistence & Files

- Runtime state: `config/settings/accessibility.json` (mirrored to the SQLite `settings` table through the shared `SettingsManager`)
- Logs: `logs/accessibility.log`
- Default presets: `comfyvn/core/settings_manager.py` (`DEFAULTS["accessibility"]` and `DEFAULTS["input_map"]`)

The accessibility manager caches the original Qt font + palette so resets restore the baseline.

## API Surface

All routes require `enable_accessibility=true` *and* `enable_accessibility_api=true`:

| Route | Method | Payload |
| --- | --- | --- |
| `/api/accessibility/state` | GET | Returns current accessibility state. |
| `/api/accessibility/state` | POST | Update any subset of fields (`font_scale`, `color_filter`, `high_contrast`, `subtitles_enabled`, `ui_scale`, `view_overrides`). |
| `/api/accessibility/set` | POST | Alias for the POST above (legacy tooling). |
| `/api/accessibility/filters` | GET | Lists available color filter presets (key/label/description). |
| `/api/accessibility/subtitle` | POST/DELETE | Push or clear viewer subtitles (`text`, `origin`, `ttl`). |
| `/api/accessibility/export` | GET | Returns `{"accessibility": {...}, "input_bindings": {...}}`. |
| `/api/accessibility/import` | POST | Accepts the export payload. `merge_bindings=true` preserves existing bindings and only overwrites supplied ones. |
| `/api/accessibility/input-map` | GET/POST | Inspect/update bindings (mirrors `/api/input/map`). |
| `/api/accessibility/input/event` | POST | Triggers an input action; optional `meta` (e.g., `{ "choice": 1 }`). |
| `/api/input/map` | GET/POST | Namespaced alias of the input map surface. |
| `/api/input/reset` | POST | Resets bindings to defaults and returns the refreshed map. |

### Example: Toggling High Contrast + Viewer Override

```bash
curl -X POST http://127.0.0.1:8001/api/accessibility/state \
  -H 'Content-Type: application/json' \
  -d '{
        "high_contrast": true,
        "ui_scale": 1.5,
        "view_overrides": {"viewer": 1.75}
      }'
```

### Example: Importing a Profile

```bash
curl -X POST http://127.0.0.1:8001/api/accessibility/import \
  -H 'Content-Type: application/json' \
  -d '{
        "accessibility": {
          "font_scale": 1.2,
          "ui_scale": 1.25,
          "color_filter": "deutan",
          "subtitles_enabled": true,
          "high_contrast": false,
          "view_overrides": {"viewer": 1.5}
        },
        "input_bindings": {},
        "merge_bindings": false
      }'
```

## Modder Hooks

`comfyvn/core/modder_hooks.py` emits:

- `on_accessibility_settings` — payload includes `state` (`ui_scale`, `view_overrides`, etc.), `timestamp`, and `source`.
- `on_accessibility_subtitle` — `text`, `origin`, `expires_at`, `enabled`, `reason`.
- `on_accessibility_input_map` — `binding`, `timestamp`, `event_id`, `reason` (`update`, `reset`, `import`).
- `on_accessibility_input` — fired when a mapped action triggers (`action`, `source`, optional `meta`).

Pair with `docs/dev_notes_modder_hooks.md` for sample payloads and WS usage.

## Debug & Verification

- UI scale + font operations log to `logs/accessibility.log` (`event=accessibility.ui_scale.update`, `event=accessibility.settings`).
- Checker profile: `python tools/check_current_system.py --profile p4_accessibility --base http://127.0.0.1:8001` verifies feature flags, routes, and required docs.
- Headless smoke test: `python -m compileall comfyvn/accessibility` ensures Python-level imports succeed without Qt.

## References

- `comfyvn/accessibility/__init__.py`
- `comfyvn/accessibility/ui_scale.py`
- `comfyvn/server/routes/accessibility.py`
- `docs/INPUT_SCHEMES.md`
- `docs/dev_notes_modder_hooks.md`
