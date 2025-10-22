# ComfyVN Security Hardening Notes

Updated: 2025-11-25 • Scope: Secrets store, audit streams, sandbox guard

Owner: Security & Platform (Chat P) — share feedback in `CHAT_WORK_ORDERS.md`

---

## 1. Encrypted Secrets Store

- Location: `comfyvn/security/secrets_store.py` manages the encrypted vault (`config/comfyvn.secrets.json`). Encryption uses Fernet (`cryptography`), keyed via `COMFYVN_SECRETS_KEY` or `config/comfyvn.secrets.key` (git-ignored).
- Bootstrap:
  ```bash
  python - <<'PY'
  from comfyvn.security.secrets_store import SecretStore

  store = SecretStore()
  key = store.rotate_key()  # generates on first run
  print('New key:', key)
  PY
  ```
  Persist the printed key to a secure secret manager and wipe the console history. Subsequent rotations accept a user-supplied base64 key via the CLI or the API (see §3).
- Runtime overrides never touch disk. Export `COMFYVN_SECRET_<PROVIDER>_<FIELD>` (e.g. `COMFYVN_SECRET_RUNPOD_API_KEY`) to merge values over the encrypted payload.
- Audit log: JSON lines append to `${COMFYVN_SECURITY_LOG_FILE:-logs/security.log}`. Each line contains `{event, timestamp, provider?, keys?, overrides?, host?, port?}`; parse with `jq` or ship to your SIEM.

## 2. Feature Flags & Config

- `enable_security_api` (default false) gates the `/api/security/*` router. Toggle via **Settings → Debug & Feature Flags** or edit `config/comfyvn.json → features` and call `feature_flags.refresh_cache()`.
- `enable_security_sandbox_guard` (default true) controls deny-by-default networking in the plugin sandbox. Set to `false` only when legacy, fully-open sandboxes are explicitly required.
- Environment helpers:
  - `SANDBOX_NETWORK_ALLOW` — comma-separated allowlist (`localhost:8080,api.example.com:443`).
  - `COMFYVN_SECURITY_LOG_FILE` — override audit log path per deployment.

## 3. Security API Endpoints

Available when `enable_security_api` is true. All responses omit secret values.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/security/secrets/providers` | Lists providers, stored keys, env overrides, and audit log path. |
| `POST` | `/api/security/secrets/rotate` | Re-encrypts the vault with a new key (optional `{"new_key": "..."}` body). Returns fingerprint + provider summaries. |
| `GET` | `/api/security/audit?limit=N` | Streams the latest audit lines (JSON). |
| `GET` | `/api/security/sandbox/defaults` | Shows current sandbox defaults (`SANDBOX_NETWORK`, allowlist). |
| `POST` | `/api/security/sandbox/check` | Validates whether a host:port pair would be allowed. Accepts `{ "host": "...", "port": 443, "allow": ["host:port", ...]? }`. |

### Curl quickstart

```bash
curl -s http://127.0.0.1:8000/api/security/secrets/providers | jq
curl -s -X POST http://127.0.0.1:8000/api/security/secrets/rotate \
  -H 'Content-Type: application/json' -d '{}' | jq '.fingerprint'
curl -s http://127.0.0.1:8000/api/security/audit?limit=10 | jq '.items[]'
curl -s -X POST http://127.0.0.1:8000/api/security/sandbox/check \
  -H 'Content-Type: application/json' \
  -d '{"host":"127.0.0.1","port":8080,"allow":["localhost:8080"]}' | jq
```

## 4. Sandbox Allowlist Behaviour

- `comfyvn/sandbox/runner.py` calls `apply_network_policy()` before executing plugin jobs. With the guard enabled, all network access is blocked unless:
  1. The job sets `"network": true`, **and**
  2. Hosts/ports appear in `network_allow` (plugin metadata) or the environment allowlist.
- Allowed patterns accept bare hosts, `host:port`, IPv6 literals (`[::1]:8000`), or URLs (`https://api.example.com:443`). Wildcards: use `*.example.com` to allow subdomains, `*` to allow everything (not recommended).
- Guard disabled (`enable_security_sandbox_guard=false`): sandbox reverts to legacy boolean behaviour (network on/off).

## 5. Modder Hooks & Observability

- `on_security_secret_read` — WS topic `security.secret_read`; indicates which provider was accessed and which keys were returned.
- `on_security_key_rotated` — WS topic `security.key_rotated`; surfaces the leading SHA256 fingerprint of the active key plus covered providers.
- `on_sandbox_network_blocked` — WS topic `security.sandbox_blocked`; captures rejected host/port pairs.
- Pair hooks with the audit log for provenance: hook payloads match the JSON lines dumped to `logs/security.log`, making it trivial to reconcile dashboards with persisted artefacts.

## 6. Testing & CI

- Unit coverage lives in:
  - `tests/test_security_secrets_store.py`
  - `tests/test_sandbox_network.py`
  - `tests/test_security_api.py`
- CI should tail `logs/security.log` (or the overridden path) post-test to ensure rotations and sandbox denials were recorded.
- When writing new plugin jobs, include a `network_allow` list in the sandbox metadata to keep test runs deterministic.
