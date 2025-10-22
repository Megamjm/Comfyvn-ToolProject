ComfyVN Plugin Loader & Asset Hooks
===================================

This note walks mod authors and tooling contributors through the new manifest-driven
plugin loader, Studio panel slots, and the REST/debug hooks available for asset-centric
automation.

Manifest & Loader Basics
------------------------
- Place extensions under `extensions/<plugin_id>/`.
- Provide a `manifest.json` describing the plugin:

  ```json
  {
    "id": "sample-hello",
    "name": "Sample Hello",
    "version": "0.1.0",
    "description": "Adds a Hello panel and REST endpoint.",
    "enabled": true,
    "routes": [
      {
        "path": "/hello",
        "methods": ["GET"],
        "entry": "backend.py",
        "callable": "hello",
        "expose": "global",
        "summary": "Return a greeting payload."
      }
    ],
    "ui": {
      "panels": [
        {
          "slot": "studio.sidebar.right",
          "label": "Hello Panel",
          "path": "ui/panel.js"
        }
      ]
    }
  }
  ```

- Loader path: `comfyvn/plugins/loader.py`
  - Validates the manifest (jsonschema when available) and records errors/warnings.
  - Dynamically imports referenced `entry` modules and resolves callables.
  - Supports event hooks via the `events` array (`topic`, `entry`, `callable`, optional `once`).
  - Persists enable/disable state to `extensions/state.json`.

Management API
--------------
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/extensions` | GET | List all discovered plugins with metadata, warnings, routes, and panel descriptors. |
| `/api/extensions/reload` | POST | Re-scan the `extensions/` directory and remount routes/panels. |
| `/api/extensions/{plugin_id}/enable` | POST | Enable the plugin (validates manifest and registers event hooks). |
| `/api/extensions/{plugin_id}/disable` | POST | Disable the plugin and unregister event hooks. |
| `/api/extensions/{plugin_id}/ui/{asset_path}` | GET | Serve static UI assets from the plugin directory. |
| `/api/extensions/ui/panels` | GET | Return the list of enabled panel descriptors for Studio. |

Route scoping rules:
- Relative `path` values mount under `/api/extensions/{plugin_id}/`.
- Absolute `path` values (starting with `/`) mount exactly as declared.

Studio Panel Mounting
---------------------
- Studio fetches `/api/extensions/ui/panels` on load and injects the returned panel scripts.
- Each panel script receives a `panel` query parameter (`id`), and can claim its mount by calling `window.getExtensionPanelMount(panelId)`.
- Example (see `extensions/sample_hello/ui/panel.js`):

  ```js
  const params = new URL(import.meta.url).searchParams;
  const panelId = params.get("panel");

  const mount = window.getExtensionPanelMount(panelId);
  if (mount) {
    mount.innerHTML = "";
    const btn = document.createElement("button");
    btn.textContent = "Call /hello";
    btn.onclick = async () => {
      const res = await fetch("/hello");
      mount.textContent = JSON.stringify(await res.json(), null, 2);
    };
    mount.appendChild(btn);
  }
  ```

Debugging Tips
--------------
- Toggle verbose loader logs: set `COMFYVN_LOG_LEVEL=DEBUG` before launching the server.
- Inspect cached plugin state in `extensions/state.json`.
- Invalid manifests are listed in `/api/extensions` with `errors[]`; fix the manifest and call `/api/extensions/reload`.
- Event hooks: enable DEBUG logging on `comfyvn.core.event_bus` to trace subscribe/emit lifecycles.
- UI troubleshooting: open the browser console on the Studio page; panel scripts log mount failures if the slot is missing.

Asset Automation Hooks
----------------------
- Registry endpoints (FastAPI prefix `/assets`):
  - `GET /assets?type=<bucket>` — enumerate registered assets.
  - `GET /assets/{uid}` — fetch metadata, provenance, and sidecar pointers.
  - `GET /assets/{uid}/history` — inspect prior registrations or overrides.
  - `POST /assets/register` — register existing files; include `metadata` for provenance.
  - `POST /assets/upload` — upload new binaries; accepts multipart payloads.
- Preview downstream exports with `GET /api/export/renpy/preview` to surface unresolved references before publishing a mod pack.
- Combine registry API calls with extension routes to build custom dashboards or automation (e.g., surface missing sprites, bulk re-hash assets, or trigger external validation services).

Event Hooks for Asset Jobs
--------------------------
- Extensions can subscribe to internal events by declaring:

  ```json
  {
    "events": [
      {
        "topic": "asset.imported",
        "entry": "backend.py",
        "callable": "on_asset_import",
        "once": false
      }
    ]
  }
  ```

- The handler signature is `def on_asset_import(payload: dict) -> None`. Use these to mirror registry changes into external tooling (e.g., update a CDN or notification bot).
- Emit events from extensions using `comfyvn.core.event_bus.emit(topic, payload)`—ensure topics stay namespaced (`asset.*`, `extension.*`, etc.) to avoid collisions.

Further Reading
---------------
- `README.md` — high-level overview and quickstart.
- `ARCHITECTURE.md` — release goals, owners, and system-wide context.
- `docs/development_notes.md` — broader modder/debug tips including translation manager, savepoints, and export hooks.
