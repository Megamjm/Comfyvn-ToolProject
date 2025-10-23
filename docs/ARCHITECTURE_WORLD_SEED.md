# World Seed (v0.5)
- Schemas define contracts for world, scene, timeline, and asset metadata.
- Worlds live under `data/worlds/<id>/`.
- Renders + sidecars live under `exports/assets/worlds/<id>/<type>/`.
- Everything here ships CC0 unless sidecars specify otherwise.
- ComfyUI connector jobs that include `metadata.asset_pipeline` will copy PNG/WAV outputs into the export tree, stamp schema-valid sidecars, and refresh `exports/assets/worlds/<id>/meta/assets_index.json`.

Integration:
- SillyTavern: use `/examples/*.md` as conversation starters.
- LM Studio: feed scene prompts + world summary to chain JSON mutations.
- Ren'Py export: consume scene beats + asset slugs to build scripts.
