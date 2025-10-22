# Dev Notes — Settings Port Binding & API Hooks

Updated: 2025-12-24 • Owner: Studio Desktop (Settings) • Channel: `docs/dev_notes_*`

---

## 1. Components & Ownership

- Qt widget: `comfyvn/gui/settings/network_panel.py`
  - Pure Qt (no server imports); safe to load headless tests via `python -m PySide6`.
  - Expects a `ServerBridge` instance; creates one lazily when not provided.
  - Fields: host (`QLineEdit`), ports CSV (`QLineEdit`), public base (`QLineEdit`),
    probe output (`QTextEdit`), status label, and Apply/Probe/Refresh buttons.
- Web admin page: `comfyvn/studio/settings/network.html`
  - Static HTML/JS served under `/studio/settings/network.html`. Requires a Bearer token
    with admin scope; verifies via `/api/auth/me` before unlocking controls.
  - Shares the same inputs as the Qt widget, mirrors probe attempts in a table, and
    renders curl drills modders can copy/paste.
- API surface: `/api/settings/ports/{get,set,probe}` (FastAPI module lives with the
  settings stack).
- Persistence: `config/comfyvn.json → server` for defaults, `config/settings/config.json`
  (user writable) for overrides, `.runtime/last_server.json` for the active binding.

## 2. UI Flow

1. `NetworkPanel.refresh()` (Qt) or `fetchConfig()` (web) fires on init and on demand:
   - Calls `GET /api/settings/ports/get`.
   - Updates form state with the flat `{host, ports, public_base, stamp}` payload.
2. `Apply` / `Save`:
   - Validates CSV → `[int]`; filters invalid entries and warns via toast/status.
   - Posts to `/api/settings/ports/set`, echoes the merged state, and re-runs refresh so
     multiple windows stay aligned.
3. `Probe`:
   - Posts to `/api/settings/ports/probe` with the current host/ports.
   - Qt: writes rows into the read-only text view.
   - Web: renders a table of attempts and highlights the “would bind to” summary.

Status text symbols (`ℹ️/⚠️/❌/✅`) mirror other settings panels. The API hint label at
the bottom lists the REST endpoints to help contributors find the relevant routes.

## 3. Error Handling & Edge Cases

- Ports list validation rejects zeros, negatives, and values > 65535; duplicates are
  dropped in the web UI and preserved in Qt (launcher already handles fallback
  gracefully).
- Empty host defaults to `127.0.0.1` when posting; UI still shows blank so contributors
  know the JSON is using the launcher default.
- Failed requests raise toasts/status updates; both panels leave the last known state
  intact rather than clearing fields.
- Neither panel writes `public_base=""`; empty text resolves to JSON `null` so the
  launcher keeps treating it as absent.
- The web page disables controls until admin scope is confirmed (role `admin` or
  scopes containing `*`). Failed checks leave the bearer prompt highlighted.

## 4. Debug Hooks

- Toggle verbose logging (`COMFYVN_LOG_LEVEL=DEBUG`) to trace `_request_sync` calls from
  `ServerBridge`.
- Run the widget standalone:

  ```bash
  python - <<'PY'
  from PySide6.QtWidgets import QApplication
  from comfyvn.gui.settings.network_panel import NetworkPanel
  app = QApplication([])
  w = NetworkPanel()
  w.show()
  app.exec()
  PY
  ```

  Provide `COMFYVN_BASE_URL` if the default runtime authority is not reachable.

- Web panel stores the API base + Bearer token in `localStorage` for convenience; use
  an incognito window if you need to avoid caching between roles.
- Curl drills live in `docs/PORTS_ROLLOVER.md` and should be mirrored whenever the API
  contract changes.

## 5. Next Steps / Open Items

- [ ] Extend `tools/check_current_system.py` with `p5_settings_ports` to automate basic
      GET/SET/PROBE coverage.
- [ ] Consider persisting the most recent probe payload so the UI can re-run without
      re-reading fields (handy for automation QA).

Ping the Studio Desktop chat if additional hooks or signals are required by modders.
