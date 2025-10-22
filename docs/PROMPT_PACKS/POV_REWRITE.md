# Prompt Pack — POV Rewrite

**Purpose:** Rephrase a node’s narration from a chosen character’s perspective **without changing plot facts**.

## Inputs
- `scene_id`, `node_id`
- `pov` (character id)
- `canonical_node` { text, stage_directions, choices[] }
- `world_lore[]`, `character_sheet[pov]`, `vars{}`, `seed`

## System Template
```
You are a VN narration rewriter. Keep plot facts identical. Output STRICT JSON matching the schema. Do not invent choices or events.
```

## User Template
```
Rewrite this node from POV = "{{pov}}".
Return JSON only.

Context:
- Scene: {{scene_id}} Node: {{node_id}}
- Canonical Node: ```{{canonical_node_json}}```
- Character Sheet ({{pov}}): ```{{character_sheet_json}}```
- World Lore: ```{{world_lore_json}}```
- Vars: ```{{vars_json}}```
- Seed: {{seed}}
```

## Output Schema (strict)
```json
{
  "narration": "string",
  "internal_monologue": "string",
  "observations": ["string"],
  "visible_choices": ["choice_id"],
  "style": {"tone":"string","register":"first_person|third_limited"}
}
```

### Guardrails
- No new facts, no new characters.
- `visible_choices` must be a subset of canonical choices filtered by POV.
- Target 500–1200 characters overall.

### Router Hints
- tags: `["chat","worldbuild","json","long-context"]`
- defaults: temperature `0.3`, top_p `0.9`, max_tokens approximately `700`
