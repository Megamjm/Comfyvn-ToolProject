# Dev Notes — Persona Importers & Consent Gate

Updated: 2025-12-18 • Audience: Backend & QA  
Owner: Importer Chat (`CHAT_WORK_ORDERS.md → P6 Persona Importers`)

---

## Debug Steps

1. Confirm defaults  
   ```bash
   python tools/check_current_system.py --profile p6_persona_importers --base http://127.0.0.1:8001
   jq .features.enable_persona_importers config/comfyvn.json  # expect false
   ```
2. Record consent  
   ```bash
   curl -sX POST http://127.0.0.1:8001/api/persona/consent \
     -H 'Content-Type: application/json' \
     -d '{"accepted": true, "rights": "owner", "sources": ["manual_entry"]}' | jq
   ```
3. Import persona text + images (see `docs/PERSONA_IMPORTERS.md` for full payloads).
4. Map persona and inspect disk artefacts:  
   ```bash
   cat data/characters/<id>/persona.json | jq
   cat data/characters/<id>/persona.provenance.json | jq
   ```
5. Tail logs with `COMFYVN_LOG_LEVEL=DEBUG` to capture parser warnings and merge
   diagnostics (`grep persona.importer logs/server.log`).

## NSFW Gate Validation

- Leave `enable_nsfw_mode` off: verify `persona.metadata.nsfw_trimmed` echoes removed
  tags and notes.
- Flip the flag, re-import with `{"nsfw_allowed": true}` consent, and confirm NSFW tags
  persist to disk.
- The preview endpoint mirrors the same trimming logic—use it to sanity check UI flows
  without touching disk.

## Modder Hooks & Jobs

- Hook: `on_persona_imported` (REST + WebSocket). Payload surfaces persona data,
  provenance sidecar path, and image asset metadata. Automation bots can subscribe via
  `/api/modder/hooks/ws` or register webhooks (`/api/modder/hooks/webhooks`).
- Image imports enqueue `persona.image2persona` jobs through `jobs_api.submit`. Poll
  `/jobs/poll` or subscribe to `/jobs/ws` when chaining into vision pipelines.

## Storage Layouts

- Consent: `data/persona/consent.json`
- Image uploads: `data/persona/imports/<persona_id>/<hash>.<ext>` + `.meta.json`
- Persona profile: `data/characters/<persona_id>/persona.json`
- Provenance: `data/characters/<persona_id>/persona.provenance.json`
- Legacy mirror: `data/personas/<persona_id>.json` (from `PersonaManager`)

## Regression Notes

- Schema validation lives in `comfyvn/persona/schema.py`. Use `build_persona_record`
  directly in unit tests to simulate NSFW gating and palette defaults.
- `CommunityProfileImporter` accepts markdown, key/value, and JSON payloads. Provide
  minimal fixtures covering each format to guard against regressions.
- Add smoke tests that hit `/api/persona/preview` with and without consent to confirm
  the 403 guard remains in place.

