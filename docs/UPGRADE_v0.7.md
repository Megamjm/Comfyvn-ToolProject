# ComfyVN v0.7 Upgrade Notes

Updated: 2025-10-26

## Release highlights
- Studio shell consolidated under `gui/main_window` with dockable Scenes, Characters, Timeline, Import, Compute, Audio, Advisory, and Logs views.
- Render Grid orchestration ships with curated provider templates, sequential fallback scheduling, and `/render/{targets,health,enqueue}` APIs.
- Roleplay + VN package importers hardened (job dashboards, provenance stamping, advisory scans); Manga importer parity scheduled as final blocker.
- Audio & policy systems now expose `/api/tts/synthesize`, `/api/music/remix`, policy gate + advisory scan workflows, all backed by cached provenance sidecars.
- Runtime storage overhaul moves mutable data to OS-specific directories via `comfyvn.config.runtime_paths` with optional overrides (`COMFYVN_RUNTIME_ROOT`, `COMFYVN_LOG_DIR`, etc.).
- Doctor v0.7 (`tools/doctor_v07.py`) validates runtime paths, dependency footprint, and render grid prerequisites.

## Pre-flight checklist
1. Ensure you are on Python 3.10+ with virtualenv/conda ready.
2. Back up any user runtime data (`~/.local/share/ComfyVN Studio`, `%LOCALAPPDATA%\ComfyVN Studio`, etc.).
3. `git fetch origin --tags` so the `v0.7.0-studio` tag is available.
4. If upgrading from <= v0.6, note any local overrides in `data/settings/config.json`; runtime storage now prefers platform directories.

## Upgrade steps
1. Checkout the release tag: `git checkout v0.7.0-studio`.
2. Install dependencies: `pip install -r requirements.txt` (use `requirements-dev.txt` if you maintain developer tooling).
3. Apply schema baseline (idempotent): `python tools/apply_migrations.py --verbose`.
4. Regenerate provider locks if you use custom render pipelines: `python tools/lock_nodes.py`.
5. Run Doctor: `python tools/doctor_v07.py` — resolves runtime paths, validates dependencies, and surfaces missing render grid prerequisites.
6. Smoke test backend: `python run_comfyvn.py --server-only` then `curl http://127.0.0.1:8000/health`.
7. Launch Studio (`python run_comfyvn.py`) to let the GUI rebuild settings caches and verify port alignment.

## Post-upgrade validation
- Confirm new runtime directories exist under the OS user data root with symlinks back into the repo (`logs/`, `data/settings/` shims).
- Run roleplay and VN import smokes; check advisory + provenance entries in the GUI dashboards.
- Trigger TTS + music remix to confirm cache + provenance sidecars appear.
- Exercise render grid panel (when enabled) to confirm providers register and health checks succeed.
- Run `pytest -q tests/test_launcher_smoke.py` (optional) to validate launcher/server alignment.

## Known caveats / follow-ups
- Studio asset inspector UX is landing post-tag; assets panel currently lists entries without inspector popovers. Track progress in `ARCHITECTURE.md` Phase 4 Part D.
- Audio automation still requires final ComfyUI linkage for provenance sidecars; without ComfyUI configured, the system falls back to deterministic stubs.
- Manga importer parity (panel segmentation → VN timeline) is the last importer feature to finalize; GUI dashboard currently displays placeholder status entries.
- Export orchestrator (Ren’Py + Studio bundle) remains in progress; only per-scene stubs are written today.
- Advisory auto-remediation (replace/remove/waiver) emits logs but not structured events yet; expect expanded GUI wiring after release.
