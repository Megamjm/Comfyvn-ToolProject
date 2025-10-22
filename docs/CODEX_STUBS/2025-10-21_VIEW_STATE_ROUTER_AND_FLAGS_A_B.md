# View State Router & Feature Flags — 2025-10-21

## Intent
- Replace the ad-hoc central tab widget with a router that remembers the last active pane, defaults to the VN Viewer when a project is open, and surfaces quick actions/actions for Assets, Timeline, and Logs.
- Expose Studio-configurable feature flags for ComfyUI preview streaming, SillyTavern bridge integration, and narrator mode; persist the toggles to `config/comfyvn.json` and ensure runtime consumers honour them without restarts.
- Tighten the modder/debug loop so bridge helpers, world sync tools, and the VN Chat overlay fail fast (or hide) when connectors are disabled, and so scripts can read the same flag state via a shared utility.

## Touchpoints
- GUI: `comfyvn/gui/central/center_router.py` (new) drives view switching, inline narrator playback, and quick actions; `MainWindow` now instantiates the router, and `gui/world_ui.py` listens for feature-flag toasts to enable/disable SillyTavern sync controls.
- Settings: `comfyvn/gui/panels/settings_panel.py` gains checkboxes for `enable_comfy_preview_stream`, `enable_sillytavern_bridge`, and `enable_narrator_mode`, publishing updates through the notifier bus.
- Feature services: `comfyvn/config/feature_flags.py` centralises flag loading; bridge consumers (`core/world_loader.py`, `core/st_sync_manager.py`, `bridge/st_bridge/health.py`) and GUI helpers now consult it before touching external systems.

## Acceptance Hooks
- Opening a project sets the router to “VN Viewer”; closing a project resets state. Switching to the Character Designer via menu or quick action should reuse the same widget instance and persist selection via `session_manager`.
- Toggling the new flags updates `config/comfyvn.json`, fires a toast with `meta.feature_flags`, and immediately hides/shows the preview stream, narrator overlay, and SillyTavern controls without requiring a restart.
- World sync helpers and `/st/health` return `{"status": "disabled"}` when the bridge flag is off, preventing accidental network calls in scripts or CI runs.

## Debug Notes
- Programmatic access: import `comfyvn.config.feature_flags` and call `load_feature_flags()` / `is_enabled()`; after manual edits invoke `refresh_cache()` so long-lived processes pick up changes.
- VN Viewer preview capture writes to `data/cache/comfy_previews`; disable `enable_comfy_preview_stream` to stop manifest churn when testing workflows that do their own image polling.
- Narrator mode uses the existing VN Chat panel: when the flag is enabled the router mounts the chat widget beneath the viewer, so modded overlays can subscribe to the same notifier events to stay in sync.
- SillyTavern bridge consumers should treat `status == "disabled"` responses as expected; Surface tailored warnings instead of treating them as errors, and encourage users to flip the flag back on from Settings when ready.
