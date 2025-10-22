# Encrypted Secrets Vault

ComfyVN keeps API tokens, SSH credentials, and other sensitive configuration inside an encrypted Fernet vault so operators can sync repositories safely. This document explains the storage layout, tooling, and integration points used by the remote installer orchestrator and other subsystems.

## File Layout

- **Vault**: `config/comfyvn.secrets.json`
- **Key**: `config/comfyvn.secrets.key` (git-ignored) or environment variable `COMFYVN_SECRETS_KEY`
- **Audit log**: `logs/security.log` (path exposed via `COMFYVN_SECURITY_LOG_FILE`)

Both files are written with `0600` permissions. If the key is absent the loader raises a `SecretStoreError` and explains how to provide one.

## Bootstrapping a Vault

Generate and persist a key once per environment:

```bash
python - <<'PY'
from comfyvn.security.secrets_store import SecretStore

store = SecretStore()
print("New Fernet key:", store.rotate_key())
PY
```

The call decrypts existing entries (if any), rewrites them with the new key, and logs an audit event containing the key fingerprint—not the key itself.

## Managing Entries Programmatically

```python
from comfyvn.security.secrets_store import SecretStore

store = SecretStore()
store.update(
    "remote_installer",
    {
        "defaults": {"port": 22},
        "hosts": {
            "gpu.lab.local": {
                "user": "ubuntu",
                "identity": "~/.ssh/gpu_lab"
            }
        }
    },
)

ssh_secret = store.get("remote_installer")
```

- `write()` replaces the entire payload; `update(provider, mapping)` merges a single provider.
- Values set to `None` are removed.
- The audit logger records provider names and key counts, but never serialises secret values.

## Environment Overrides

Each provider can be overridden without editing the vault: export `COMFYVN_SECRET_<PROVIDER>_<FIELD>`. Examples:

```bash
export COMFYVN_SECRET_REMOTE_INSTALLER_USER=ubuntu
export COMFYVN_SECRET_REMOTE_INSTALLER_IDENTITY=~/.ssh/gpu_fallback
```

Overrides merge with the on-disk payload at read time and are included in `describe()` responses.

## Remote Installer Integration

`/api/remote/install` expects SSH metadata to come from the `secrets` block in the request. The orchestrator resolves it through `SecretStore.get("remote_installer")`, merging:

1. `defaults` (shared fields like `port` or `ssh_command`)
2. `hosts.<key>` or `hosts.<hostname>`
3. Direct provider fields (`user`, `identity`, etc.)
4. Environment overrides

Only non-null fields are forwarded to the SSH runtime. Responses, logs, and FastAPI exceptions omit credential values entirely.

## Auditing & Hooks

- All reads, writes, and key rotations emit structured JSON to the `comfyvn.security.secrets` logger (`logs/security.log`).
- Modder hooks receive `on_security_secret_read` and `on_security_key_rotated` events, enabling custom dashboards or notifications without exposing raw secrets.
- Failed decrypt attempts also emit audit entries, helping operators detect invalid keys quickly.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `SecretStoreError: Secrets key not configured` | Export `COMFYVN_SECRETS_KEY` or create `config/comfyvn.secrets.key` and restart. |
| `Failed to decrypt secrets payload` | Regenerate the key (if you still have the plaintext backup) or restore from a secure copy. New rotations always write the latest format. |
| Secrets appear in logs | Ensure logging level for `comfyvn.security` is unchanged. Custom handlers should redact by default; do not enable DEBUG globally in production. |

Treat `config/comfyvn.secrets.json` and `config/comfyvn.secrets.key` as sensitive artefacts—keep them out of source control and share via your secure secrets management process.
