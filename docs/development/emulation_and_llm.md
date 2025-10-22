# Character Emulation & LLM Proxy Notes

These notes collect the hooks modders and tooling chats can reuse when wiring
the SillyCompatOffload emulation engine, prompt packs, and LLM adapter proxy.

## Feature Flag

- Toggle the engine via `features.silly_compat_offload` in `config/config.json`
  or set `COMFYVN_SILLY_COMPAT_OFFLOAD=1` before launching the backend.
- When disabled the `/api/emulation/*` routes return status only and skip
  adapter calls so SillyTavern installs stay unaffected.

## Emulation Engine (`/api/emulation/*`)

- `GET /api/emulation/status` → snapshot of the feature flag plus cached persona
  state (memory, style guides, safety metadata).
- `POST /api/emulation/toggle` with `{ "enabled": true }` → persist the
  SillyCompatOffload flag.
- `POST /api/emulation/persona` with `{persona_id, memory?, style_guides?,
  safety?, metadata?}` → seed persona context; history is capped to 20 turns.
- `POST /api/emulation/chat` expects OpenAI-style `messages` and optional
  `{module, provider, model, options}` overrides. Responses proxy through the
  shared LLM registry and return `{reply, usage, metadata}`.

## LLM Proxy (`/api/llm/*`)

- `GET /api/llm/registry` → aggregated provider metadata, defaults, and the
  SillyCompatOffload flag state.
- `GET /api/llm/runtime` / `POST /api/llm/runtime/register` /
  `DELETE /api/llm/runtime/{id}` → manage in-memory adapters for experiments
  without touching disk.
- `POST /api/llm/test-call` → adapter dry-run helper. Accepts the same
  overrides as the emulation engine and echoes structured replies (or the stub
  fallback) so CI and GUI panels stay deterministic.
- TODO: `/api/llm/chat` and `/api/llm/prompt-pack/{module}` remain unshipped;
  progress captured in `docs/CODEX_STUBS/2025-10-21_PUBLIC_LLM_ROUTER_AND_TOP10_A_B.md`.

## Prompt Packs & Recommendations

- Prompt templates will live in `comfyvn/models/prompt_packs/<module>.md` once the public router ships; track spec updates in the public LLM router stub.
- Module defaults (provider/model/options) are versioned in
  `comfyvn/models/registry.json`; update both when swapping adapters.
- `docs/LLM_RECOMMENDATIONS.md` summarises starter temperatures, top_p values,
  and notes for each module (Translate, VN Chat, Narrator, Worldbuild,
  CharacterInfo, Manga OCR, ST Bridge).

## Debugging Hooks

- Raise verbosity with `COMFYVN_LOG_LEVEL=DEBUG` to surface adapter requests and
  persona history updates.
- Emulation history is stored in-memory only; call `GET /api/emulation/status`
  to inspect the cached turns when tuning prompts.
- Registry changes require no restart—update `comfyvn/models/registry.json` and
  call `comfyvn.models.registry.refresh_registry()` (or bounce the process) to
  reload providers.
