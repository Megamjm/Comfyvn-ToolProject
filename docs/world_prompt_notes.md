# World Lore Prompt Notes

This note documents how the default **AuroraGate Transit Station** lore is interpreted when building prompts for ComfyUI.

## Locating key details

- **Primary setting**: The loader chooses `locations.concourse` by default because it is the first registered location. Its summary, sensory descriptors, and story hooks become the backbone of the prompt.
- **Tone**: Pulled from the top-level `tone` field (`"Hopeful science-fantasy…"`). If that value is missing, we fall back to the world `summary`.
- **Rules**: Combined from the `rules` dictionary into a single line: technology level, energy rules, narrative focus, and visual motifs. Visual motifs are also extracted separately so the ComfyUI prompt can call them out for rendering.
- **Story hooks**: We surface the first two hooks to give the image generation pipeline optional narrative beats (e.g., *“A courier drops a prism-drive…”*).

## Example prompt output

```
AuroraGate Transit Station — Main Concourse. A cathedral-like hall with layered glass walkways and suspended kiosks... (truncated)
Tone: Hopeful science-fantasy with grounded technology...
Visual Motifs: glass promenades washed in teal and magenta, holographic koi swimming through weightless gardens, fractured sunlight refracted by orbiting aurora panels
Story Hooks: A courier drops a prism-drive that hums with encrypted coordinates. | A diplomatic envoy requests a quiet corner to negotiate a ceasefire.
Rules: Technology Level: Post-scarcity nanofabrication mixed with artisanal craftsmanship. | Energy Rules: Station-wide power routed through aurora siphons; surges can cause chromatic storms. | Narrative Focus: Character-driven encounters that reveal secrets through dialogue and environmental cues.
```

The trace returned by `build_world_prompt` records how each fragment is selected so downstream consumers can audit or adjust the prompt at run time.
