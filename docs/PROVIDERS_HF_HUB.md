# Hugging Face Hub Connector

Dry-run connector for Hugging Face Hub assets. The server exposes helper routes
so Studio panels, automation scripts, and modders can explore model cards,
inspect file inventories, and plan gated downloads without touching the live
Hub unless contributors explicitly opt in with a token plus license
acknowledgement.

## Feature flag & setup

- Feature flag: `enable_public_model_hubs` (defaults to `false`).
- Enable only after storing a **personal access token (PAT)**. Use either
  environment variables (`HF_TOKEN`, `HF_API_TOKEN`,
  `HUGGINGFACEHUB_API_TOKEN`, `HUGGINGFACEHUB_TOKEN`) or the secrets store
  (`config/comfyvn.secrets.json` under the `hf_hub` provider with `token`,
  `api_token`, or `hf_token`).
- The backend merges env + secrets when the flag is enabled; missing tokens keep
  `dry_run` responses but mark pulls as unauthorised.
- Pair the connector with the advisory licence gate: call
  `POST /api/advisory/license/snapshot` before offering a download, surface the
  normalised text to the user, store the acknowledgement via
  `POST /api/advisory/license/ack`, and gate pulls with
  `POST /api/advisory/license/require`. Details live in
  `docs/ADVISORY_LICENSE_SNAPSHOT.md`.

## REST endpoints

All routes live under `/api/providers/hf/*` and return dry-run payloads that
include connector metadata (`docs_url`, `last_checked`, feature context).

### `GET /api/providers/hf/health`

- Returns connector metadata, dependency status (whether `huggingface_hub` is
  installed), token presence, and timestamp.
- No network calls; safe to hit even when the feature flag remains disabled.

### `GET /api/providers/hf/search`

- Query params:
  - `query` (required): search term.
  - `kind`: `model`, `dataset`, or `space` (default `model`).
  - `limit`: caps at `50` (default `10`).
  - `auth` (`true|false`): when `true`, the server will attempt to reuse the
    stored PAT; `token` overrides when supplied.
  - `token`: optional explicit PAT if the stored secret is absent.
- Results include normalised tags (merged from Hub metadata + model card),
  license hints, file listings with `size`/`is_large` signals, `gated`/`private`
  flags, and `dry_run: true`.
- Large artifacts (`>= 1 GiB`) increment `large_file_count` so Studio can warn
  modders before they pull.

### `GET /api/providers/hf/metadata`

- Query params mirror `/search` and add `id` (required repo id) plus optional
  `revision`.
- Returns a single `item` object with full file inventory (`path`, `size`,
  `download_url`, `is_large`, `lfs`), card summary (`summary`, `pipeline_tag`,
  `language`, `base_model`, `model_index_count`), and `requires_token` flag.
- Tokens are optional for public repos; gated/private repos respond with HTTP
  401 unless the caller opted into `auth=true` or provided `token`.

### `POST /api/providers/hf/pull`

- Input fields:
  - `repo_id` / `id` / `repo`: repository identifier (required).
  - `kind`: `model|dataset|space` (defaults to `model`).
  - `revision`: optional git ref.
  - `files` (array or comma string): optional subset of files to include.
  - `ack_license` (`true|false`): **required**; `412` when omitted.
  - `token` or nested `config.token`: optional explicit PAT; otherwise the
    server resolves stored secrets via `hf_hub`.
- Requires a PAT for gated/private repos. When credentials and license
  acknowledgement are present the response contains a dry-run plan: resolved
  revision, enumerated files, total byte size, large-file count, and a nested
  metadata snapshot (`metadata`).
- The plan never downloads files; clients must perform the actual pull once
  the user explicitly opts in.

## Debugging & dev notes

- All responses include `feature` context; when the flag is disabled, the
  payloads set `ok: false` with `reason: "feature disabled"` so dashboards can
  reflect the disabled state without issuing warnings.
- `token_present` in `/health` helps UI surfaces gate buttons before probing
  the Hub.
- Search/metadata requests bubble dependency and HTTP errors as typed HTTP
  responses (`huggingface_hub` missing → `503`, missing token → `401`,
  missing files → `404`).
- Modder tooling can inspect `metadata.plan.files[*].is_large` to decide when
  to warn about large downloads or prompt for streaming strategies.

## Checker profile

Run the profile after toggling the flag on a dev instance to confirm routes +
docs exist:

```bash
python tools/check_current_system.py \
  --profile p7_connectors_huggingface \
  --base http://127.0.0.1:8001
```
