# ComfyVN Extension Manifest & Marketplace Guide

This guide documents the manifest schema consumed by the Studio extension loader, the new packaging CLI, and the marketplace APIs introduced in the Mod Marketplace & Packaging (A/B) work order. It supersedes the legacy `extension.json` format—existing plugins should migrate to the structure described below so they can be installed, sandboxed, and audited through the marketplace tooling.

## Manifest (`manifest.json`)

Every extension directory **must** ship a `manifest.json` at its root. The loader and packager validate the payload with `comfyvn.market.manifest.ExtensionManifest`:

```jsonc
{
  "manifest_version": "1.1",
  "id": "demo.toolkit",
  "name": "Demo Toolkit",
  "version": "0.1.0",
  "summary": "Utility helpers for inspecting assets during scenario runs.",
  "description": "Registers REST/WS hooks, a Studio panel, and modder hook listeners.",
  "homepage": "https://example.com/toolkit",
  "authors": ["ComfyVN Contributors"],
  "license": "MIT",
  "permissions": [
    {"scope": "assets.read", "description": "List registered assets"},
    {"scope": "hooks.listen", "description": "Subscribe to modder hook topics"},
    {"scope": "ui.panels"}
  ],
  "trust": {"level": "unverified"},
  "routes": [
    {
      "path": "/assets",
      "entry": "handlers.py",
      "callable": "handlers.list_assets",
      "methods": ["GET"],
      "summary": "Enumerate assets registered in the current workspace",
      "expose": "extension"
    }
  ],
  "events": [
    {
      "topic": "on_scene_enter",
      "entry": "handlers.py",
      "callable": "handlers.on_scene",
      "once": false
    }
  ],
  "ui": {
      "panels": [
        {"slot": "tools", "label": "Demo Toolkit", "path": "ui/index.html", "icon": "icons/toolkit.svg"}
      ]
  },
  "hooks": ["on_scene_enter", "on_asset_saved"],
  "diagnostics": {
    "log_topics": ["demo.toolkit"],
    "metrics": ["demo_toolkit_assets"]
  }
}
```

### Permission scopes

Manifest permissions request access to specific systems. Known scopes (enforced by `ExtensionManifest`) are:

| Scope | Grants |
| --- | --- |
| `assets.read` | Read asset registry metadata through `/api/assets/*`. |
| `assets.write` | Modify assets or sidecars. Requires explicit review. |
| `hooks.listen` | Subscribe to the Modder Hook Bus (`/api/modder/hooks`, WebSocket topics). |
| `hooks.emit` | Emit custom hook payloads back onto the bus. |
| `ui.panels` | Register Studio panels via `ui.panels`. |
| `api.global` | Request global HTTP routes (verified extensions only; see sandbox notes). |
| `sandbox.fs.limited` | Extend sandbox write access beyond the default allowlist. |

Unrecognised scopes raise a manifest error during packaging/installation. Use the `description` field to justify why a permission is required; Studio surfaces the text in the catalog entry/tooltips.

### Trust levels & sandboxing

`trust.level` drives the install sandbox:

- `unverified` (default): routes are forced under `/api/extensions/{id}`; global routes are rejected. Installations run in the default sandbox profile.
- `verified`: routes may target allowlisted prefixes (`/api/modder/`, `/api/hooks/`, `/api/extensions/`, `/ws/modder`). Use this level only for extensions shipped in the official catalog or accompanied by signing metadata.

The installer persists trust metadata to `extensions/<id>/.market.json` alongside the package digest so deployments can audit provenance.

## Packaging workflow

Use the CLI wrapper `bin/comfyvn_market_package.py` (or `python -m comfyvn.market.packaging`) to build archives:

```bash
bin/comfyvn_market_package.py path/to/extension \
  --trust verified \
  --output dist/
# => dist/demo.toolkit-0.1.0.cvnext (SHA-256 digest printed on completion)
```

