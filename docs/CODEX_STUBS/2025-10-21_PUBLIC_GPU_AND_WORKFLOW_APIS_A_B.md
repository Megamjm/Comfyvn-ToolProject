# Public GPU & Workflow APIs — A/B

**Updated:** 2025-10-27  
**Owner Chat:** Platform Integration / Compute Advisor

---

## 1. Snapshot — How things work today
- Provider registry lives in `comfyvn/compute/providers.py`, persisting curated entries to `config/compute_providers.json` and seeding from `comfyvn.json`. GUI + REST (`/api/providers/*` in `comfyvn/server/routes/providers.py`) already expose health/quotas/templates and bootstrap jobs for RunPod & unRAID.
- Remote workflows lean on task runners (`TaskRegistry`, `/api/providers/bootstrap`) and the compute advisor (`/api/gpu/advise`) to annotate jobs with cost/VRAM hints. Changelog `2025-10-20` and docs (`docs/remote_gpu_services.md`, `docs/compute_advisor_integration.md`) describe the heuristics.
- Public adapters currently ship as dry-run stubs under `comfyvn/public_providers/`. Only `gpu_runpod.py` exists; it returns deterministic mock IDs while reading secrets from `config/comfyvn.secrets.json` via `provider_secrets`.
- There is no dedicated `/api/providers/gpu/*` route layer yet. Integration points for modders/debuggers live in `docs/dev_notes_modder_hooks.md` (scheduler, asset registry, bridge APIs) but lack GPU-specific hooks.

## 2. Intent recap
**A) Choice mode:** expose adapter stubs that let authors explicitly pick a provider, validate credentials, and call `submit(job) -> {id}` without dispatching real workloads when secrets are absent.  
**B) Sim mode:** model the full handshake (`submit -> poll -> artifacts/logs`) with seeded narration so Preview/Advisor flows can exercise deterministic branches while the runtime/runner chooses the actual branch later.

## 3. Implementation outline
1. **Adapter modules (`comfyvn/public_providers/`):**
   - `gpu_runpod.py` (already stubbed) → keep dry-run defaults, add logging hook to surface job payload in debug mode.
   - New stubs: `gpu_hf_endpoints.py`, `gpu_replicate.py`, `gpu_modal.py`. Each should:
     - Merge secrets via `provider_secrets("<slug>")`.
     - Implement `health(cfg=None)`, `submit(job, cfg=None)`, `poll(job_id, cfg=None)` returning deterministic dry-run payloads when secrets are missing.
     - Mirror provider-specific config hints (base URL, region, hardware profile) so downstream advisor logic can seed defaults.
     - Emit structured debug logs on submit/poll when `COMFYVN_LOG_LEVEL=DEBUG`.
2. **Route scaffolding (`comfyvn/server/routes/providers_gpu.py`):**
   - Mount under `/api/providers/gpu`; expose:
     - `POST /health` → `{ok, dry_run?, reason?}` by delegating to requested adapter.
     - `POST /submit` → returns `{ok, id, dry_run}`.
     - `GET /poll/{id}` → returns `{ok, status, artifacts[], logs[], dry_run}`.
     - `GET /providers` → enumerate available adapters + required secret keys (for GUI forms).
   - Reuse the existing `provider_secrets` helper and guard against missing secrets (never throw 500; always surface deterministic dry-run results).
   - Add minimal tests mirroring `tests/test_providers_api.py`, exercising dry-run flows.
3. **Compute advisor wiring:**
   - Extend advisor heuristics to recognise the new adapters (map provider slug → adapter module). When remote jobs are simulated (`dry_run`), attach `decision["dry_run"]=True` so Studio surfaces “mock” badges.
   - Update `comfyvn/core/provider_profiles.py` to add entries for RunPod, Hugging Face Inference Endpoints, Replicate, and Modal with pricing snapshots (see pricing refs in work order) and required auth fields.
   - Ensure `/api/gpu/advise` (or new `/api/providers/gpu/simulate`) can seed narration/log lines when running in Sim mode.
4. **Secrets handling:**
   - Document the expected structure of `config/comfyvn.secrets.json`:
     ```jsonc
     {
       "runpod": {"api_key": "RP_..."},
       "huggingface": {"api_key": "hf_..."},
       "replicate": {"api_token": "r8_..."},
       "modal": {"token_id": "...", "token_secret": "..."}
     }
     ```
   - Add schema snippet to `docs/tool_installers.md` or a new `docs/config/secrets.md`.

