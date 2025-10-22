# ComfyVN Marketplace — Manifests, Packaging, Trust & Sandbox

Updated: 2025-12-11 • Scope P4 Marketplace (Manifests, Packaging, Trust Levels, Install/Uninstall)

The marketplace stack covers four pillars:

1. **Manifest schema** — extension metadata, permissions, declared routes/events/UI slots, diagnostics, and trust envelopes (`comfyvn/market/manifest.py`).
2. **Packaging CLI** — deterministic `.cvnext` archives with optional signature verification (`comfyvn/market/packaging.py`, entrypoint `bin/comfyvn_market_package.py`).
3. **Trust & sandboxing** — verified vs unverified bundles, sandbox allowlists for global routes, lifecycle logging, and manifest digests.
4. **Server API** — `/api/market/{list,install,uninstall,health}` on FastAPI, guarded by feature flags and aware of modder/debug hooks.

This page distils the workflow for modders, integrators, and QA.

---

## Feature Flags

```jsonc
// config/comfyvn.json
"features": {
  "enable_marketplace": false,          // primary router gate
  "enable_extension_market": false,     // legacy alias honoured during migration
  "enable_extension_market_uploads": false
}
```

- Toggle via **Settings → Debug & Feature Flags** or edit the JSON then call `feature_flags.refresh_cache()`.
- `enable_marketplace` must be enabled for any `/api/market/*` route.
- Keep `enable_extension_market_uploads` false in production; enabling it allows install/uninstall requests.

---

## Manifest Essentials

Every marketplace extension ships a `manifest.json` (legacy `extension.json` still recognised). Key fields:

| Field | Notes |
| --- | --- |
| `manifest_version` | Defaults to `1.1`. |
| `id`, `name`, `version` | Required; `id` must match `^[a-z][a-z0-9_.-]{2,63}$`. |
| `author` / `authors[]` | `author` is normalised into `authors` (first entry becomes the primary author). |
| `summary` / `description` | `summary` falls back to `description` when omitted. |
| `permissions[]` | Declarative scopes; unknown entries raise `ManifestError`. |
| `routes[]`, `events[]`, `ui.panels[]` | Document exposed HTTP endpoints, bus events, and Studio UI slots. |
| `hooks[]` | Declared modder hook dependencies (`on_scene_enter`, `on_asset_meta_updated`, …). |
| `diagnostics` | Optional `log_topics`, `metrics`, `traces` published by the extension. |
| `trust` | `{level, signed_by?, signature?, signature_type?, reason?}`. |

### Permission registry

The packager validates scopes against `comfyvn.market.manifest.KNOWN_PERMISSION_SCOPES`:

| Scope | Purpose |
| --- | --- |
| `assets.read` | List/query asset registry metadata. |
| `assets.write` | Register or update asset metadata & sidecars. |
| `assets.events` | Subscribe to asset registry hook events. |
| `assets.debug` | Access asset debug metrics/traces/thumbnails. |
| `hooks.emit` | Emit modder hook events via the internal bus. |
| `hooks.listen` | Subscribe to modder hook events from the bus. |
| `extensions.lifecycle` | Listen for extension install/uninstall lifecycle updates. |
| `ui.panels` | Register Studio UI panels. |
| `api.global` | Expose HTTP routes outside the extension namespace. |
| `diagnostics.read` | Access debug tooling endpoints exposed by the extension. |
| `sandbox.fs.limited` | Request write access to additional filesystem roots. |

### Trust metadata & signatures

| Level | Global routes | Notes |
| --- | --- | --- |
| `unverified` | ❌ (forced under `/api/extensions/<id>`). | Default for community bundles. |
| `verified` | ✅ (allowlisted: `/api/modder/`, `/api/hooks/`, `/api/extensions/`, `/ws/modder`). | Requires review + signature. |

- `trust.signature` may contain either `sha256:<hex>` or raw SHA-256 hex/base64 digests. The packager recalculates the manifest digest after normalisation and aborts when values diverge.
- `trust.signature_type` is set to `sha256` when verification succeeds.
- Store provenance in `.market.json` sidecars; the loader reuses the manifest schema for runtime checks.

---

## Packaging CLI

