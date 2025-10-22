# Community Connectors — F-List & FurAffinity

Updated: 2025-12-23 • Owner: Persona Connectors Chat

Community connectors let authors import roleplay personas without scraping third-party
services. The flow stays consent-first, feature-flagged, and provably local: users
paste F-List profile exports and upload FurAffinity images they own. Nothing is fetched
from remote endpoints, cookies, or crawlers.

---

## Feature Flags & Prerequisites

- `features.enable_persona_importers` must be enabled before any connector routes respond.
- `features.enable_nsfw_mode` remains **false** by default; when flipped (and the user
  grants NSFW consent) the connectors preserve kink/NSFW tags, otherwise they are trimmed.
- Consent is persisted to `data/persona/consent.json`. Until `/api/connect/flist/consent`
  is acknowledged, every connector route returns HTTP 403.

The system checker covers the wiring:

```bash
python tools/check_current_system.py \
  --profile p7_connectors_flist_fa \
  --base http://127.0.0.1:8001
```

---

## Consent Flow

`POST /api/connect/flist/consent`

- Required before any `/api/connect/*` call succeeds.
- Records `{rights, sources[], nsfw_allowed, agent, notes, profile_url}` under
  `data/persona/consent.json → connectors.flist`.
- Response includes feature & NSFW gate states so dashboards can warn users when the
  global NSFW toggle is still disabled.

Example:

```bash
curl -s -X POST http://127.0.0.1:8001/api/connect/flist/consent \
  -H "Content-Type: application/json" \
  -d '{
        "accepted": true,
        "rights": "owner",
        "sources": ["https://www.f-list.net/c/sample"],
        "profile_url": "https://www.f-list.net/c/sample",
        "nsfw_allowed": false,
        "agent": "studio.cli"
      }' | jq
```

---

## F-List Profile Import

`POST /api/connect/flist/import_text`

- Accepts raw F-List exports/markdown. No scraping or HTTP fetches occur.
- Normalises persona fields (species, pronouns, lore, preferences, likes/dislikes/nope)
  and maps the kink taxonomy (`Favourites`, `Yes`, `Maybe`, `No`) into persona tags.
- Returns `{persona, warnings[], debug.sections, debug.kink_counts, nsfw}`. The `nsfw`
  block reports which tags were trimmed when the gate is closed.
- Emits the `on_flist_profile_parsed` modder hook with the full persona payload so
  dashboards/plugins can diff changes.

Example:

```bash
curl -s -X POST http://127.0.0.1:8001/api/connect/flist/import_text \
  -H "Content-Type: application/json" \
  -d '{
        "text": "[b]Name:[/b] Meridian Fox\n[b]Species:[/b] Kitsune\n[b]Kinks - Favorites[/b]\n- Tail play\n- Warm baths",
        "persona_id": "meridian-fox",
        "metadata": {"source": "manual-upload"},
        "role": "npc"
      }' | jq '.persona.metadata.import_debug'
```

---

## FurAffinity Uploads (User-Supplied Only)

`POST /api/connect/furaffinity/upload`

- Accepts a list of `{data, filename?, media_type?, tags?, nsfw_tags?, artist?, title?, description?, source_url?}`.
- `data` must be a base64 blob (Data URI prefixes are supported). The backend never
  performs outbound fetches or cookie-authenticated queries.
- Files store under `data/persona/imports/<persona_id>/<sha256>.<ext>`; sidecars append
  `.meta.json` detailing hashes, provenance, credits, and trimmed NSFW tags.
- When NSFW mode is disabled (or consent forbids it) any supplied `nsfw_tags` move into
  `*.meta.json → nsfw_tags_trimmed`. Responses reflect the trimmed list via `debug`.
- Emits the `on_furaffinity_asset_uploaded` hook with `{persona_id, assets[], debug[], requested_at}`.

Example:

```bash
curl -s -X POST http://127.0.0.1:8001/api/connect/furaffinity/upload \
  -H "Content-Type: application/json" \
  -d '{
        "persona_id": "meridian-fox",
        "images": [{
          "filename": "meridian-badge.png",
          "media_type": "image/png",
          "data": "'$(base64 -w0 assets/sample.png)'",
          "tags": ["badge", "portrait"],
          "artist": "Meridian"
        }]
      }' | jq '.assets[0].sidecar'
```

---

## Persona Mapping

`POST /api/connect/persona/map`

- Merges the text persona (from F-List) with optional `image_traits` (Phase-6
  image2persona output) and user-supplied tag overrides.
- Persists `data/characters/<persona_id>/persona.json` and
  `data/characters/<persona_id>/persona.provenance.json`.
- Attaches consent metadata, stored image asset references, and NSFW trim summaries
  to `persona.metadata`.
- Emits both `on_connector_persona_mapped` and the existing `on_persona_imported`
  hooks so existing Studio/automation integrations continue to receive updates.

Quick preview:

```bash
curl -s -X POST http://127.0.0.1:8001/api/connect/persona/map \
  -H "Content-Type: application/json" \
  -d '{
        "persona_id": "meridian-fox",
        "text_persona": {"id": "meridian-fox", "name": "Meridian Fox"},
        "image_assets": [{"hash": "abc", "path": "/tmp/sample.png"}]
      }' | jq '.persona_path'
```

---

## Persona Schema Extensions

`PersonaPreferences` (`likes`, `dislikes`, `nope`) were added to the core persona schema.
Connector payloads populate the block so automation doesn’t need custom metadata keys
to track boundaries.

---

## Hook Reference

| Event                          | Payload Highlights                                                  |
|--------------------------------|---------------------------------------------------------------------|
| `on_flist_profile_parsed`      | `persona_id`, `persona`, `warnings`, `debug`, `requested_at`        |
| `on_furaffinity_asset_uploaded`| `persona_id`, `assets[]`, `debug[]`, `requested_at`                 |
| `on_connector_persona_mapped`  | `persona_id`, `persona`, `character_dir`, `provenance`, `sources[]` |

All hooks appear in `/api/modder/hooks` once the connector routes load.

---

## Debugging & QA Checklist

- [ ] Consent JSON contains `connectors.flist.accepted=true` before running imports.
- [ ] F-List parser reports expected `debug.sections` (e.g., `profile`, `kinks - favorites`).
- [ ] FurAffinity uploads store to `data/persona/imports/<persona>/<sha256>.ext` with a matching `.meta.json`.
- [ ] `persona.metadata.nsfw_trimmed.nsfw_tags_removed` reflects trimmed kink tags when the gate is closed.
- [ ] Hook history (`/api/modder/hooks/history`) shows each connector event with deterministic timestamps.
- [ ] The system checker profile `p7_connectors_flist_fa` returns `"pass": true`.
