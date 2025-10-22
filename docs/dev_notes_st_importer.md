# Dev Notes — SillyTavern Chat Importer

Owner: Project Integration (Chat P) • Updated: 2025-10-21

Scope: implementation details, heuristics, and debug recipes for the Phase 9
ST chat importer (`comfyvn/importers/st_chat/*`,
`comfyvn/server/routes/import_st.py`). Pair with
`docs/ST_IMPORTER_GUIDE.md` for operator/modder guidance.

---

## Feature flag & entry points

- Flag: `features.enable_st_importer` (default **false**). Flip via
  **Settings → Debug & Feature Flags** or edit `config/comfyvn.json` and call
  `feature_flags.refresh_cache()` in long-lived processes.
- Router: `comfyvn/server/routes/import_st.py` mounted through
  `comfyvn/server/modules/st_import_api.py`.
- Endpoints:
  - `POST /api/import/st/start` — accepts `projectId` + exactly one of
    `file` (`UploadFile`), `text` (str), or `url` (HTTP/S). Returns `{ok, runId,
    sceneCount, warnings, status}`.
  - `GET /api/import/st/status/{runId}` — returns `{phase, progress, scenes,
    warnings, preview}` plus cached run metadata.
- Modder hooks:
  - `on_st_import_started` → fired after run directory creation (`{run_id,
    project_id, source, timestamp}`).
  - `on_st_import_scene_ready` → per generated scene (`{run_id, project_id,
    scene_id, title, participants, warnings}`).
  - `on_st_import_completed` → terminal success (`{run_id, project_id,
    scene_count, warnings, status, preview_path}`).
  - `on_st_import_failed` → terminal failure (`{run_id, project_id, error,
    timestamp}`).

---

## Parser heuristics (`comfyvn/importers/st_chat/parser.py`)

- Supports SillyTavern `.json`, `.jsonl`, and roleplay `.txt` exports.
- Standard keys: `entries`, `messages`, `history`, `chat`, `turns`.
- Speaker resolution: probes `name`, `speaker`, `author`, `role`, `character`,
  falling back to nested `metadata/meta/extensions` dictionaries.
- Timestamp parsing order:
  1. Numeric ints/floats (epoch seconds) — millisecond heuristics divide by 1000.
  2. ISO-8601 strings with or without timezone suffix.
  3. Common `YYYY/MM/DD HH:MM:SS` formats.
  4. SillyTavern metadata hints (`meta.timestamp`, `extensions.created`).
- Role hints: `is_user`, `is_bot`, `role`, and speaker name heuristics map to
  `meta.is_user` for the mapper.
- Roleplay `.txt` fallback uses regex patterns:
  - `[timestamp] Speaker: text`
  - `Speaker: text`
  - continuation lines append to the previous turn.
  Stage markers or empty lines reset the accumulator.

---

## Mapper heuristics (`comfyvn/importers/st_chat/mapper.py`)

- Segmentation: new scene when
  - session/chat ID changes (`meta.session` / `meta.chat_id`),
  - title changes (`meta.conversation_title`),
  - timestamp gaps exceed 90 minutes, or
  - explicit break markers (`meta.scene_break`, text exactly `---`, `***`, `===`).
- Node inference:
  - Player turns with `>` or `Choice:` prefixes become `choice` nodes; each
    bullet line becomes a `ChoiceOptionSpec` whose `next` pointer defaults to
    the following node.
  - All other turns become `line` nodes; an `end` node is appended automatically.
- Persona resolution:
  - Normalises speaker names (`slugify`, lowercase) and searches the provided
    alias map (`PersonaManager.list_personas()` → `id`, `name`, `display_name`,
    `short_name`).
  - Player turns fall back to `PersonaManager.state['active_persona']` when
    available.
  - Missing matches populate `meta.unresolved_personas[]` and emit warnings.
- Expression extraction: `[emote]`, ASCII emoji, Unicode emoji, and `*stage*`
  cues map to `LineNode.expression` plus `meta.annotations[<node>] = {stage:[]}`.
- Determinism: nodes are sequentially linked; `ChoiceOptionSpec.next` defaults to
  the following node ID to keep ScenarioRunner deterministic without branching
  metadata.

---

## Run artefacts

```
imports/<runId>/turns.json   # normalised transcript
imports/<runId>/scenes.json  # ScenarioSpec payloads (list of scenes)
imports/<runId>/preview.json # summary {scene_count, turn_count, participants}
imports/<runId>/status.json  # {phase, progress, warnings, preview, timestamps}
```

- Scenes are also saved to `data/scenes/<scene>.json` and appended to
  `data/projects/<projectId>.json` under `imports.st_chat[]` for history.
- Aggregated warnings bubble up via the REST response and `status.json` so GUI or
  CLI tooling can prompt for persona mapping or transcript fixes.

---

## Debug checklist

1. Enable DEBUG logging (`COMFYVN_LOG_LEVEL=DEBUG`) to capture phase markers:
   `comfyvn.server.routes.import_st` logs `phase=...` and artefact paths.
2. Run a smoke import:
   ```bash
   run_id=$(curl -s -X POST http://127.0.0.1:8001/api/import/st/start \
     -F projectId=debug-import \
     -F 'text=Aurora: Welcome back!\nYou: Choice: Ask about the relic\nYou: > Leave camp' \
     | jq -r '.runId')
   curl -s "http://127.0.0.1:8001/api/import/st/status/${run_id}" | jq
   ```
3. Inspect `imports/${run_id}/status.json` — expect `phase"completed"` and
   warnings list (empty when personas resolve cleanly).
4. Verify scenes landed under `data/scenes/` and are referenced in
   `data/projects/<projectId>.json`.
5. Subscribe to hooks (WebSocket):
   ```bash
   websocat ws://127.0.0.1:8001/api/modder/hooks/ws \
     | jq 'select(.event | test("on_st_import_(started|scene_ready|completed|failed)"))'
   ```
6. Run unit tests: `pytest tests/test_st_importer.py` — covers parser heuristics,
   mapper output, and REST workflow with temporary storage roots.
7. Checker: `python tools/check_current_system.py --profile p9_st_import_pipeline`.

---

## Follow-ups / open tasks

- Persona auto-matching from `/api/persona/map` (currently manual) — evaluate
  caching persona aliases per project to reduce unresolved warnings.
- Optional diff view comparing imported transcript vs generated scene for QA.
- GUI integration: expose run history in Studio Import tab once importer flag
  is promoted to default-on.
