# Dev Notes — Image→Persona Hooks & QA

Scope: P6 Image→Persona tooling (`comfyvn/persona/image2persona.py`, `style_suggestions.py`)

## Modder Hooks

- **Appearance overrides** — provide `PersonaImageOptions(hooks={"appearance": your_callable})`. Callable receives `image` (PIL.Image), `palette` (list of swatches), and should return a dict overriding `species`, `fur_skin`, `colorways`, etc.  
- **Palette overrides** — `hooks["palette"]` can reorder/replace the generated swatches (list of dicts with `hex`, `rgb`, `ratio`, `luma`, `name`). Return value should mirror the original schema.  
- **Pose anchor overrides** — `hooks["anchors"]` receives the current anchor payload and can add/extreplace additional anchors (e.g., `elbow`, `tail`).  
- **Expression overrides** — `hooks["expressions"]` can inject detector output (blink probability, smile score). Pass `appearance` and `anchors` for context.  
- **Summary override** — `hooks["summary"]` receives the merged summary and per-image reports before hashing. Use this to inject QA metrics or mark manual adjustments.

Hook call order: palette → appearance → anchors → expressions → summary. All hooks execute prior to constructing the provenance digest to keep hashes stable.

## Style Registry Extensions

- `StyleSuggestionRegistry` keeps per-tag lists of `(style_id, weight)` and `(lora_name, weight)`. Use `register_style/register_lora` to extend or override defaults.  
- Weights act as priority hints (0.0–1.0). Highest weight wins when multiple tags collide; ties resolve alphabetically for determinism.

## QA Recommendations

- Run `python tools/check_current_system.py --profile p6_image2persona --base http://127.0.0.1:8001` after wiring routes/flags.  
- Add smoke snapshots to your project: serialize `suggestion.as_json(indent=2)` to `provenance/image2persona/<persona_id>.json` and commit the digest for diffable reviews.  
- Confirm repeatability: feed the same images twice and assert the `summary.provenance["summary_digest"]` value is unchanged.  
- Mixed-format test: `["front.png", "profile.jpg", "pose.webp"]`. Ensure EXIF transpose does not alter the hash order.  
- Conflict detection: purposely mix human and beastfolk references; `summary["conflicts"]` should flag `appearance.species`.  
- For anchor QA, log `PersonaSuggestion.per_image[*].anchors["bounding_box"]` and overlay normalized coordinates in UI tooling.

## Open Items

- Optional: integrate third-party taggers (CLIP, DeepDanbooru) behind the appearance hook. Please record dependencies and licensing before enabling by default.  
- Optional: export palette previews to `/tmp/image2persona/<digest>.png` during debug runs.  
- Optional: expose REST endpoints (`/api/persona/images/analyze`, `/api/persona/images/unify`) once backend wiring lands; reuse the analyzer to stay deterministic.

