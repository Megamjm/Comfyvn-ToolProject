# Dev Notes — Extension Marketplace & Packaging

**Scope:** Mod Marketplace & Packaging (A/B) — manifest schema upgrade, packaging CLI, marketplace API surface, trust-level sandboxing.

## Module map

- `comfyvn/market/manifest.py` — Pydantic schema, permission registry, trust allowlists, helper `validate_manifest_payload`, and contribution summaries for marketplace listings.
- `comfyvn/market/packaging.py` — `build_extension_package()` + CLI (`bin/comfyvn_market_package.py`), deterministic ZIP assembly, manifest/package SHA-256 digests, signature verification.
- `comfyvn/market/service.py` — catalog ingestion, install/uninstall orchestration, `.market.json` sidecars, sandbox checks.
- `comfyvn/server/routes/market.py` — FastAPI router (`/api/market/{list,install,uninstall,health}`) gated by `enable_marketplace`, returns permission glossaries + modder hook catalogues.
- `comfyvn/server/modules/market_api.py` — Legacy router kept for backward compatibility during the transition (`/api/market/{catalog,installed,install,uninstall}`).
- `config/market_catalog.json` — default catalog entries; loader falls back to scanning `extensions/`.

## Feature flags

```jsonc
// config/comfyvn.json
"features": {
  "enable_marketplace": false,
  "enable_extension_market": false,           // legacy alias honoured during migration
  "enable_extension_market_uploads": false,
  …
}
```

`comfyvn/config/feature_flags.py` mirrors the defaults. `enable_marketplace` is the primary gate (the legacy `enable_extension_market` fallback remains for older configs). Flip the flags via Settings → Debug & Feature Flags or by editing the JSON and calling `feature_flags.refresh_cache()`.

## Packaging & API smoke test

```bash
EXT=extensions/sample_toolkit
bin/comfyvn_market_package.py "$EXT" --output tmp_pkg --force

# Install (feature flag must be true)
PKG="$(realpath tmp_pkg/sample_toolkit-*.cvnext)"
curl -X POST http://127.0.0.1:8000/api/market/install \
  -H 'Content-Type: application/json' \
  -d '{"package": "'"$PKG"'"}' | jq

# List catalog + installed summaries
curl -s http://127.0.0.1:8000/api/market/list | jq '{installed, permissions, hooks}'

# Health snapshot (trust counts + last error)
curl -s http://127.0.0.1:8000/api/market/health | jq

# Inspect sidecar
jq '.' extensions/sample_toolkit/.market.json

# Uninstall
curl -X POST http://127.0.0.1:8000/api/market/uninstall \
  -H 'Content-Type: application/json' \
  -d '{"id": "sample_toolkit"}' | jq
```

Logs land under `logs/server.log` with `event=market.install|market.uninstall`, `extension_id`, `trust`, and the recorded SHA-256 digest. Sidecars store the same metadata plus the install timestamp and package digest.

The packaging CLI prints both package and manifest SHA-256 digests. For verified entries, `trust.signature` must match `manifest_sha256`; mismatches cause the packager to abort.

## Sandbox & trust quick reference

| Trust | Global routes | Notes |
| --- | --- | --- |
| `unverified` | ❌ — forced under `/api/extensions/{id}` | Default; ideal for community bundles. |
| `verified` | ✅ — limited to `/api/modder/`, `/api/hooks/`, `/api/extensions/`, `/ws/modder` | For catalog-reviewed packages; subject to signature policy. |

Adjust the allowlist via JSON when onboarding additional prefixes.

## Modder hooks & debugging

- Manifests list expected hook topics in `hooks`. Pair this with `docs/dev_notes_modder_hooks.md` to document payloads (`on_scene_enter`, `on_asset_saved`, `on_asset_meta_updated`, etc.).
- The installer does **not** auto-subscribe — extensions must still call `comfyvn.core.modder_hooks.subscribe` inside their entry modules. Listing hook names in the manifest keeps catalog entries honest and documents intent.
- WebSocket testing:

  ```bash
  websocat ws://127.0.0.1:8000/api/modder/hooks/ws <<< '{"topics": ["on_scene_enter"]}'
  ```
- `/api/market/list` surfaces both the extension-declared hooks and the platform hook catalogue so dashboards can diff declared vs available topics.

## Debug & Verification snapshot

- Tests: `pytest tests/test_market_manifest.py tests/test_market_service.py tests/test_market_api.py`
- Remaining platform parity: run the packaging CLI and install flow on Windows; mock mode on CI to be added.
- Open questions: distribution mechanism for verified signature material, upload pipeline (flag stubbed).

## Related documents

- `README.md` — Marketplace overview + CLI pointers.
- `architecture.md` — Module bullet for marketplace service.
- `docs/MARKETPLACE.md` — single-source marketplace workflow (manifest schema snapshots, trust rules, curl recipes).
- `docs/extension_manifest_guide.md` — full schema, permission scopes, checklist.
- `docs/dev_notes_modder_hooks.md` — hook payloads for assets/scenarios/weather.
