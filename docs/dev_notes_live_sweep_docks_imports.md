# Dev Notes — Live Sweep (Docks/Menu/Import/ST)

Date: 2025-10-22

## Summary

- Dock manager now guarantees `objectName` assignment during creation and keeps
  area registration in sync when users move docks via the context menu.
- Quick Access toolbar gated behind `feature_flags.enable_quick_toolbar`
  (defaults to `false`). Toggle via Settings → Debug & Feature Flags or by
  editing `config/comfyvn.json`.
- Tools menu gains an **Import** submenu. The “From File…” entry streams JSON
  payloads through `/st/import` or `/api/imports/*` and uploads archives to
  `/import/vnpack/extract`. Existing SillyTavern presets remain accessible for
  manual tweaking.
- SillyTavern integration settings expose discrete host, port, and plugin base
  controls inside Studio Basics. `integrations.sillytavern` now stores
  `host`, `port`, `base_url`, and `plugin_base`.
- Help menu links to the refreshed documentation set (Import Guide, SillyTavern
  Bridge, Legal & Liability, Docking & Layout).

## Testing Notes

- Run `python tools/doctor_phase_all.py --out .doctor_all.json` to validate the
  bridge health probes and dock naming regression tests.
- Execute `pytest -q -s -vv -k settings_api -o timeout=60` to exercise the
  settings persistence path, including the new SillyTavern fields.
- Manual sanity check: launch the GUI, open a few docks, right-click to move
  them, and confirm `QMainWindow::saveState()` logs stay clean.

## Follow-ups

- Consider adding async upload progress indicators for large VN pack archives.
- Evaluate auto-detection for SillyTavern base path when the plugin responds at
  a different prefix.
- Extend Import Manager presets with schema hints so modders can build payloads
  from scratch without referencing server code.
