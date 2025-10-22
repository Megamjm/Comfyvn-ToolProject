# Dev Notes — Extension Marketplace & Packaging

**Scope:** Mod Marketplace & Packaging (A/B) — manifest schema upgrade, packaging CLI, marketplace API surface, trust-level sandboxing.

## Module map

- `comfyvn/market/manifest.py` — Pydantic schema, permission registry, trust allowlists, helper `validate_manifest_payload`.
- `comfyvn/market/packaging.py` — `build_extension_package()` + CLI (`bin/comfyvn_market_package.py`), deterministic ZIP assembly, SHA-256 digests.
- `comfyvn/market/service.py` — catalog ingestion, install/uninstall orchestration, `.market.json` sidecars, sandbox checks.
- `comfyvn/server/modules/market_api.py` — FastAPI router (`/api/market/{catalog,installed,install,uninstall}`) gated by `feature_flags.is_enabled("enable_extension_market")`.
- `config/market_catalog.json` — default catalog entries; loader falls back to scanning `extensions/`.

## Feature flags

```jsonc
// config/comfyvn.json
"features": {
  "enable_extension_market": false,
  "enable_extension_market_uploads": false,
  …
}
```

`comfyvn/config/feature_flags.py` mirrors the defaults. Flip the flags via Settings → Debug & Feature Flags or by editing the JSON and calling `feature_flags.refresh_cache()`.

## Packaging & install smoke test

```bash
EXT=extensions/sample_toolkit
bin/comfyvn_market_package.py "$EXT" --output tmp_pkg --force

# Install (feature flag must be true)
curl -X POST http://127.0.0.1:8000/api/market/install \
  -H 'Content-Type: application/json' \
  -d '{"package": "'"$(realpath tmp_pkg/sample_toolkit-*.cvnext)"'"}' | jq

# Inspect sidecar
jq '.' extensions/sample_toolkit/.market.json

# Uninstall
curl -X POST http://127.0.0.1:8000/api/market/uninstall \
  -H 'Content-Type: application/json' \
  -d '{"id": "sample_toolkit"}' | jq
```

Logs land under `logs/server.log` with `event=market.install|market.uninstall`, `extension_id`, `trust`, and the recorded SHA-256 digest. Sidecars store the same metadata plus the install timestamp.

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

## Debug & Verification snapshot

- Tests: `pytest tests/test_market_manifest.py tests/test_market_service.py tests/test_market_api.py`
- Remaining platform parity: run the packaging CLI and install flow on Windows; mock mode on CI to be added.
- Open questions: signature format for verified packages, upload pipeline (flag stubbed).

## Related documents

- `README.md` — Marketplace overview + CLI pointers.
- `architecture.md` — Module bullet for marketplace service.
- `docs/extension_manifest_guide.md` — full schema, permission scopes, checklist.
- `docs/dev_notes_modder_hooks.md` — hook payloads for assets/scenarios/weather.
