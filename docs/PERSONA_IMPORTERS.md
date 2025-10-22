# Persona Importers — Community Profiles (Phase 6)

Updated: 2025-12-18 • Owner: Importer Chat  
Checker: `python tools/check_current_system.py --profile p6_persona_importers --base http://127.0.0.1:8001`

The community persona importer maps ad-hoc profile dumps (markdown, text blocks,
structured JSON) into the Studio persona schema. The flow is feature gated and
requires explicit user consent before any payload is processed. Community connectors
(`docs/COMMUNITY_CONNECTORS.md`) reuse the same consent + NSFW gates for F-List and
FurAffinity uploads.

---

## Feature Flags & Consent

- `features.enable_persona_importers` (default **false**) gates every route described
  below. When disabled the API responds with HTTP 403.
- `features.enable_nsfw_mode` (default **false**) enables NSFW field processing. Even
  when the flag is raised, NSFW notes and tags are filtered unless the consent record
  includes `"nsfw_allowed": true`.
- Consent is recorded via `POST /api/persona/consent`. Payload:

  ```jsonc
  {
    "accepted": true,
    "rights": "owner",
    "sources": ["manual_entry"],
    "nsfw_allowed": false,
    "notes": "Profiles supplied by team."
  }
  ```

  Metadata persists to `data/persona/consent.json`, echoing `accepted_at`, feature flag
  state, and any agent/notes provided. Requests without consent return HTTP 403.

## API Surface

| Endpoint | Purpose |
| --- | --- |
| `POST /api/persona/consent` | Persist acknowledgement + rights to process supplied personas. |
| `POST /api/persona/import/text` | Parse profile text (markdown, JSON, key/value blocks) into the persona schema. |
| `POST /api/persona/import/images` | Store reference images, write provenance sidecars, and enqueue an `persona.image2persona` job. |
| `POST /api/persona/map` | Merge text + image traits, dedupe tags, and persist `data/characters/<id>/persona.json` + provenance. |
| `POST /api/persona/preview` | Dry-run mapping for UI previews (no disk writes). |

### `/api/persona/import/text`

```bash
curl -s -X POST http://127.0.0.1:8001/api/persona/import/text \
  -H 'Content-Type: application/json' \
  -d @- <<'JSON'
{
  "persona_id": "midnight-alchemist",
  "text": "## Name\nMidnight Alchemist\n## Species\nElf\n## Appearance\n- Tall\n- Silver hair\n## Pronouns\nshe/her\n## Voice\nWarm, sardonic.\n",
  "metadata": {
    "source": "wiki_dump",
    "version": "v3"
  }
}
JSON | jq
```

Response highlights:

```jsonc
{
  "ok": true,
  "persona": {
    "id": "midnight-alchemist",
    "name": "Midnight Alchemist",
    "tags": {"general": ["elf"], "style": [], "nsfw": []},
    "appearance": {"summary": "..."},
    "preferences": {"likes": [], "dislikes": [], "nope": []},
    "palette": {"primary": "#a855f7", "secondary": "#6366f1", "accent": "#ec4899"},
    "nsfw": {"allowed": false, "tags": [], "notes": null},
    "sources": [
      {"type": "text", "value": "wiki_dump", "rights": "owner"}
    ]
  },
  "warnings": ["Species not provided."],
  "nsfw": {"allowed": false, "trimmed": {...}}
}
```

### `/api/persona/import/images`

Accepts a list of base64-encoded images. Assets are written under
`data/persona/imports/<persona_id>/` with `.meta.json` sidecars capturing hashes,
consent context, and original filenames.

```bash
BASE64_IMAGE=$(base64 -w0 assets/example/persona_ref.png)
curl -s -X POST http://127.0.0.1:8001/api/persona/import/images \
  -H 'Content-Type: application/json' \
  -d @- <<JSON
{
  "persona_id": "midnight-alchemist",
  "images": [
    {
      "filename": "ref01.png",
      "media_type": "image/png",
      "data": "$BASE64_IMAGE"
    }
  ]
}
JSON | jq
```

The response includes stored file metadata plus a `jobs.submit` payload:

```jsonc
{
  "ok": true,
  "persona_id": "midnight-alchemist",
  "images": [
    {
      "hash": "c5f0…",
      "path": "data/persona/imports/midnight-alchemist/c5f0....png",
      "sidecar": "data/persona/imports/midnight-alchemist/c5f0....png.meta.json"
    }
  ],
  "job": {"ok": true, "id": "0d1e..."},
  "nsfw": {"allowed": false}
}
```

Automation can tail `/jobs/ws` or poll `/jobs/poll` for the `persona.image2persona`
job to attach downstream inference results.

### `/api/persona/map`

Combines textual persona data with optional `image_traits` and `image_assets`, writes
`data/characters/<id>/persona.json`, mirrors provenance to
`data/characters/<id>/persona.provenance.json`, and registers the persona with
`PersonaManager`.

```bash
curl -s -X POST http://127.0.0.1:8001/api/persona/map \
  -H 'Content-Type: application/json' \
  -d @- <<'JSON'
{
  "persona_id": "midnight-alchemist",
  "text_persona": { "name": "Midnight Alchemist", "tags": {"general": ["alchemist"]}},
  "image_traits": { "palette": {"swatches": [{"name": "accent", "hex": "#6b7280"}]}},
  "image_assets": [
    {"hash": "c5f0...", "path": "data/persona/imports/midnight-alchemist/c5f0....png"}
  ]
}
JSON | jq
```

Response:

```jsonc
{
  "ok": true,
  "persona": {...},
  "persona_path": "data/characters/midnight-alchemist/persona.json",
  "provenance": "data/characters/midnight-alchemist/persona.provenance.json"
}
```

## Storage & Provenance

- Persona profiles persist to `data/characters/<id>/persona.json`. Legacy
  `PersonaManager` mirrors continue to land under `data/personas/<id>.json`.
- Provenance sidecars live next to the persona profile as
  `persona.provenance.json`, capturing image hashes, consent state, NSFW gating,
  and timestamps.
- Image uploads carry `.meta.json` sidecars with SHA-256 digests and consent metadata.
  Use `jq` or `python -m json.tool` to inspect them during QA.

## Modder Hooks & Automation

- Hook name: `on_persona_imported`
  - WebSocket topic: `modder.on_persona_imported`
  - Payload fields: `persona_id`, `persona`, `character_dir`, `sidecar`,
    `image_assets`, `sources`, `requested_at`.
- Subscribe via `/api/modder/hooks/ws` or register REST webhooks through
  `/api/modder/hooks/webhooks`. Automation can diff persona payloads, mirror sidecars,
  or trigger downstream asset generation safely (the hook is emitted after disk writes).

## Debug & Verification

- Run `python tools/check_current_system.py --profile p6_persona_importers` to confirm
  default flag states, route registration, and documentation coverage.
- Set `COMFYVN_LOG_LEVEL=DEBUG` to capture persona importer traces under
  `logs/server.log` (`comfyvn.server.routes.persona` logger).
- Inspect consent state with `jq < data/persona/consent.json`.
- When NSFW mode is disabled, responses echo the tags/notes trimmed from the payload
  so QA can verify gating without re-running inference.
