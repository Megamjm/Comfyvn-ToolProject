# Dev Notes — Asset Ingest Queue

Updated: 2025-12-22

## Feature toggles & config

- `features.enable_asset_ingest`: gates `/api/ingest/*`. Keep **false** in shipping builds; Studio toggles it under Settings → Debug & Feature Flags.
- `features.require_remote_terms_ack`: forces `terms_acknowledged=true` for remote pulls (Civitai/Hugging Face). Disable temporarily when replaying archived requests that lack the field.
- Staging path: `data/ingest/staging/`
- Dedup index: `cache/ingest/dedup_cache.json`

## Queue internals

- `comfyvn/ingest/queue.py::AssetIngestQueue` owns persistence, rate limiting, and coordination with the asset registry.
  - Background state lives in `queue_state.json` (versioned). Updating the schema requires bumping `STATE_VERSION`.
  - Rate limiting uses a token bucket (`~0.33 rps`) per provider key. Increase `DEFAULT_RATE_LIMIT` when testing bulk remote pulls.
  - Dedup hits:
    - Matching digest already in queue → `status=duplicate`, `dedup_of=<job_id>`
    - Matching digest already in registry → `status=duplicate`, `existing_uid=<asset_uid>`
  - Cache pins drop after `apply()` or `release()`. Missing staging files mark the job `failed`.
- Metadata normalisation lives in `comfyvn/ingest/mappers.py`. Extending the system for new providers means:
  1. Add a provider block inside `normalise_metadata()`
  2. Add domain rules in `_REMOTE_ALLOWLIST` when remote pulls are allowed
  3. Extend docs (`docs/ASSET_INGEST.md`)

## Modder hooks

- `on_asset_ingest_enqueued` fires for every queue attempt (including duplicates). Sample payload:

  ```json
  {
    "job_id": "abc123def456",
    "provider": "civitai",
    "status": "staged",
    "digest": "4e3a...",
    "asset_type_hint": "models",
    "notes": []
  }
  ```

- `on_asset_ingest_applied` triggers after `apply()` copies into the registry and sidecars are written.
- `on_asset_ingest_failed` captures both remote download errors and apply failures (e.g., missing staging file).
- Subscribe through `/api/modder/hooks` or `ws://.../api/modder/hooks/stream`.

## Debug cookbook

1. **Inspect queue state**  
   `python - <<'PY'\nfrom comfyvn.ingest.queue import get_ingest_queue\nq = get_ingest_queue()\nprint(q.summary())\nprint(q.list_jobs(limit=5))\nPY`

2. **Snapshot dedup cache**  
   `jq '.cache' <<< "$(curl -s http://127.0.0.1:8001/api/ingest/status?include_cache=true)"`

3. **Force-release a stuck job**  
   `python - <<'PY'\nfrom comfyvn.ingest.queue import get_ingest_queue\nq = get_ingest_queue()\nprint(q.release("job_id_here"))\nPY`

4. **Validate queue + routes stay wired**  
   `python tools/check_current_system.py --profile p7_asset_ingest_cache --base http://127.0.0.1:8001`

## Failure scenarios & remediation

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `duplicate.registry` note | Digest already registered | Surface to user, optionally create registry alias instead of re-importing. |
| `Status=failed` with `Staging file missing` | External tooling removed `data/ingest/staging/*` | Re-queue the source asset. |
| `429` on remote pulls | Rate limiter triggered | Sleep/retry; increase `DEFAULT_RATE_LIMIT` for bulk tests. |
| `enable_asset_ingest disabled` response | Feature flag still false | Flip via Studio Settings or edit `config/comfyvn.json`. |
| `Remote asset exceeds size limit` | Pull bigger than `200 MiB` | Download manually, use `source_path` upload, or raise `MAX_REMOTE_BYTES` for controlled runs. |

## Test profile

Run the system checker as part of integration sweeps:

```bash
python tools/check_current_system.py --profile p7_asset_ingest_cache --base http://127.0.0.1:8001
```

It validates feature flag defaults, route existence, and documentation coverage.

