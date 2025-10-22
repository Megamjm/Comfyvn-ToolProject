# Remote Installer Orchestrator (SSH)

The remote installer orchestrator provisions ComfyUI, SillyTavern, LM Studio, and Ollama on SSH-accessible hosts while keeping credentials encrypted and status updates deterministic. Commands are issued over SSH, no configuration files are overwritten, and every run appends structured metadata so automation can resume safely.

## Feature Flag & Prerequisites
- Flip `features.enable_remote_installer` on via **Settings → Debug & Feature Flags** or set the field in `config/comfyvn.json` before starting the server. The feature is disabled by default.
- Remote host requirements:
  - Linux (Ubuntu 20.04+, Debian 12+, Rocky 9) is the reference platform. Windows hosts are supported when OpenSSH Server is enabled and the PowerShell profile loads a POSIX-like shell (Git Bash, MSYS2). Command detection relies on standard POSIX semantics.
  - `sudo` access for package management where noted (ComfyUI dependencies install `git`, `python3-venv`, `python3-pip`).
  - Outbound network access to fetch upstream archives (`git`, `curl`, `npm`), and sufficient disk space (~6 GiB) per tool.
  - SSH key authentication is recommended. Point the orchestrator at an identity stored locally; the private key is never copied to the remote node.

## Secrets & Credential Layout
Store connection details in the encrypted vault `config/comfyvn.secrets.json` (see `docs/SECURITY_SECRETS.md`). A minimal entry:

```json
{
  "remote_installer": {
    "defaults": {"port": 22},
    "hosts": {
      "gpu.lab.local": {
        "user": "ubuntu",
        "identity": "~/.ssh/gpu_lab"
      }
    }
  }
}
```

Override fields at runtime with `COMFYVN_SECRET_REMOTE_INSTALLER_<FIELD>` (e.g. `COMFYVN_SECRET_REMOTE_INSTALLER_USER=ubuntu`). All reads and writes emit audit events to `logs/security.log` without serialising credential values.

## API Surface

| Route | Method | Description |
| --- | --- | --- |
| `/api/remote/modules` | GET | Enumerate installer modules, install steps, config sync descriptors, and detection probes. |
| `/api/remote/install` | POST | Plan and apply remote installs. Supports `dry_run`, SSH overrides, and secret-backed credential lookup. |
| `/api/remote/status` | GET | Return a list of known hosts or the latest status manifest for a specific host. |

### Request Payload

```json
{
  "host": "gpu.lab.local",
  "modules": ["comfyui", "ollama"],
  "dry_run": false,
  "ssh": {
    "probe": true,
    "record_only": false
  },
  "secrets": {
    "provider": "remote_installer",
    "key": "gpu.lab.local"
  }
}
```

- `ssh` overrides (all optional): `user`, `port`, `identity`, `ssh_command`, `scp_command`, `connect_timeout`, `env`, `probe`, `record_only`.
- `secrets` specifies which vault entry to merge. The provider payload may define `defaults` plus `hosts.{key}` blocks. Secrets are never echoed in responses or logs.

### Example Calls

```bash
# Inspect available modules
curl -s http://127.0.0.1:8001/api/remote/modules | jq

# Dry-run install to review idempotent steps
curl -s -X POST http://127.0.0.1:8001/api/remote/install \
  -H 'Content-Type: application/json' \
  -d '{"host":"gpu.lab.local","modules":["comfyui"],"dry_run":true}' | jq '.plan'

# Apply install using secrets-backed credentials
curl -s -X POST http://127.0.0.1:8001/api/remote/install \
  -H 'Content-Type: application/json' \
  -d '{"host":"gpu.lab.local","modules":["comfyui"],"secrets":{"provider":"remote_installer"}}' | jq '{status,installed,skipped,failed,status_path,log_path}'

# Fetch status for a specific host
curl -s 'http://127.0.0.1:8001/api/remote/status?host=gpu.lab.local' | jq
```

## Execution Model & Idempotency

- **Detection**: Each module ships probe commands (`detect_steps`) that look for installation sentinels (`~/.config/comfyvn/remote/<module>.installed`) and project directories. Planned actions flip to `"noop"` when the remote host already satisfies the checks, even if the local status file was lost.
- **Sentinel writes**: Final installer steps create module-specific sentinel files, enabling replays without clobbering user changes.
- **Config sync**: Assets are uploaded only when local sources exist and the remote destination is absent. Existing files are preserved to avoid overwriting operator-tuned configs.
- **Status manifests**: Runs persist to `data/remote/install/<host>.json`, capturing per-module state (`installed`, `failed`, `skipped`), timestamps, and the last reason. Logs append to `logs/remote/install/<host>.log`.
- **Failures**: Any non-zero command or missing required asset marks the module as `failed` and halts further steps for that module. Re-run the installer after fixing the underlying issue; successful modules remain untouched.

## Rollback & Recovery

1. Inspect the status manifest (`/api/remote/status`) to identify failing modules.
2. Tail the log file referenced in the response for command-level output.
3. If a step failed mid-stream, correct the remote environment (e.g., reinstall packages, free disk space) and re-run the installer. Idempotent checks ensure completed commands are skipped.
4. To rollback repo changes manually, use the git workspace on the remote host (`~/ComfyUI`, `~/SillyTavern`, etc.). Config sync never overwrites existing files; create backups before hand-tuning remote configs.

## Debug & Modder Hooks

- Toggle `dry_run` to capture plans without mutating files—ideal for CI or human approval loops.
- Pair the orchestrator with `comfyvn.remote.installer.open_log` for streaming log data to task dashboards.
- Secret operations emit audit JSON to `logs/security.log` via the `comfyvn.security.secrets` logger. Hooks defined in `comfyvn.core.modder_hooks` receive `on_security_secret_read` and `on_security_key_rotated` events when applicable, enabling contributors to broadcast state inside custom tooling.
- For smoke verification, run the planner twice for each host: the second execution should report `"status":"noop"` and skip modules detected as installed.

## Supported Modules Overview

| Module | Focus | Key Steps |
| --- | --- | --- |
| `comfyui` | Workflow engine | Apt dependencies, git clone/update, Python venv bootstrap, sentinel creation. |
| `sillytavern` | RP frontend | Repo clone/update, `npm install`, optional extension sync, sentinel creation. |
| `lmstudio` | Local LLM tooling | Archive download/extract, optional settings sync, sentinel creation. |
| `ollama` | LLM runtime | Official install script, first-run `ollama serve`, config sync, sentinel creation. |

Logs redact credentials and only record high-level actions, ensuring secrets remain confined to the vault.
