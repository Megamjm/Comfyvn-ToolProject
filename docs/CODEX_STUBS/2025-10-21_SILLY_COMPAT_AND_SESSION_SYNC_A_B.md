# SillyTavern Compat & Session Sync — Parts A/B  
Updated 2025-10-31 • Owner: ST Bridge + Persona Chats

## Outcomes
- **Health + sync parity** — `collect_extension_status` now inspects both the bundled
  ComfyVN extension and the comfyvn-data-exporter plugin, exposing `plugin_needs_sync`,
  destination package manifests, and an `overall_needs_sync` bit. `/st/health` returns
  the merged view together with ping timings, `alerts`, and the new
  `versions.{extension,plugin}` summaries so Studio panels and CLI scripts can warn on
  mismatches.
- **Session context bridge** — added `comfyvn/bridge/st_bridge/session_sync.py` and
  `POST /st/session/sync`. The helper compacts scene ID, POV, variables, and the most
  recent transcript turns (trimmed via `limit_messages`) before posting to
  comfyvn-data-exporter. Responses include `panel_reply` + `reply_text` so VN Chat can
  render the assistant reply without additional mapping. Default timeout: 2 s; dry-run
  mode avoids external calls during CI.
- **Docs + modder hooks** — README, architecture, dev-notes, and this stub call out the
  new payloads, version alerts, and environment overrides (`COMFYVN_ST_EXTENSIONS_DIR`,
  `SILLYTAVERN_PATH`, `COMFYVN_LOG_LEVEL=DEBUG`). Added CLI snippets for each endpoint.

## API Cheatsheet
- `GET /st/health`
  - Keys: `status`, `alerts[]`, `versions.extension`, `versions.plugin`,
    `extension.plugin_needs_sync`, `paths.watch_paths[]`.
  - Alerts raised for manifest mismatches (`extension_mismatch`, `plugin_missing`, …).
  - Use alongside `/st/paths` to resolve file-system probes when wiring installers.
- `POST /st/extension/sync`
  - Accepts `{"dry_run": true,"source": "...","destination": "..."}`.
  - Response contains copy stats and the canonical path resolution chain for logging.
- `POST /st/session/sync`
  - Request:
    ```jsonc
    {
      "scene_id": "chapter_03",
      "pov": "narrator",
      "variables": {"affinity": 0.42},
      "messages": [
        {"role": "narrator", "content": "Evening settles over the city."},
        {"role": "alice", "content": "Did you find the clue?"}
      ],
      "limit_messages": 40
    }
    ```
  - Response: `{ok, latency_ms, reply, panel_reply, reply_text, context, message_count,
    endpoint, scene_source}`. `panel_reply` is already normalised for the VN Chat panel.
  - Set `"dry_run": true` during CLI/local testing; the endpoint mirrors the actual body
    under `context` for debugging.

## Debug & Automation Notes
- Watch `alerts` + `plugin_needs_sync` from `/st/health` to fail fast when the bundled
  plugin lags behind the installed copy.
- `collect_extension_status.watch_paths` now includes the plugin package JSON, making it
  straightforward to attach `inotify`/FsNotify watchers when modders mirror assets.
- Session payloads record `message_count` and `timeout` in the response so automation can
  assert budgets; latency stays under 2 s on the mock transport.
- Environment overrides remain unchanged (`COMFYVN_ST_EXTENSIONS_DIR`, `SILLYTAVERN_PATH`);
  set `COMFYVN_LOG_LEVEL=DEBUG` to stream per-file copy logs during syncs.

## Follow-ups
- Align comfyvn-data-exporter (ST plugin) to expose a `/session/sync` handler returning
  structured `{role, content, emotion?}` payloads so the reply normaliser preserves
  metadata beyond free-form text.
- Add FastAPI tests covering the new route once a mock transport module lands; ensure
  mismatch alerts surface in Studio notifications.
- Surface session sync telemetry (latency, message_count) inside Studio’s VN Chat dock
  for live debugging.
