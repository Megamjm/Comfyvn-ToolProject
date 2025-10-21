# ComfyVN Studio Extension Manifest Guide

This document explains how GUI extensions are discovered, versioned, and loaded by the Studio shell. Starting with Phase 4 updates (2025-10-22) extension metadata is **mandatory** for packaged plugins so the launcher can negotiate compatibility and avoid hard crashes when requirements are not met.

## Manifest (`extension.json`)

Every extension folder under `extensions/` must ship an `extension.json` file with at least the following keys:

```jsonc
{
  "id": "demo_tool",                // unique slug
  "name": "Demo Tool",             // human-friendly label
  "version": "0.1.0",              // PEP 440 version string
  "entrypoint": "extension.py",    // Python file relative to the extension folder
  "requires": {
    "comfyvn": ">=1.0.0"            // semantic version specifier (uses packaging.SpecifierSet)
  },
  "api_version": "1"               // optional studio API level for future gating
}
```

Additional fields (`description`, `author`, `homepage`, `official`) are surfaced in the Extensions menu but do not influence compatibility.

### Version constraints

- `requires.comfyvn` accepts any PEP 440-compatible expression (e.g. `">=1.0,<2.0"`). The current Studio version is derived from `comfyvn.__version__`. Incompatible specs are reported to the user and the extension is skipped.
- Legacy `min_app_version` / `max_app_version` keys are still honoured and merged into the specifier set.
- A malformed specifier marks the extension as incompatible, preventing accidental partial loads.

### Entry point semantics

The loader imports the entrypoint file and expects a top-level `register` callable:

```python
from comfyvn.core.menu_runtime_bridge import MenuRegistry

def register(registry: MenuRegistry) -> None:
    registry.add("Demo Action", section="Tools", callback=_run)

def _run(window) -> None:
    ...  # window is the active MainWindow instance
```

`MenuRegistry.add` accepts either:

- `handler="method_name"` to invoke a method defined on `MainWindow`, preserving the legacy behaviour, **or**
- `callback=callable` to run an arbitrary function that receives the current `MainWindow` instance.

Use callbacks for self-contained extensions that do not need to patch the core window class.

### Emitting warnings

Extensions can surface contextual warnings via the shared notifier:

```python
from comfyvn.core.notifier import notifier

notifier.toast("warn", "Demo extension initialised without full support")
```

Warnings appear in the Studio toast overlay and are recorded in the warning log accessible through `/api/system/warnings`.

## Diagnostic flow

- Discovery metadata is exposed via `MainWindow._extension_metadata`; incompatible entries appear under the Extensions menu with a warning icon and disabled state.
- The backend captures Python `logging.WARNING+` records through `comfyvn.core.warning_bus.warning_bus`, surfaces them at `/api/system/warnings`, and the GUI renders new entries as toasts.
- Set `COMFYVN_RUNTIME_ROOT` during development to isolate log/config/cache directories while testing extensions.

## Example project layout

```
extensions/
  demo_tool/
    extension.json
    extension.py
    README.md (optional)
  my_extension/
    extension.json
    extension.py
    resources/
      icon.png
```

Packaging tools (e.g. zip bundles) should retain the manifest at the root of the extension folder so `comfyvn.core.extensions_discovery.load_extension_metadata` can enforce compatibility before attempting imports.
