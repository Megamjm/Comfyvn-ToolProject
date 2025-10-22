# P6 — Image→Persona Analyzer

> Feature flag: `features.enable_image2persona` (defaults **false**). Keep the flag off until the modder/QA lane verifies pipelines and hashes.  
> Checker: `python tools/check_current_system.py --profile p6_image2persona --base http://127.0.0.1:8001`

## Intent

Turn 1–N reference images into structured Persona hints: appearance tags, color palette, pose anchors, expression prototypes, and downstream style/LoRA suggestions. The analyzer is deterministic (hash-stable) so assets can be versioned, diffed, and merged with the Persona schema and provenance logs.

## Pipeline Overview

1. **Normalization** – Each image is EXIF-transposed and converted to RGB before hashing (`sha1(version + dims + bytes)`) to guarantee stable digests and provenance sidecars.  
2. **Palette extraction** – RGB median-cut quantization (5–8 swatches) produces normalized swatches (`hex`, `rgb`, `luma`, `ratio`, `name`). Sorting favours coverage, then hex to keep output stable across runs.  
3. **Appearance tagging** – Heuristics derive `species`, `fur_skin`, `colorways`, `accent_colors`, and `clothing_motifs` from palette statistics (with optional contributor overrides via hooks).  
4. **Pose anchors** – A grayscale percentile mask estimates a subject bounding box; anchors are emitted for face, hands, and feet with normalized coordinates and confidence scores.  
5. **Expression prototypes** – Brightness/contrast metrics seed a neutral baseline plus optional `smile`, `soft_smile`, and `anger` prototypes. Each carries mood, trigger hints, and average confidence.  
6. **Style fusion** – Appearance tags feed `StyleSuggestionRegistry`, returning studio-friendly style hints plus optional LoRA names (names only, no URLs/downloads).  
7. **Merge** – Multiple images merge through weighted averages. Conflicts (e.g., disagreeing `species` or `primary_color`) are surfaced for review.

The top-level summary lives under `metadata.image2persona` when merged into a Persona profile and includes:

```json
{
  "appearance": {...},
  "palette": [...],
  "pose_anchors": {...},
  "expression_set": {...},
  "style": {
    "styles": [{"id": "studio-portrait-soft", "priority": 0.6}],
    "lora": [{"name": "portraitplus-v15", "priority": 0.55}],
    "applied_tags": ["species:human", "clothing:minimalist"]
  },
  "conflicts": [{"field": "appearance.species", "values": ["human", "unspecified"]}]
}
```

## Python API

```python
from comfyvn.persona.image2persona import (
    analyze_images,
    ImagePersonaAnalyzer,
    PersonaImageOptions,
)

sources = ["./persona_refs/front.png", "./persona_refs/profile.png"]
options = PersonaImageOptions(debug=True)
suggestion = analyze_images(sources, persona_id="heroine-01", options=options)

print(suggestion.summary["appearance"]["colorways"])
# ['primary:warm:orange', 'secondary:neutral:stone', 'accent:cool:teal']

profile = {}
analyzer = ImagePersonaAnalyzer(options)
merged_profile = analyzer.merge_into_persona_profile(profile, suggestion)
```

- `PersonaImageOptions.hooks` accepts optional callables (`appearance`, `palette`, `anchors`, `expressions`, `summary`) for modder overrides. Each hook receives the current payload and can return replacements/patches.  
- `options.debug=True` attaches `metrics`, palette tokens, and anchor boxes to each per-image report for tooling dashboards.  
- Output is fully JSON serializable; call `suggestion.as_json(indent=2)` to persist snapshots for reviews.

## Style & LoRA Suggestions

`comfyvn/persona/style_suggestions.py` ships a baseline registry. Contributors can extend it:

```python
from comfyvn.persona.style_suggestions import StyleSuggestionRegistry

registry = StyleSuggestionRegistry.default()
registry.register_style("species:android", "hard-light-cyberpunk", 0.7)
registry.register_lora("colorway:accent:cool:teal", "cyan-rim-v12", 0.5)

options = PersonaImageOptions(style_registry=registry)
```

The analyzer only surfaces names; downstream fetchers are intentionally out-of-scope.

## Debugging & Determinism

- Hashes include the analyzer version string (`p6.image2persona.v1`). Bumping the algorithm requires updating `ANALYZER_VERSION` and documenting changes in the changelog.  
- `conflicts` enumerate mismatched attributes so producers can reconcile persona packs manually.  
- Enable `LOG_LEVEL=DEBUG` and wrap extractor calls to log `suggestion.provenance` for QA pipelines.  
- Smoke tests: feed the same image set twice and assert identical `summary_digest` values. Mix formats (PNG/JPEG/WebP) to confirm EXIF normalization.

## Integration Notes

- Persona Manager consumers should treat `metadata.image2persona` as advisory data. Leave canonical persona fields (`name`, `expression`, `poses`) unchanged unless the user confirms merges.  
- GUI/CLI panels can surface the palette and anchor previews by reading `PersonaSuggestion.per_image[*].debug` when debug mode is enabled.  
- Feature flag stays off until `p6_image2persona` checker passes (docs, files, flag defaults, API surface).

