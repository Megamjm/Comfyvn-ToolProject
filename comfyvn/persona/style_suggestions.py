from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


@dataclass(slots=True)
class StyleSuggestionRegistry:
    """Holds style and LoRA suggestions keyed by persona tags."""

    styles: Dict[str, List[Tuple[str, float]]] = field(default_factory=dict)
    loras: Dict[str, List[Tuple[str, float]]] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "StyleSuggestionRegistry":
        registry = cls()
        registry._load_defaults()
        return registry

    def _load_defaults(self) -> None:
        defaults = {
            "species:unspecified": [("baseline-portrait", 0.4)],
            "species:human": [("studio-portrait-soft", 0.6), ("drama-lighting", 0.35)],
            "species:beastfolk": [("anthro-detail", 0.7)],
            "colorway:primary:warm:red": [("cinematic-warm", 0.65)],
            "colorway:primary:cool:blue": [("noir-rim-light", 0.55)],
            "colorway:accent:warm:orange": [("rimlight-golden", 0.45)],
            "colorway:accent:cool:teal": [("split-tone-teal", 0.5)],
            "clothing:vibrant": [("fashion-editorial", 0.6)],
            "clothing:muted": [("painterly-muted", 0.55)],
            "clothing:minimalist": [("documentary-natural", 0.4)],
        }
        lora_defaults = {
            "species:human": [("portraitplus-v15", 0.55)],
            "species:beastfolk": [("anthroline-v21", 0.6)],
            "colorway:primary:warm:red": [("warmglow-detail", 0.45)],
            "colorway:primary:cool:blue": [("coolmist-soft", 0.45)],
            "clothing:vibrant": [("streetwear-luxe", 0.5)],
        }
        for tag, suggestions in defaults.items():
            for suggestion in suggestions:
                self.register_style(tag, suggestion[0], suggestion[1])
        for tag, suggestions in lora_defaults.items():
            for suggestion in suggestions:
                self.register_lora(tag, suggestion[0], suggestion[1])

    def register_style(self, tag: str, suggestion: str, weight: float = 0.5) -> None:
        items = self.styles.setdefault(tag, [])
        items.append((suggestion, weight))

    def register_lora(self, tag: str, lora_name: str, weight: float = 0.5) -> None:
        items = self.loras.setdefault(tag, [])
        items.append((lora_name, weight))

    def list_styles(self, tag: str) -> Sequence[Tuple[str, float]]:
        return tuple(self.styles.get(tag, ()))

    def list_loras(self, tag: str) -> Sequence[Tuple[str, float]]:
        return tuple(self.loras.get(tag, ()))


def suggest_styles(
    appearance: Dict[str, Any],
    palette: Sequence[Dict[str, Any]],
    *,
    registry: Optional[StyleSuggestionRegistry] = None,
    extra_tags: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    registry = registry or StyleSuggestionRegistry.default()
    tag_set: Set[str] = set()

    species = appearance.get("species")
    if species:
        tag_set.add(f"species:{species}")
    fur_skin = appearance.get("fur_skin")
    if fur_skin:
        tag_set.add(f"fur_skin:{fur_skin}")
    for token in appearance.get("colorways") or []:
        tag_set.add(f"colorway:{token}")
    for motif in appearance.get("clothing_motifs") or []:
        tag_set.add(f"clothing:{motif}")
    for accent in appearance.get("accent_colors") or []:
        tag_set.add(f"accent:{accent}")

    if extra_tags:
        tag_set.update(extra_tags)

    styles: Dict[str, Tuple[float, str]] = {}
    loras: Dict[str, Tuple[float, str]] = {}

    for tag in sorted(tag_set):
        for style, weight in registry.list_styles(tag):
            current = styles.get(style)
            if current is None or weight > current[0]:
                styles[style] = (weight, tag)
        for name, weight in registry.list_loras(tag):
            current = loras.get(name)
            if current is None or weight > current[0]:
                loras[name] = (weight, tag)

    style_list = sorted(styles.items(), key=lambda item: (-item[1][0], item[0]))
    lora_list = sorted(loras.items(), key=lambda item: (-item[1][0], item[0]))

    result = {
        "styles": [
            {"id": style, "priority": round(weight, 3), "source_tag": source_tag}
            for style, (weight, source_tag) in style_list
        ],
        "lora": [
            {"name": name, "priority": round(weight, 3), "source_tag": source_tag}
            for name, (weight, source_tag) in lora_list
        ],
        "applied_tags": sorted(tag_set),
    }

    if palette:
        primary = palette[0]
        result["primary_palette_hex"] = primary.get("hex")

    return result


__all__ = ["StyleSuggestionRegistry", "suggest_styles"]
