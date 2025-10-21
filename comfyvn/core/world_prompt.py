"""Utilities for translating world lore into ComfyUI-friendly prompts."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class PromptTraceEntry:
    path: str
    value: str
    reason: str


@dataclass
class WorldPromptResult:
    prompt: str
    trace: List[PromptTraceEntry]


DEFAULT_TEMPLATE = (
    "{location_summary}\n"
    "Tone: {tone}\n"
    "Visual Motifs: {motifs}\n"
    "Story Hooks: {hooks}\n"
    "Rules: {rules}\n"
)


def build_world_prompt(
    world: Dict,
    *,
    location_id: Optional[str] = None,
    include_rules: bool = True,
    hook_count: int = 2,
) -> WorldPromptResult:
    """Generate a narrative prompt and tracing information from world data."""

    trace: List[PromptTraceEntry] = []
    tone = world.get("tone") or world.get("summary", "")
    if tone:
        trace.append(PromptTraceEntry(path="tone", value=tone, reason="World tone"))

    rules = _format_rules(world.get("rules", {})) if include_rules else ""
    if rules:
        trace.append(PromptTraceEntry(path="rules", value=rules, reason="World rules"))

    motifs = _compile_motifs(world.get("rules", {}))
    if motifs:
        trace.append(
            PromptTraceEntry(
                path="rules.visual_motifs", value=motifs, reason="Visual motifs"
            )
        )

    location = _select_location(world.get("locations", {}), location_id)
    location_summary_raw = location.get("summary", "")
    location_name = location.get("name", "") or location.get("id", "")
    location_summary = location_summary_raw
    if location_name and location_summary_raw:
        location_summary = f"{location_name} — {location_summary_raw}"
    if location_summary:
        trace.append(
            PromptTraceEntry(
                path=f"locations.{location.get('id', location_id or 'unknown')}.",
                value=location_summary,
                reason="Active location summary",
            )
        )

    hooks = location.get("story_hooks", [])
    hooks_text = _format_hooks(hooks, hook_count)
    if hooks_text:
        trace.append(
            PromptTraceEntry(
                path="locations.story_hooks",
                value=hooks_text,
                reason="Story hooks",
            )
        )

    template = (world.get("prompt_templates") or {}).get("base", DEFAULT_TEMPLATE)
    prompt = template.format(
        location_summary=location_summary,
        tone=tone,
        motifs=motifs or "",
        hooks=hooks_text,
        rules=rules,
        location_name=location_name,
    ).strip()

    prompt = textwrap.dedent(prompt).strip()
    return WorldPromptResult(prompt=prompt, trace=trace)


def _select_location(locations: Dict[str, Dict], location_id: Optional[str]) -> Dict:
    if location_id and location_id in locations:
        selection = dict(locations[location_id])
        selection["id"] = location_id
        return selection
    if locations:
        key, value = next(iter(locations.items()))
        selection = dict(value)
        selection["id"] = key
        return selection
    return {
        "id": "unknown",
        "name": "Unknown",
        "summary": "A nondescript space awaiting description.",
        "story_hooks": [],
    }


def _format_rules(rules: Dict[str, str]) -> str:
    if not rules:
        return ""
    fragments = []
    for key, value in rules.items():
        pretty_key = key.replace("_", " ").title()
        fragments.append(f"{pretty_key}: {value}")
    return " | ".join(fragments)


def _compile_motifs(rules: Dict[str, str]) -> str:
    if isinstance(rules, dict):
        motifs = rules.get("visual_motifs")
        if isinstance(motifs, list):
            return ", ".join(motifs)
    return ""


def _format_hooks(hooks: List[str], count: int) -> str:
    if not hooks:
        return ""
    selected = hooks[:count] if count > 0 else hooks
    return " | ".join(selected)
