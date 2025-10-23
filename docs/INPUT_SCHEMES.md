# Input Schemes & Controller Profiles

The input manager centralises keyboard and controller bindings for the Studio viewer, editors, and automation hooks. Bindings persist to `config/settings/accessibility.json` under `input_map` (mirrored to the SQLite `settings` table), can be remapped live inside Studio, and remain scriptable via FastAPI.

## Default Bindings

### Keyboard (Viewer & Editor)

| Action | Default Keys | Category | Notes |
| --- | --- | --- | --- |
| `viewer.advance` | `Space`, `Right` | Viewer | Advance dialogue / continue. |
| `viewer.back` | `Backspace`, `Left` | Viewer | Backlog / previous line. |
| `viewer.skip` | `Ctrl+F` | Viewer | Toggle skip/fast-forward mode. |
| `viewer.menu` | `Escape` | Viewer | Open viewer menu. |
| `viewer.overlays_toggle` | `V` | Viewer | Toggle overlay stack. |
| `viewer.narrator_toggle` | `N` | Viewer | Toggle narrator voice. |
| `viewer.choice_1`–`viewer.choice_9` | `1`–`9` | Viewer | Select numbered choices. |
| `editor.pick_winner` | `P` | Editor | Flag the active branch as the winner in editor tooling. |

Controllers inherit the same actions; defaults map `Advance/Back/Menu/Skip` to face buttons, overlays to `Y`, narrator toggle to `Select/Back`, and pick-winner to `R1`. Choice bindings ship unassigned for controllers so teams can tailor layouts per device.

## Studio Panel

Settings → **Input & Controllers** lists every action with:

- **Primary** / **Secondary** keyboard captures (uses `ShortcutCapture`).
- **Controller** drop-down populated from `input_map_manager.available_gamepad_bindings()`.
- **Apply / Reset** buttons per action plus a global reset.

Updates apply immediately, persist to disk, refresh controller listeners, and fire modder hooks with `reason="update"`.

## API Surface

Bindings share payloads across both namespaces:

| Route | Method | Description |
| --- | --- | --- |
| `/api/accessibility/input-map` | GET | Returns `bindings`, `gamepad_options`, and `controller_enabled`. |
| `/api/accessibility/input-map` | POST | Update a single binding (primary/secondary/gamepad). |
| `/api/input/map` | GET/POST | Alias of the same payloads under `/api/input`. |
| `/api/input/reset` | POST | Reset all bindings to defaults and return the refreshed map. |

### Example: Bind Choice 1 to `Q`

```bash
curl -X POST http://127.0.0.1:8001/api/input/map \
  -H 'Content-Type: application/json' \
  -d '{
        "action": "viewer.choice_1",
        "primary": "Q",
        "gamepad": "dpad_up"
      }'
```

## Export / Import

- `input_map_manager.export_bindings()` → `{action: {label, primary, secondary, gamepad, category}}`
- `input_map_manager.import_bindings(payload, merge=False)` → replaces (or merges) bindings and emits modder hooks with `reason="import"`.
- `/api/accessibility/export` bundles both accessibility settings and bindings; `/api/accessibility/import` applies them (set `merge_bindings=true` to preserve existing keys where the payload omits entries).

Bindings that are reset via API or UI emit `reason="reset"` through `on_accessibility_input_map`, allowing dashboards to keep histories without polling.

## Modder Hooks

- `on_accessibility_input_map` — fires on update/reset/import with payload `{action, binding, timestamp, event_id, reason}`.
- `on_accessibility_input` — fires whenever a mapped input triggers (keyboard, controller, or `/api/accessibility/input/event`), including viewer choice metadata (`meta: {"choice": N}` where applicable).

See `docs/dev_notes_modder_hooks.md` for examples and WebSocket usage.

## Debug & Verification

- Use `/api/accessibility/input-map` to snapshot bindings before/after automation updates.
- Input events log to `logs/accessibility.log` with `event=accessibility.input_map.binding` (`reason` context) and `event=accessibility.input.trigger`.
- `python tools/check_current_system.py --profile p4_accessibility --base http://127.0.0.1:8001` verifies routes, feature flags, and doc presence.
