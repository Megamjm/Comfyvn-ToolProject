# Headless Mode Bootstrap

ComfyVN can run in a pure server context where the Qt GUI is skipped (`--server-only`) or by exporting `COMFYVN_HEADLESS=1`. The launcher now prepares this environment by installing any headless-only Python dependencies before the API starts serving.

## Auto-install flow
- Bootstrap entrypoint: `comfyvn.server.bootstrap.headless.ensure_headless_ready()`.
- Triggered *only* when `--server-only` is passed or `COMFYVN_HEADLESS=1`.
- Requirements search order (first match wins):
  1. `requirements-headless.txt`
  2. `requirements/web.txt`
  3. `requirements/requirements-headless.txt`
- The selected file is hashed (`SHA-256`) and compared with `.runtime/headless.hash`. If unchanged, nothing runs.
- When the hash differs, dependencies are installed via `python -m pip install -r <file> -q`. Output is captured to `.runtime/headless_install.log`.

## Configuration knobs
- `COMFYVN_HEADLESS_AUTO=0|false|no` skips the auto-install entirely while still launching the server.
- Existing pip environment variables are respected—most notably `PIP_INDEX_URL`, `PIP_NO_INDEX`, and authentication settings.
- Hashes and logs live under the repo `.runtime/` directory so they are scoped to a single checkout. Deleting `.runtime/headless.hash` forces a reinstall on the next headless start.

## Offline & failure handling
- A quick TCP reachability probe uses `PIP_INDEX_URL` (or defaults to `https://pypi.org/simple/`). If the index host cannot be reached, installation is skipped.
- The launcher prints one clear message to stdout when it skips due to offline detection and then continues serving.
- Pip failures are non-fatal. The error is appended to `.runtime/headless_install.log` so contributors can diagnose without stalling CI or staging servers.

## Debugging checklist
- Inspect `.runtime/headless_install.log` for the full pip transcript and timestamps.
- Compare the active requirements hash stored in `.runtime/headless.hash` with `sha256sum <requirements file>` if you suspect a partial write.
- Override `COMFYVN_HEADLESS_AUTO=0` when debugging packaging issues to keep the launcher from re-installing repeatedly.
- If you ship custom headless bundles, publish a repo-specific `requirements-headless.txt` in the repo root so the bootstrap system picks it up without extra wiring.

## Developer hooks
- `ensure_headless_ready()` is lightweight and safe to call from other automation (e.g. deployment scripts, test fixtures). It no-ops when the hash matches or when the auto flag is disabled.
- Modding toolchains can extend the process by generating their own requirements file in one of the supported locations before the launcher starts, ensuring their APIs are installed automatically.