## 4. Documentation / changelog touch points
- **architecture.md:** add a section beneath Remote GPU services describing the public provider shim (`public_providers/*`), the dry-run contract, and how compute advisor integrates. Call out the single-shape job contract (`submit -> poll -> artifacts/logs`).
- **architecture_updates.md:** log the addition of `/api/providers/gpu/*`, enumerating how RunPod / HF / Replicate / Modal stubs behave and when real network calls will be plugged in.
- **README.md:** add a short “Remote GPU dry-run adapters” paragraph in the Scheduler & Cost Telemetry or Compute sections, including instructions for `config/comfyvn.secrets.json`.
- **CHANGELOG.md:** draft an entry (dated when we land this) highlighting the new API surface and dry-run diagnostics, referencing the new docs + tests.
- **docs/dev_notes_modder_hooks.md:** append a subsection under Scheduler or API surfaces covering:
  - Endpoints exported by `providers_gpu.py`.
  - Example cURL for dry-run submit/poll.
  - Pointers to the deterministic log outputs and how modders can inject custom job payloads.
- **Docs channel drop (internal):** add a brief Development Note summarising the adapter expectations, secrets layout, and how to enable verbose logging for remote provider simulations.

## 5. Debug & modder hooks checklist
- Provide a structured log channel (`logs/providers_gpu.log`) by adding a dedicated logger in the new route; include job payload, provider slug, dry-run flag, simulated latency.
- Expose `POST /api/providers/gpu/simulate` (optional) that accepts `{provider, job, seed}` and returns `{transcript: [ ... narration lines ... ], decision}` so Story/Battle layers can visualise outcomes without enqueuing real jobs.
- Extend the existing `TaskRegistry` job metadata to include `dry_run`, `provider_slug`, and `public_adapter` fields for downstream automation.
- Surface adapter availability in the Studio **Compute** view: list dry-run readiness, highlight missing secrets, and offer “Copy sample secrets JSON” action for contributors.
- Update `docs/remote_gpu_services.md` to reference the new stubs and clarify which providers are live vs. dry-run.

## 6. Acceptance / QA notes
- `POST /api/providers/gpu/submit` with secrets absent → deterministic `{ok:false,dry_run:true,reason:"missing token"}`.
- `POST /api/providers/gpu/submit` with mock secrets → `{ok:true,id:"mock-<provider>-seed"}` and poll returns `{status:"done", artifacts:[], logs:["Simulated completion"], dry_run:true}`.
- Minimal unit tests cover `health/submit/poll` for each adapter, ensuring secrets fallback works.
- Regression: existing `/api/providers/*` routes continue to operate; compute advisor still resolves RunPod/Unraid via legacy path.

## 7. Open questions / follow-ups
- When do we flip from dry-run to live API calls? Need timelines per provider + rate-limit handling plan.
- Do we surface cost estimates per provider in the dry-run payload (pull static pricing tables vs. fetched catalog)?
- Should we add webhook simulation (e.g., RunPod job status callbacks) before real integration?
- Coordinate with GUI team on how “Sim mode” narration should appear in the Scheduler Board / Compute view.

## 8. Documentation deliverables checklist
- **README.md** → add “Public GPU dry-run adapters” section (link to new APIs, mention secrets file and dry-run guarantees).
- **architecture.md** → expand the Remote GPU chapter with the unified `submit -> poll -> artifacts/logs` contract and the new `providers_gpu` router.
- **architecture_updates.md** → log the feature with context: adapters, dry-run guarantees, future live integration path.
- **CHANGELOG.md** → entry describing the new `/api/providers/gpu/*` surface, secrets handling, and dry-run tests.
- **docs/dev_notes_modder_hooks.md** → new subsection under Scheduler/API that documents cURL examples, dry-run payloads, log locations.
- **docs/remote_gpu_services.md** → tag RunPod/HuggingFace/Replicate/Modal as “public adapters (dry-run)” with pricing snapshot updates.
- **Docs channel post** → summarize what changed, why dry-run mode exists, and where to find logs/secrets template.
- **config/comfyvn.json** → add feature flag `enable_public_gpu_adapters` (default `false`) so external builds ship disabled.
- **Docs samples** → include `config/comfyvn.secrets.json.sample` snippet showing key names for each provider.
- **Tests** → mention new `tests/test_public_gpu_adapters.py` verifying deterministic IDs and dry-run flags.

## 9. Debug & verification (embed in PR description)
```
- [ ] Docs updated: README, architecture, CHANGELOG, /docs notes (what changed + why)
- [ ] Feature flags: added/persisted in config/comfyvn.json; OFF by default for external services
- [ ] API surfaces: list endpoints added/modified; include sample curl and expected JSON
- [ ] Modder hooks: events/WS topics emitted (e.g., on_scene_enter, on_asset_saved)
- [ ] Logs: structured log lines + error surfaces (path to .log)
- [ ] Provenance: sidecars updated (tool/version/seed/workflow/pov)
- [ ] Determinism: same seed + same vars + same pov ⇒ same next node
- [ ] Windows/Linux: sanity run on both (or mock mode on CI)
- [ ] Security: secrets only from config/comfyvn.secrets.json (git-ignored)
- [ ] Dry-run mode: for any paid/public API call
```

---

**Next steps:** implement stubs + routes, update documentation set above, then schedule a dev-channel note summarising dry-run usage for modders/contributors.
