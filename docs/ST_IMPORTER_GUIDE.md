# SillyTavern Chat Import Pipeline

Updated: 2025-10-21 • Scope: Phase 9 Project Integration Chat importer

The ST chat importer converts exported SillyTavern transcripts into
ComfyVN scenario graphs. It understands both `.json` archives and plain
roleplay `.txt` logs, segments long conversations into scenes, maps
speakers onto existing personas, and writes the generated content to the
standard project folders so Mini-VN previews (and downstream tooling)
can pick them up immediately.

The feature is guarded by the `features.enable_st_importer` flag in
`config/comfyvn.json`; leave it disabled in production builds until
consent and privacy steps are completed.

---

## 1. Exporting chats from SillyTavern

1. Open the target chat session in SillyTavern and use the built-in
   export panel.
2. Preferred format: **JSON** (includes timestamps, author metadata, and
   SillyTavern extensions). The importer also accepts the Roleplay text
   format when JSON is unavailable.
3. Ensure the transcript only contains messages you have permission to
   reuse. The importer copies the raw transcript into
   `imports/<runId>/turns.json` for auditing.
4. If the transcript contains private or third-party content, scrub it
   before uploading; ComfyVN does not attempt to redact personal data.

### Privacy & consent

The importer preserves the raw payload for debugging, so treat
`imports/<runId>/turns.json` and `logs/server.log` as sensitive. When
working with third-party or community content, collect explicit consent
before running the pipeline and store the consent artefacts alongside
the transcript for future reference.

---

## 2. API overview

### 2.1 Start an import run

```
POST /api/import/st/start
Content-Type: multipart/form-data

Fields:
  projectId (required) – existing or new project identifier
  file      (optional) – upload a SillyTavern .json or .txt export
  text      (optional) – paste inline transcript text/JSON
  url       (optional) – fetch the transcript from an HTTP(S) endpoint

Exactly one of file/text/url must be supplied.
```

Sample curl using inline text:

```bash
curl -s -X POST http://127.0.0.1:8001/api/import/st/start \
  -F projectId=demo_project \
  -F 'text=Aurora: Welcome\nYou: Choice: Ask about relic\nYou: > Leave' | jq
```

The endpoint returns:

```jsonc
{
  "ok": true,
  "runId": "9d58…",
  "sceneCount": 2,
  "warnings": ["Unresolved persona: Guide"],
  "status": {
    "phase": "completed",
    "progress": 1.0,
    "scenes": ["demo-project-scene-001", "demo-project-scene-002"],
    "preview": "imports/9d58…/preview.json"
  }
}
```

During the run a status file is updated with progress markers:

| Phase       | Meaning                                   |
|-------------|-------------------------------------------|
| initializing| Run folder created, inputs staged         |
| parsed      | Transcript normalised to uniform turns    |
| mapped      | Scenario nodes generated, warnings logged |
| completed   | Scenes saved, project metadata refreshed  |
| failed      | Fatal error; `status.error` holds details |

### 2.2 Poll run status

```
GET /api/import/st/status/{runId}
```

Returns progress, generated scenes (with full payloads), aggregated
warnings, and the cached preview summary.

---

## 3. Scenario mapping heuristics

The mapper (`comfyvn/importers/st_chat/mapper.py`) applies the
following rules to flatten the transcript into scenario nodes:

- **Segmentation:** Conversation titles and long gaps (> 90 min) start a
  new scene. Explicit markers (`scene_break` metadata or `--- / ***` rows)
  also trigger a split.
- **Persona mapping:** Speaker names are normalised (slug + lowercase)
  and matched against known personas (`PersonaManager.list_personas()`).
  Player turns inherit the active persona ID when available. Missing
  matches are reported in the scene’s `meta.unresolved_personas` list.
- **Choices:** Player messages starting with `>` or `Choice:` yield a
  `choice` node. Consecutive bullet lines are converted into individual
  options that branch to the next node in the sequence.
- **Expressions:** Inline `[emotion]` tags, emoji, and stage directions
  (e.g. `*sigh*`) map to `LineNode.expression` and `meta.annotations`.
  Cleaned text retains stage cues in parentheses when they are the only
  content.
- **Deterministic linking:** Nodes are sequential, with a closing
  `end` node appended so ScenarioRunner and Mini-VN can step through the
  transcript deterministically.

### Output folders

```
imports/<runId>/turns.json   Raw, normalised transcript
imports/<runId>/scenes.json  Scenario payloads used to build the project
imports/<runId>/preview.json High-level summary (scene count, participants)
imports/<runId>/status.json  Progress + warnings + timestamps
```

Generated scenes are also written to `data/scenes/<sceneId>.json` and
referenced from `data/projects/<projectId>.json → imports.st_chat[]` so
downstream tooling can surface the history.

---

## 4. Modder hooks & debug signals

Four Modder Hook events broadcast importer activity:

| Event                      | Payload summary                                  |
|----------------------------|---------------------------------------------------|
| `on_st_import_started`     | `{run_id, project_id, source, timestamp}`         |
| `on_st_import_scene_ready` | `{run_id, project_id, scene_id, title, participants, warnings}` |
| `on_st_import_completed`   | `{run_id, project_id, scene_count, warnings, status, preview_path}` |
| `on_st_import_failed`      | `{run_id, project_id, error, timestamp}`          |

Consume these via `/api/modder/hooks/ws` or straight from
`comfyvn.core.modder_hooks` to stream progress into dashboards or CI
pipelines. The importer logs structured breadcrumbs under
`comfyvn.server.routes.import_st` at DEBUG level; set
`COMFYVN_LOG_LEVEL=DEBUG` during development for verbose traces.

---

## 5. Troubleshooting

- **Empty output:** Check `turns.json` to confirm the transcript was
  parsed correctly. If it is empty, verify the export format and ensure
  the payload is valid JSON or roleplay text.
- **Missing personas:** Run `/api/persona/map` or update the Persona
  Manager so the importer can resolve speaker aliases. Warnings list the
  unresolved names.
- **Choice detection misfires:** Ensure player options are prefixed with
  `>` or `Choice:`. Mixed formatting may land in the line text instead of
  choice nodes.
- **Bridge imports:** When supplying a URL, the server fetches the
  payload with a 15s timeout. Failures surface as HTTP errors in
  `status.error` and `logs/server.log`.

See `tests/test_st_importer.py` for end-to-end samples and the new
`p9_st_import_pipeline` checker profile for required files/routes.