The packager

1. Validates the manifest against the schema and trust allowlists.
2. Normalises the manifest (`manifest.json` is rewritten inside the archive).
3. Zips the extension into `<id>-<version>.cvnext`, ignoring `__pycache__`, `.pyc`, logs, etc.
4. Prints the SHA-256 so catalogs or CI can record provenance.

Archives failing validation (e.g., unverified package exposing `/api/system/*`) abort with `ManifestError`.

## Marketplace APIs & feature flags

- Feature flags: `enable_extension_market` (enables `/api/market/*`), `enable_extension_market_uploads` (reserved for future upload flows). Both default to `false` in `config/comfyvn.json` and `comfyvn.config.feature_flags.FEATURE_DEFAULTS`.
- Catalog ingestion: `comfyvn.market.service.MarketCatalog` loads `config/market_catalog.json` (fallback: scans local `extensions/`). Entries expose id, summary, permissions, tags, trust level, and optional package hints.
- Installer: `comfyvn.market.service.ExtensionMarket.install()` validates archives, extracts to `/extensions/<id>`, writes `.market.json`, and logs `event=market.install` with `{extension_id, trust, sha256}` to `logs/server.log`.
- REST routes (`comfyvn/server/modules/market_api.py`):
  - `GET /api/market/catalog` → catalog snapshot.
  - `GET /api/market/installed` → `.market.json` sidecars.
  - `POST /api/market/install` → `{"package": "/absolute/path/to/pkg.cvnext", "trust": "verified"?}`.
  - `POST /api/market/uninstall` → `{"id": "demo.toolkit"}`.

## Debug & Verification Checklist

Embed this checklist in PR summaries when changing marketplace or packaging code. The items below correspond to the Mod Marketplace & Packaging (A/B) deliverables.

- [x] **Docs updated** — README, architecture.md, CHANGELOG, and this guide cover schema, CLI, endpoints, and sandbox rules.
- [x] **Feature flags** — `enable_extension_market` / `enable_extension_market_uploads` live in `config/comfyvn.json`, defaulting to `false`, and are mirrored in `comfyvn/config/feature_flags.py`.
- [x] **API surfaces** — `/api/market/{catalog,installed,install,uninstall}` documented with sample JSON payloads above.
- [x] **Modder hooks** — manifests declare `hooks`, and existing hook docs (`docs/dev_notes_modder_hooks.md`) explain payloads (`on_scene_enter`, `on_asset_saved`, etc.).
- [x] **Logs** — install/uninstall flows log structured entries to `logs/server.log`; CLI prints SHA-256 digests.
- [x] **Provenance** — `.market.json` sidecars capture `{id, version, trust, package, sha256, installed_at}`; packager prints digests.
- [x] **Determinism** — packager sorts files, rewrites manifest, and uses ZIP_DEFLATED ensuring repeatable archives for identical sources.
- [ ] **Windows/Linux** — smoke on both platforms (or CI mock) pending dedicated runner; see `docs/dev_notes_marketplace.md` for platform notes.
- [x] **Security** — sandbox deny-list prevents unverified bundles from exposing global routes; trust allowlists configurable via JSON.
- [x] **Dry-run mode** — CLI prints manifest + digest without side effects; install handler validates before extraction and aborts on failure.

## Additional references

- `comfyvn/market/manifest.py` — Pydantic models, permission registry, and allowlist logic.
- `comfyvn/market/packaging.py` — CLI implementation (`build_extension_package`, SHA-256 helper).
- `comfyvn/market/service.py` — catalog loader, installer, sidecar persistence.
- `docs/dev_notes_modder_hooks.md` — payloads for `on_scene_enter`, `on_asset_saved`, `on_asset_meta_updated`, etc. Declare the hook names in the manifest `hooks` list for clarity.
- `docs/dev_notes_marketplace.md` — development notes, platform quirks, and smoke-test commands for marketplace flows.
