## ComfyVN Studio Phase 0 Bootstrap

These scaffolding utilities prepare the repository for the incoming Studio shell redesign.

### 1. Rebuild database and folders

```bash
python setup/apply_phase06_rebuild.py --recreate-all
```

This initialises placeholder directories under `data/`, `cache/`, and `logs/` for backwards compatibility. At runtime, mutable data is redirected to the platform-specific locations exposed by `comfyvn.config.runtime_paths`, while the setup script ensures the legacy symlinks or empty folders exist for tooling that still references the repo paths. The SQLite database at `comfyvn/data/comfyvn.db` contains the required v0.6 tables (all tagged with `project_id`).

### 2. Registry access

The new package `comfyvn.studio.core` exposes lightweight registry facades:

- `SceneRegistry`
- `CharacterRegistry`
- `AssetRegistry`
- `WorldRegistry`

Each registry derives from `BaseRegistry` and targets the shared SQLite store.  The registries default to the `"default"` project but accept a `project_id` override.

```python
from comfyvn.studio.core import SceneRegistry

scenes = SceneRegistry()
for row in scenes.list_scenes():
    print(row["title"])
```

### 3. Sanity probe

For quick checks after running the rebuild, execute:

```bash
python tools/status_probe.py
```

The script validates the presence of key files and the studio core package, and reminds you to verify the `/system/metrics` endpoint once the server is running.
