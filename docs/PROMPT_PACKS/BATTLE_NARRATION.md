# Prompt Pack — Battle Narration (Choice & Sim)

**Purpose:** Produce a short, cinematic log for a battle. The runner decides the outcome; the LLM only narrates.

## Modes
- **choice**: user/author chose a winner → narrate consistent beats.
- **sim**: engine determines outcome using odds; you narrate to match.

## Inputs
- `pov`, `fighters[{id, name, style, hp, tags}]`, `env{location, weather}`
- `chosen_outcome` (optional), `odds_summary` (optional)
- `style_guide` (short!), `seed`

## System Template
```
You write brief battle beats in present tense. Do not change the outcome. JSON ONLY.
```

## User Template
```
Write a 4–8 beat battle log.
POV: {{pov}}
Fighters: ```{{fighters_json}}```
Environment: ```{{env_json}}```
ChosenOutcome: {{chosen_outcome_or_null}}
Odds: ```{{odds_json_or_empty}}```
Style: ```{{style_guide}}```
Seed: {{seed}}
```

## Output Schema
```json
{
  "outcome": "A|B|draw",
  "beats": [
    {"speaker":"narrator|fighter_id","text":"string","sfx":"optional"},
    {"speaker":"...", "text":"..."}
  ],
  "vars_patch": {"battle_outcome":"A"},
  "next_choice_hint": "choice_id_or_null"
}
```

### Guardrails
- 4–8 beats, fewer than 800 characters total.
- Don’t invent weapons/skills beyond tags.
- `vars_patch.battle_outcome` must match `outcome`.

### Router Hints
- tags: `["chat","json","roleplay"]`
- defaults: temperature `0.5`, max_tokens approximately `500`
