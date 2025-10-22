# Remote Installer Orchestrator — 2025-10-21

## Overview
- Expose a remote installer orchestrator that plans SSH-friendly provisioning steps for ComfyUI, SillyTavern, LM Studio, and Ollama.
- Surface a module registry so GUIs/automation can discover what installers exist, the commands they expect to run, and the configuration assets that should be mirrored to each host.
- `/api/remote/install` records the orchestration run (logs + status file) and is idempotent: once a module is marked installed for a host the next call becomes a no-op while still returning the plan metadata.

## References
- `comfyvn/remote/installer.py` — module registry, plan builder, log/status helpers.
- `comfyvn/server/routes/remote_orchestrator.py` — FastAPI wiring for `/api/remote/{modules,install}`.
- Status root: `data/remote/install/<host>.json` (override with `COMFYVN_REMOTE_INSTALL_STATUS_ROOT`).
- Log root: `logs/remote/install/<host>.log` (override with `COMFYVN_REMOTE_INSTALL_LOG_ROOT`).

## A) SSH Provisioning Flow
- Installer plan entries enumerate shell commands (apt/git/npm/curl) that a remote executor should replay via SSH. Each command keeps human-readable descriptions so ops runbooks can be generated directly from the log.
- Config sync steps describe host paths to copy local assets (e.g. ComfyVN SillyTavern extension, shared settings JSON). When the source asset is absent the orchestrator logs the miss but still marks the step optional where flagged.
- `/api/remote/install` appends every step to the per-host log and updates the status JSON with timestamps so the orchestration can be audited later or resumed by dispatch tooling.
- Dry runs (`{"dry_run": true}`) expose the plan without touching the status file. Use this path for previews in the GUI before triggering the actual execution.

## B) Module Registry Expectations
- Registry exposes modules with `id`, human name, tags (`ssh`, `llm`, `workflow`, etc.), install commands, and config sync descriptors. Consumers should call `GET /api/remote/modules` to hydrate UI dropdowns or CLI autocompletion.
- Modules currently shipped:
  - `comfyui` — apt/python/git bootstrap + virtualenv setup.
  - `sillytavern` — git clone + `npm install`, optional sync of bundled SillyTavern extension.
  - `lmstudio` — curl + tar extraction of latest LM Studio release, optional settings mirror.
  - `ollama` — official install script + first `ollama serve` bootstrap, optional registry sync.
- Registry data is pure metadata; actual command execution is left to the caller (or future worker) after reading the per-host log.

## API Behaviour & Acceptance
1. `POST /api/remote/install` with a new host writes `logs/remote/install/<host>.log`, creates `data/remote/install/<host>.json`, and returns `status="installed"` with the plan echo.
2. Re-running with the same module returns `status="noop"`, leaves the installed module state intact, and logs a no-op entry rather than duplicating install steps.
3. `GET /api/remote/modules` returns the registry entries described above so the GUI can offer module pickers without hard-coding metadata.
