# Dev Notes — Community Connectors (F-List & FurAffinity)

Updated: 2025-12-23 • Audience: Backend + Tooling contributors

## Purpose

Document connector-specific debugging flows, consent storage, hook expectations, and
parser heuristics so contributors can extend or troubleshoot the import pipeline without
scraping any community platforms.

---

## Code Map

- `comfyvn/connectors/flist.py`
  - `_strip_markup` removes BBCode/URL wrappers; `_extract_sections` recognises headings
    such as `Kinks - Favourites`, `Physical Description`, `RP Preferences`.
  - `_extract_kink_sets` groups favourites/yes/maybe/no entries for NSFW tag mapping.
  - `_prepare_preferences` yields the new schema block `{likes, dislikes, nope}`.
  - `FListConnector.from_text(...)` returns `FListParseResult` with `{persona, warnings,
    trimmed, debug}`. The persona payload already includes metadata + sources.
- `comfyvn/connectors/furaffinity.py`
  - `FurAffinityUploadManager.store_upload` validates base64 payloads, hashes files,
    writes `.meta.json` sidecars, trims NSFW tags when required, and returns debug hints
    (`trimmed_nsfw_tags`, stored filename).
- `comfyvn/server/routes/connectors_persona.py`
  - `/api/connect/flist/consent` writes `data/persona/consent.json` (inherits the same
    file used by `/api/persona/consent`) and stores connector metadata under
    `connectors.flist`.
  - `/api/connect/flist/import_text` and `/api/connect/furaffinity/upload` gate on
    consent + feature flag, returning `debug` structures ready for dashboards.
  - `/api/connect/persona/map` merges text/image payloads, applies NSFW policy, persists
    persona + provenance JSON, and broadcasts both connector + legacy hooks.

---

## Consent Debugging

- Consent lives at `data/persona/consent.json`. Expect shape:

```jsonc
{
  "accepted": true,
  "rights": "owner",
  "sources": ["https://www.f-list.net/c/sample"],
  "nsfw_allowed": false,
  "connectors": {
    "flist": {
      "accepted": true,
      "accepted_at": 1734931200.0,
      "nsfw_allowed": false,
      "profile_url": "https://www.f-list.net/c/sample",
      "agent": "studio.cli"
    }
  }
}
```

- Delete the file between tests to simulate the 403 consent gate.
- When NSFW mode is flipped during runtime, re-call `/api/connect/flist/consent` (or
  `/api/persona/consent`) to update `nsfw_allowed` and confirm responses propagate `nsfw.allowed=true`.

---

## Parser Heuristics

- Headings: `[b]`, `==`, trailing colon. Handy for unit tests: feed sample exports and
  assert `debug.sections` contains `profile`, `kinks - favorites`, `rp preferences`.
- Pronouns: direct `Pronouns:` field takes precedence; otherwise gender heuristics fall
  back to `he/him`, `she/her`, or `they/them`.
- Preferences: likes/dislikes/nope aggregate from keys (`Likes`, `Dislikes`, `No`, `Hard Limits`)
  and the `RP Preferences` section. The output populates `persona.preferences`.
- Kinks: `Favourites` + `Yes` feed `persona.tags.nsfw` and `persona.nsfw.tags`.
  `Maybe`/`No` are preserved via debug + preferences (nope list).

---

## FurAffinity Upload Notes

- Only base64 payloads accepted. Any attempt to pass URLs should return HTTP 400.
- Sidecar example (`*.meta.json`):

```jsonc
{
  "hash": "abc123",
  "persona_id": "meridian-fox",
  "filename": "badge.png",
  "stored_name": "abc123.png",
  "media_type": "image/png",
  "artist": "Meridian",
  "tags": ["badge", "portrait"],
  "nsfw_tags": [],
  "nsfw_tags_trimmed": ["nsfw"],
  "provenance": {"source_url": "https://www.furaffinity.net/view/123"}
}
```

- When NSFW gating is disabled, expect `nsfw_tags=[]` and the trimmed list to echo the
  user-supplied tags for audit trails.

---

## Hook Verification

| Route                              | Hook(s) fired                           | Debug field(s)                       |
|------------------------------------|-----------------------------------------|--------------------------------------|
| `/api/connect/flist/import_text`   | `on_flist_profile_parsed`                | `result.debug`                       |
| `/api/connect/furaffinity/upload`  | `on_furaffinity_asset_uploaded`         | `debug_entries[]`                    |
| `/api/connect/persona/map`         | `on_connector_persona_mapped` + legacy `on_persona_imported` | `persona.metadata.import_debug`, `persona.metadata.image_assets` |

Use `/api/modder/hooks/history` to confirm payloads (hashes, sidecars, persona IDs)
match the REST responses.

---

## QA / Automation Checklist

- [ ] Run `python tools/check_current_system.py --profile p7_connectors_flist_fa`.
- [ ] Toggle `enable_nsfw_mode` and confirm trimmed tags reappear/persist accordingly.
- [ ] Confirm consent metadata propagates to `persona.metadata.consent`.
- [ ] Validate persona preferences appear in saved `persona.json`.
- [ ] Ensure no network requests occur during uploads (network sandbox logs remain empty).

---

## Open Follow-ups

- OAuth flow for F-List remains TODO until the platform publishes an official API.
- Artist credit taxonomy for FurAffinity uploads could move to a reusable provenance
  schema shared with future gallery connectors.
