# SillyTavern Bridge Configuration

The SillyTavern bridge exposes live import/export endpoints that let ComfyVN
ingest chats, personas, and lore while synchronising bridge assets. This guide
covers the refreshed host/port controls, consent requirements, and fallback
flows for offline modding.

## Configuring the Bridge

1. Open **Settings → Studio Basics**.
2. Enter the **SillyTavern Host** and **SillyTavern Port**. The host field
   accepts either raw hostnames (`127.0.0.1`) or full URLs
   (`https://st.example.dev`).  
   The base URL used by the bridge is derived from these fields.
3. Adjust the **SillyTavern Plugin Base** if you mounted the
   `comfyvn-data-exporter` extension under a custom prefix. The default is
   `/api/plugins/comfyvn-data-exporter`.
4. Toggle the **Enable SillyTavern bridge integration** flag inside
   **Settings → Debug & Feature Flags**. The bridge remains dormant until this
   feature flag is enabled.

All values are persisted in `config/comfyvn.json` under
`integrations.sillytavern`. The `/st/health` endpoint and the GUI health probe
surface the active configuration, including whether an auth token was detected.

## Consent & Liability

Ensure contributors have read `docs/LEGAL_LIABILITY.md` and have acknowledged
the `/api/policy/ack` waiver before syncing user-generated content. The bridge
flags missing acknowledgement as `alerts: ["policy_unacknowledged"]` in the
health payload to help operators enforce compliance.

## API Surface

| Endpoint | Purpose | Notes |
| -------- | ------- | ----- |
| `GET /st/health` | Combined health report covering connectivity, plugin version parity, and token checks. | Accepts optional `base_url` and `plugin_base` overrides. |
| `POST /st/import` | Imports SillyTavern exports (personas, worlds, chats). | Submit payloads with `{ "type": "...", "data": [...] }`. |
| `POST /st/extension/sync` | Copies the bundled ComfyVN extension into the detected SillyTavern install. | Supports `{ "dry_run": true }` to preview actions. |
| `POST /st/session/sync` | Pushes active VN state to the bridge and pulls the live reply. | Respects the configured host/port/base URL combination. |

All utilities used by the GUI (`Tools → Import` submenu, Import Manager presets,
and the Help menu launchers) call these endpoints and therefore inherit the host
and port defined in settings.

## Offline Fallback

When a live SillyTavern instance is unavailable you can still queue imports by
selecting **Tools → Import → From File…** and providing JSON exports. The GUI
asks how to process list payloads and replays them through the same REST
pipeline, making it easy for modders to stage assets before reconnecting to a
bridge.
