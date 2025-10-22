# NSFW Gating — Persona Importers

Updated: 2025-12-18 • Owner: Importer Chat

The community persona importer ships with an explicit NSFW gate. Payloads that include
adult-oriented tags or notes are always filtered unless two switches are enabled:

1. `features.enable_persona_importers` — unlocks the import pipeline at all.
2. `features.enable_nsfw_mode` **and** consent JSON `{"nsfw_allowed": true}` —
   together allow NSFW fields to be persisted.

Without both toggles the API still parses input but removes sensitive data while
reporting what changed, keeping logs clean for teams that prefer safe defaults.

---

## Flow Summary

1. User submits `POST /api/persona/consent` with `{"accepted": true, "nsfw_allowed": true}`.
2. Feature flag `enable_nsfw_mode` remains **false** by default. Flip it in
   `config/comfyvn.json → features.enable_nsfw_mode` or via Studio Settings.
3. Persona imports (`/api/persona/import/text`, `/api/persona/map`, `/api/persona/preview`)
   and community connector routes (`/api/connect/flist/import_text`,
   `/api/connect/furaffinity/upload`, `/api/connect/persona/map`) call `apply_nsfw_policy`
   and shared helpers in `comfyvn/persona/schema.py`:
   - When disabled, the response echoes `nsfw.trimmed` with removed tags/notes.
   - When enabled *and* consent allows NSFW, tags persist under `persona.tags.nsfw`
     and notes remain intact.
4. Disk writes (`persona.json`, `.provenance.json`) mirror the same filtered payloads.

## Example

```jsonc
{
  "nsfw": {
    "allowed": false,
    "tags": [],
    "notes": null
  },
  "tags": {
    "general": ["alchemist", "nightlife"],
    "style": ["urban fantasy"],
    "nsfw": []
  },
  "metadata": {
    "nsfw_trimmed": {
      "nsfw_tags_removed": ["nsfw"],
      "nsfw_notes_removed": true,
      "general_tags_removed": []
    }
  }
}
```

Once NSFW mode is enabled and consent authorises NSFW processing, the same payload
returns:

```jsonc
{
  "nsfw": {
    "allowed": true,
    "tags": ["nsfw"],
    "notes": "Explicit romance arcs."
  }
}
```

## Verification Checklist

- `[ ]` `config/comfyvn.json → features.enable_nsfw_mode` remains **false** by default.
- `[ ]` `data/persona/consent.json` records `nsfw_allowed` before any NSFW metadata is
        stored.
- `[ ]` Responses expose `nsfw.trimmed` when the gate is closed.
- `[ ]` `persona.provenance.json` mirrors `nsfw_allowed` so auditors can confirm how the
        record was produced.
- `[ ]` Connector responses (`/api/connect/flist/import_text`, `/api/connect/furaffinity/upload`,
        `/api/connect/persona/map`) report `nsfw.allowed/trimmed` aligned with the persona
        importer responses.

Use `python tools/check_current_system.py --profile p6_persona_importers` after toggling
flags to ensure the checker still reports the expected defaults. For connector coverage,
run `python tools/check_current_system.py --profile p7_connectors_flist_fa`.
