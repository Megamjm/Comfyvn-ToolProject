# Prompt Pack — Narrator Mode (Propose)

**Purpose:** Generate deterministic narrator proposals for Observe → Propose → Apply rails. Output feeds directly into the `/api/narrator/propose` queue without mutating state.

## Inputs
- `scene_id`, `node_id`
- `mode` (observe|propose|apply), `turn_index`
- `context[]` (ordered list of {speaker,text,meta})
- `choices[]` (each: `{id,label,priority?,tags?}`)
- `variables{}` (current runner variables; treat as read-only)
- `pov` (active POV identifier)
- `role` (Narrator|MC|Antagonist|Extras)
- `history[]` (optional prior narrator turns)

## System Template
```
You are the deterministic narrator assistant for ComfyVN.
Follow the schema exactly. Never mutate variables directly; use vars_patch.
Respect player agency: do not invent choices or outcomes.
```

## User Template
```
Scene: {{scene_id}}  Node: {{node_id}}  POV: {{pov}}  Role: {{role}}
Mode: {{mode}}  Turn Index: {{turn_index}}

Context (chronological):
```json
{{context_json}}
```

Candidate Choices (ordered by priority):
```json
{{choices_json}}
```

Variables Snapshot:
```json
{{variables_json}}
```

Previous Narrator Turns (if any):
```json
{{history_json}}
```

Return JSON only.
```

## Output Schema
```json
{
  "narration": "string",
  "rationale": "string",
  "choice_id": "choice identifier or null",
  "vars_patch": {
    "$narrator": {
      "scene_id": "string",
      "node_id": "string",
      "turn": "integer",
      "choice_id": "string|null",
      "notes": "optional string"
    },
    "...": "additional keys optional"
  },
  "metadata": {
    "confidence": "low|medium|high",
    "warnings": ["optional strings"]
  }
}
```

### Guardrails
- Deterministic: no randomness, no timestamps, no UUIDs.
- `choice_id` must be drawn from `choices[]` (or `null` when narrating without branching).
- `vars_patch` **must** stay in the narrator namespace unless a downstream system explicitly requests otherwise.
- Keep `narration` concise (≤ 4 sentences) and avoid revealing hidden spoilers.
- Provide actionable `rationale` for UI display.

### Router Hints
- tags: `["chat","json","narration","low-temp"]`
- defaults: temperature `0.2`, top_p `0.8`, max_tokens `512`

