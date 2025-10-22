# Ports & Base URL Roll-over

Updated: 2025-10-21  
Owner: Studio Desktop (Settings)  
Scope: Launcher host binding, ordered port probing, REST access, runtime ledger.

---

## 1. Intent & Summary

All launch flows (desktop GUI, headless `run_comfyvn.py`, diagnostics scripts) now
resolve server host/port details from a single source: `config/comfyvn.json → server`.
The server binds to the first free port in the configured order (default
`[8001, 8000]`) and writes the result to `.runtime/last_server.json` for other tools.
Modders and automation runners can adjust bindings through a small REST surface under
`/api/settings/ports`.

For browser administration, the stack now ships `/studio/settings/network.html` — an
admin-only page that wraps the same API endpoints, mirrors probe output (“would bind
to” summary), and publishes ready-to-share curl drills for contributors.

Key guarantees:

- Default bind host matches `config/comfyvn.json: server.host` (ships as `127.0.0.1`).
- Port roll-over preserves list order; we never auto-increment outside the list unless
  every candidate is busy.
- `.runtime/last_server.json` mirrors the persisted config and records the active port
  plus a hash stamp for cache-busting.

---

## 2. Source of Truth Layout

`config/comfyvn.json`

```jsonc
{
  "server": {
    "host": "127.0.0.1",
    "ports": [8001, 8000],
    "public_base": null
  }
}
```

- `host`: interface bound by uvicorn (`127.0.0.1`, `0.0.0.0`, LAN IP, etc.).
- `ports`: ordered preference list; launcher probes each until it finds a free one.
- `public_base`: optional externally reachable origin (ex: `https://studio.example.com`).

Legacy fields in `config/settings/config.json` are ignored for binding and will be
removed in a later cleanup.

---

## 3. Environment Overrides & Precedence

Environment variables override persisted values before the launcher starts:

| Variable | Effect |
|----------|--------|
| `COMFYVN_HOST` | Overrides `server.host`. |
| `COMFYVN_PORTS` | Comma/space-separated list that replaces the roll-over order. |
| `COMFYVN_BASE` | Sets `server.public_base` and seeds the runtime ledger. |

Backward-compatible knobs (`COMFYVN_SERVER_HOST`, `COMFYVN_SERVER_PORT`,
`COMFYVN_BASE_URL`) still work; when present they are inserted at the front of the
roll-over list so existing automations do not break.

Precedence:

1. CLI flags (`--server-host` / `--host`, `--server-port` / `--port`).
2. Environment overrides (table above).
3. `config/comfyvn.json`.
4. Hard coded fallback (`host=127.0.0.1`, `ports=[8001, 8000]`).

---

## 4. Runtime Ledger

When the launcher resolves a binding it writes `.runtime/last_server.json`:

```jsonc
{
  "config": {
    "host": "127.0.0.1",
    "ports": [8001, 8000],
    "public_base": null
  },
  "active": 8001,
  "base_url": "http://127.0.0.1:8001",
  "stamp": "9f4bf4c8…",
  "updated": 1732137600.123
}
```

- `config`: resolved configuration after env/CLI overrides.
- `active`: port chosen during roll-over (can be `null` when only persisting config).
- `base_url`: effective base (either derived from host/port or `public_base`).
- `stamp`: SHA-256 hash of the config block; consumers can short-circuit if unchanged.

The server process refreshes this ledger once it boots so helper scripts always see
the runtime port, even after a background restart.

---

## 5. Launcher Behaviour (`run_comfyvn.py`)

- `--server-host` and `--host` are interchangeable, same for `--server-port` / `--port`.
- When no port is supplied, the launcher walks the configured list in order and logs
  the first free entry. If every candidate is busy we fall back to sequential search.
- Binding state is broadcast through `COMFYVN_SERVER_BASE`, `COMFYVN_SERVER_HOST`,
  `COMFYVN_SERVER_PORT`, and the runtime ledger.
- `public_base` (when present) becomes the GUI target URL even if the server binds to
  `127.0.0.1`.

---

## 6. REST API Surface (`/api/settings/ports`)

All payloads and responses are JSON.

### GET `/get`

Returns the current configuration plus the hash stamp.

```bash
curl -s http://127.0.0.1:8001/api/settings/ports/get \
  -H "Authorization: Bearer ${API_TOKEN}" | jq
```

Sample response:

```json
{
  "host": "127.0.0.1",
  "ports": [8001, 8000],
  "public_base": null,
  "stamp": "9f4bf4c8fc1e..."
}
```

### POST `/set`

Persists the supplied host/ports/public_base to `config/comfyvn.json`, refreshes the
runtime ledger, and echoes the new state.

```bash
curl -s -X POST http://127.0.0.1:8001/api/settings/ports/set \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -d '{"host":"0.0.0.0","ports":[9001,9002],"public_base":null}' | jq
```

Response mirrors `/get` with an updated stamp. A restart is required for the running
server to use the new binding.

### POST `/probe`

Walks the candidate list (defaults to the persisted config) and performs `GET /health`
against each endpoint. The first response with HTTP < 500 is considered healthy.

```bash
curl -s -X POST http://127.0.0.1:8001/api/settings/ports/probe \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -d '{"ports":[8001,8000,9001]}' | jq
```

Possible response:

```json
{
  "ok": true,
  "host": "127.0.0.1",
  "port": 8001,
  "base_url": "http://127.0.0.1:8001",
  "status_code": 200,
  "attempts": [
    {"url": "http://127.0.0.1:8001/health", "status_code": 200},
    {"url": "http://127.0.0.1:8000/health", "status_code": 503}
  ],
  "stamp": "9f4bf4c8fc1e..."
}
```

Failures return `ok=false`, leave `port` null, and include `error` strings for each
attempt.

---

## 7. Debug Notes & Modder Hooks

- Swap hosts/ports through the API without touching disk; `.runtime/last_server.json`
  updates immediately so local tooling can pick up the change.
- Modders can script port detection by calling `/probe` before starting custom assets
  or bridge services.
- To diagnose binding conflicts, inspect the `attempts` array for connection errors
  (socket refusal, SSL mismatch, etc.).
- GUI panels should re-fetch `/get` after saving to stay in sync with other open
  windows.
- The web panel stores base URL + token locally, verifies admin scope against
  `/api/auth/me`, and disables controls when scopes fall short of admin privileges.

Ping Studio Desktop in `#docs` if additional fields are required.
