# ComfyVN Extension API (v1.1.0)
Generated 2025-10-18 01:08:54

Extensions are discovered via two lightweight manifests inside each folder under `extensions/`:

- `extension.json` (new in v1.2) describes metadata – id, name, author, version, and whether the package is an official ComfyVN extension.
- `manifest.json` continues to declare individual menu hooks (`{"type": "menu_hook", ...}`) that the Studio injects at runtime.

## Manifest Example
```json
{
  "id": "example.plugin",
  "name": "Example Plugin",
  "version": "1.0.0",
  "official": false,
  "author": "You",
  "description": "Adds a sample action under Extensions → Imported Extensions."
}
```

Accompany the metadata with a `manifest.json` that declares menu hooks:

```json
{
  "type": "menu_hook",
  "menu": "Extensions",
  "label": "Example Action",
  "module": "extensions.example_plugin.entry",
  "callable": "run"
}
```

With both files present the Studio automatically shows the extension under **Extensions → Imported Extensions**, separates official ComfyVN packages from community ones, and exposes the descriptive metadata via the GUI.