```bash
# Package (normalises manifest, verifies allowlists + trust.signature)
bin/comfyvn_market_package.py extensions/sample_toolkit --output tmp_pkg --force

# Sample output
# [ok] created /abs/tmp_pkg/sample_toolkit-1.2.3.cvnext
#       files=5 bytes=24576 sha256=0f4c...
#       manifest id=sample.toolkit version=1.2.3
#       trust=unverified manifest_sha256=1c2d...
```

Highlights:

- Deterministic ZIP entries (fixed timestamps/permissions) for reproducible artefacts.
- Prints both package (`sha256`) and manifest (`manifest_sha256`) digests.
- Fails early when `trust.signature` is present but mismatched or encoded with an unsupported algorithm.
- `--trust verified` temporarily overrides `trust.level` (useful when staging catalog-signed bundles).
- `--allowlist <file>` merges extra prefixes into the global-route allowlist per trust level.

---

## API Quickstart (`/api/market/*`)

All endpoints expect `enable_marketplace=true`. Install/uninstall also require `enable_extension_market_uploads=true`.

```bash
# Catalog snapshot + installed state, permissions glossary, modder hook catalogue
curl -s http://127.0.0.1:8000/api/market/list | jq '{catalog, installed, permissions, hooks}'

# Install a package
curl -s -X POST http://127.0.0.1:8000/api/market/install \
  -H 'Content-Type: application/json' \
  -d '{"package": "/abs/path/sample_toolkit-1.2.3.cvnext"}' | jq '.installed.manifest_summary'

# Uninstall an extension
curl -s -X POST http://127.0.0.1:8000/api/market/uninstall \
  -H 'Content-Type: application/json' \
  -d '{"id": "sample.toolkit"}' | jq

# Health report (trust breakdown + last error message if any)
curl -s http://127.0.0.1:8000/api/market/health | jq
```

Response highlights:

- `list` returns:
  - `catalog[]` — entries with `manifest_summary` (authors, trust, capabilities) when a manifest is bundled.
  - `installed[]` — installed sidecars + manifest summaries and diagnostics.
  - `permissions[]` — ordered glossary derived from `KNOWN_PERMISSION_SCOPES`.
  - `hooks[]` — modder hook catalogue (`comfyvn.core.modder_hooks`).
- `install`/`uninstall` mirror structured logs (`event=market.install|market.uninstall`) with `extension_id`, trust, and package SHA-256.
- `health` reports `trust_breakdown`, counts, and `last_error` (action, message, timestamp).

---

## Sandbox Allowlist

- Unverified bundles are confined to `/api/extensions/<id>`; attempts to expose global routes raise `ManifestError` during packaging/installation.
- Verified bundles may expose endpoints under `/api/modder/`, `/api/hooks/`, `/api/extensions/`, and `/ws/modder`. Extend the allowlist via a JSON file passed to `--allowlist`.
- Archive extraction prevents directory traversal and strips platform-specific permissions.

---

## Debug & Verification Checklist

1. Package the extension (`bin/comfyvn_market_package.py`) and capture the reported `sha256` + `manifest_sha256`.
2. Ensure `trust.signature` equals `manifest_sha256` for verified bundles; otherwise leave the signature blank.
3. Install with `/api/market/install` and inspect:
   - HTTP payload (`installed.manifest_summary`) for permissions, routes, diagnostics.
   - `extensions/<id>/.market.json` sidecar for trust metadata and digests.
   - `logs/server.log` for `event=market.install`.
4. Hit `/api/market/list` and confirm:
   - Catalog entry shows declared permissions and hook dependencies.
   - Installed entry surfaces diagnostics (`log_topics`, `metrics`, `traces`).
   - Permission glossary lists the scopes the extension requested.
5. Smoke `/api/market/health` (trust counts, `last_error` is `null`).
6. Uninstall and verify:
   - `/api/market/uninstall` returns `{"ok": true}`.
   - Extension directory removed; sidecar deleted.
   - `logs/server.log` contains `event=market.uninstall`.

---

## Related References

- `docs/extension_manifest_guide.md` — exhaustive schema reference + examples.
- `docs/dev_notes_marketplace.md` — development notes, smoke tests, outstanding questions.
- `docs/dev_notes_modder_hooks.md` — hook payload shapes for assets, scenarios, weather, battle.
- `README.md` & `architecture.md` — high-level architecture bullets.
