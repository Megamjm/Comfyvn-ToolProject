# Export: Playable POV Forks — Parts A/B

## Overview

The Ren'Py export pipeline now detects narrative perspectives (POVs) declared on timelines, scene metadata, and node/dialogue blocks. Whenever at least two perspectives are encountered, the orchestrator:

- Generates dedicated entry labels per POV (`comfyvn_pov_<slug>`) while retaining the shared per-scene labels under `game/scenes/`.
- Produces a master `script.rpy` with an opt-in in-game **Switch POV** menu (`--pov-mode auto` + menu enabled by default) so testers can hop between branches.
- Stages per-POV forks under `build/renpy_game/forks/<slug>/` with their own `script.rpy` and `export_manifest.json`. Each fork is ready to publish independently (modders can tailor assets or splash screens per branch without touching the master tree).

## CLI additions

```
python scripts/export_renpy.py \
  --project demo \
  --timeline main \
  --pov-mode auto \
  --publish --publish-out exports/demo_master.zip
```

- `--pov-mode {auto,master,forks,both,disabled}` toggles fork generation and the master switch menu. `auto` builds both master + forks when multiple POVs surface. `master` keeps only the unified build; `forks` writes branch folders without adding the menu; `both` forces both outputs even if a single POV exists; `disabled` reverts to legacy behaviour.
- `--no-pov-switch` suppresses the in-game menu (useful when external launchers pick the branch).

Publishing (`--publish`) now emits:

- A master archive (`exports/demo_master.zip`) plus per-POV archives (`exports/demo_master__pov_alice.zip`, etc.).
- Matching `<stem>.manifest.json` files per archive containing the provenance payload, platform placeholders, and POV metadata (`active`, `slug`, `routes`).

The JSON summary printed by the CLI (and returned by the FastAPI mirror) includes:

- `pov.mode`, `pov.menu_enabled`, `pov.default`
- `pov.routes[]` with label and scene sequences
- `pov.forks{}` with relative paths for each staged fork
- `publish.fork_archives[]` with per-POV archive paths and checksums when `--publish` is supplied

## Manifest & debug hooks

`export_manifest.json` now ships a `pov` section:

```json
"pov": {
  "mode": "both",
  "menu_enabled": true,
  "default": "alice",
  "routes": [
    {
      "id": "alice",
      "name": "Alice POV",
      "slug": "alice",
      "entry_label": "comfyvn_pov_alice",
      "scene_labels": ["scene_intro", "scene_day1"],
      "scenes": ["scene_intro", "scene_day1"]
    }
  ],
  "forks": [
    {
      "id": "alice",
      "name": "Alice POV",
      "slug": "alice",
      "manifest": "forks/alice/export_manifest.json",
      "script": "forks/alice/game/script.rpy",
      "game_dir": "forks/alice/game"
    }
  ]
}
```

Modders can diff this block to identify branch-specific assets or automate build pipelines (e.g., patching menu art per POV). The FastAPI export preview route mirrors the structure for tooling.

## Contributor notes

- Tests: `tests/test_renpy_pov_export.py` exercises POV detection, timeline parsing, and script generation.
- Docs updated: `README.md` (CLI usage), `architecture.md` (export manifest contract), `architecture_updates.md` (status digest), and this stub for project history.
- Follow-up tasks (tracked in `CHAT_WORK_ORDERS.md`): surface POV fork selectors inside Studio’s Export view, add per-POV cover art slots, and expose manifest `pov` blocks through the REST export endpoints for automation bots.
