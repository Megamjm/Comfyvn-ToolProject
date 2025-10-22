from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from comfyvn.persona.schema import (
    PersonaValidationError,
    build_persona_record,
    merge_tag_sets,
    normalise_tags,
    slugify,
)

LOGGER = logging.getLogger(__name__)

SECTION_HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
BOLD_HEADING_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*:?\s*$")
COLON_HEADING_RE = re.compile(r"^\s*([A-Za-z][\w\s\-\/]{2,40})\s*:\s*$")
KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z][\w\s\-\/]{1,40})\s*[:\-]\s*(.+?)\s*$")
HASHTAG_RE = re.compile(r"#([A-Za-z0-9_\-]{2,32})")
HEX_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.+)$")


def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return parts[0] if parts else text.strip()


def _split_list(value: str) -> List[str]:
    if not value:
        return []
    segments = re.split(r"[,;/\n]", value)
    return [segment.strip() for segment in segments if segment.strip()]


def _extract_sections(text: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current = "summary"
    buffer: List[str] = []
    lines = text.splitlines()
    for raw_line in lines:
        line = raw_line.rstrip()
        heading: Optional[str] = None
        match = SECTION_HEADING_RE.match(line)
        if match:
            heading = match.group(2)
        else:
            bold = BOLD_HEADING_RE.match(line)
            if bold:
                heading = bold.group(1)
            else:
                colon = COLON_HEADING_RE.match(line)
                if colon:
                    heading = colon.group(1)

        if heading:
            if buffer:
                sections[current] = "\n".join(buffer).strip()
                buffer = []
            current = heading.strip().lower()
            continue
        buffer.append(raw_line)

    if buffer:
        sections[current] = "\n".join(buffer).strip()
    return sections


def _parse_key_values(text: str) -> Dict[str, str]:
    pairs: Dict[str, str] = {}
    for line in text.splitlines():
        match = KEY_VALUE_RE.match(line)
        if not match:
            continue
        key = match.group(1).strip().lower()
        value = match.group(2).strip()
        if not value:
            continue
        pairs[key] = value
    return pairs


def _parse_pronouns(value: str) -> Dict[str, str]:
    cleaned = value.strip()
    if "/" in cleaned:
        parts = [
            segment.strip().lower() for segment in cleaned.split("/") if segment.strip()
        ]
        if len(parts) >= 2:
            return {
                "subject": parts[0],
                "object": parts[1] if len(parts) >= 2 else parts[0],
                "possessive": parts[2] if len(parts) >= 3 else parts[1],
                "reflexive": parts[3] if len(parts) >= 4 else f"{parts[0]}self",
            }
    if "," in cleaned:
        parts = [
            segment.strip().lower() for segment in cleaned.split(",") if segment.strip()
        ]
        return {
            "subject": parts[0],
            "object": parts[1] if len(parts) > 1 else parts[0],
            "possessive": parts[2] if len(parts) > 2 else parts[0],
            "reflexive": parts[3] if len(parts) > 3 else f"{parts[0]}self",
        }
    words = cleaned.lower().split()
    if len(words) >= 2:
        return {
            "subject": words[0],
            "object": words[1],
            "possessive": words[2] if len(words) > 2 else words[1],
            "reflexive": words[3] if len(words) > 3 else f"{words[0]}self",
        }
    return {}


def _extract_relationships(section: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for line in section.splitlines():
        match = LIST_ITEM_RE.match(line)
        text = match.group(1) if match else line.strip()
        if not text:
            continue
        if ":" in text:
            name, summary = text.split(":", 1)
        elif "-" in text:
            name, summary = text.split("-", 1)
        else:
            name, summary = text, ""
        entries.append(
            {
                "name": name.strip(),
                "summary": summary.strip() or None,
            }
        )
    return entries


def _extract_palette(*chunks: str) -> List[Dict[str, str]]:
    colors: List[str] = []
    for chunk in chunks:
        for match in HEX_COLOR_RE.findall(chunk or ""):
            hex_code = match.lower()
            if hex_code not in colors:
                colors.append(hex_code)
    swatches: List[Dict[str, str]] = []
    for idx, hex_code in enumerate(colors[:6]):
        if idx == 0:
            name = "primary"
        elif idx == 1:
            name = "secondary"
        elif idx == 2:
            name = "accent"
        else:
            name = f"swatch_{idx+1}"
        swatches.append({"name": name, "hex": hex_code})
    return swatches


def _extract_quotes(section: str) -> List[str]:
    quotes: List[str] = []
    for line in section.splitlines():
        line = line.strip().strip('"').strip("'")
        if not line:
            continue
        if len(line.split()) <= 2:
            continue
        quotes.append(line)
    return quotes[:6]


def _first_nonempty(lines: Iterable[str]) -> str:
    for line in lines:
        text = line.strip()
        if text:
            return text
    return ""


@dataclass
class ParsedProfile:
    profile: Dict[str, Any]
    warnings: List[str]
    debug: Dict[str, Any]


class CommunityProfileImporter:
    """Parse community supplied persona profiles."""

    def __init__(self) -> None:
        self.logger = LOGGER

    def from_text(
        self,
        *,
        text: str,
        persona_id: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        nsfw_allowed: bool = False,
        default_role: str = "npc",
        source_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        parsed = self._parse_text_profile(text)
        profile = parsed.profile
        warnings = list(parsed.warnings)

        if persona_id:
            profile["id"] = slugify(persona_id)

        meta_block = profile.setdefault("metadata", {})
        meta_block["importer"] = "community_profile"
        if metadata:
            for key, value in metadata.items():
                if isinstance(key, str):
                    meta_block[key] = value

        try:
            persona, trimmed = build_persona_record(
                profile,
                allow_nsfw=nsfw_allowed,
                default_role=default_role,
            )
        except Exception as exc:  # pragma: no cover - defensive
            raise PersonaValidationError(str(exc)) from exc

        sources = list(persona.get("sources") or [])
        sources.append(
            {
                "type": "text",
                "value": metadata.get("source") if metadata else source_label,
                "rights": metadata.get("rights") if metadata else None,
            }
        )
        persona["sources"] = [
            entry
            for entry in sources
            if isinstance(entry, Mapping)
            and (entry.get("value") or entry.get("rights") or entry.get("type"))
        ]

        result = {
            "persona": persona,
            "warnings": warnings,
            "trimmed": trimmed,
            "debug": parsed.debug,
        }
        return result

    def _parse_text_profile(self, text: str) -> ParsedProfile:
        text = text or ""
        stripped = text.strip()
        if not stripped:
            raise PersonaValidationError("Profile text is required.")

        json_payload = self._try_json(stripped)
        if json_payload is not None:
            profile, warnings, debug = self._from_json(json_payload)
            return ParsedProfile(profile=profile, warnings=warnings, debug=debug)

        sections = _extract_sections(stripped)
        key_values = _parse_key_values(stripped)

        profile: Dict[str, Any] = {}
        warnings: List[str] = []
        debug: Dict[str, Any] = {
            "sections": list(sections.keys()),
            "keys": list(key_values.keys()),
        }

        name = (
            key_values.get("name")
            or sections.get("name")
            or _first_nonempty(stripped.splitlines())
        )
        if not name:
            warnings.append("Name missing from profile; using anonymous persona.")
            name = "Anonymous Persona"
        profile["name"] = name.strip()

        summary = (
            key_values.get("summary")
            or sections.get("summary")
            or _first_sentence(stripped)
        )
        profile["summary"] = summary.strip() if summary else None

        species = key_values.get("species") or sections.get("species")
        if species:
            profile["species"] = _split_list(species)
        else:
            warnings.append("Species not provided.")
            profile["species"] = []

        pronouns = key_values.get("pronouns") or sections.get("pronouns")
        if pronouns:
            parsed_pronouns = _parse_pronouns(pronouns)
            if parsed_pronouns:
                profile["pronouns"] = parsed_pronouns

        general_tags = normalise_tags(key_values.get("tags"))
        style_tags = normalise_tags(key_values.get("style") or key_values.get("genre"))

        hashtag_tags = [tag.lower() for tag in HASHTAG_RE.findall(stripped)]
        if hashtag_tags:
            general_tags.extend(hashtag_tags)

        appearance_section = sections.get("appearance") or sections.get("looks")
        if appearance_section:
            lines = [
                LIST_ITEM_RE.match(line).group(1) if LIST_ITEM_RE.match(line) else line
                for line in appearance_section.splitlines()
            ]
            traits = [line.strip() for line in lines if line.strip()]
            profile["appearance"] = {
                "summary": appearance_section.strip(),
                "traits": traits[:12],
            }
        else:
            warnings.append("Appearance section missing.")

        palette_swatches = _extract_palette(
            sections.get("palette") or "",
            sections.get("appearance") or "",
            stripped,
        )
        if palette_swatches:
            profile.setdefault("palette", {})["swatches"] = palette_swatches

        lore_section = (
            sections.get("lore")
            or sections.get("backstory")
            or sections.get("history")
            or sections.get("bio")
        )
        if lore_section:
            profile["lore"] = {
                "backstory": lore_section.strip(),
                "quotes": _extract_quotes(sections.get("quotes", "")),
            }

        motivation = key_values.get("motivation") or sections.get("motivation")
        if motivation:
            lore_block = profile.setdefault("lore", {})
            lore_block["motivation"] = motivation.strip()

        relationships_section = sections.get("relationships") or sections.get(
            "connections"
        )
        if relationships_section:
            profile["relationships"] = _extract_relationships(relationships_section)

        voice_section = sections.get("voice") or key_values.get("voice")
        if voice_section:
            profile["voice"] = {
                "style": (
                    voice_section.splitlines()[0].strip()
                    if voice_section.splitlines()
                    else voice_section.strip()
                ),
                "hints": [
                    line.strip()
                    for line in voice_section.splitlines()[1:6]
                    if line.strip()
                ],
            }

        nsfw_section = sections.get("nsfw") or key_values.get("nsfw")
        if nsfw_section:
            profile["nsfw"] = {
                "notes": nsfw_section.strip(),
                "tags": normalise_tags(_split_list(nsfw_section)),
            }

        style_section = sections.get("style") or sections.get("tone")
        if style_section:
            style_tags.extend(normalise_tags(style_section.splitlines()))

        combined_tags = merge_tag_sets(
            {"general": general_tags, "style": style_tags, "nsfw": []}
        )
        profile["tags"] = combined_tags.model_dump()

        debug["tag_counts"] = {
            "general": len(profile["tags"]["general"]),
            "style": len(profile["tags"]["style"]),
        }

        return ParsedProfile(profile=profile, warnings=warnings, debug=debug)

    def _try_json(self, text: str) -> Optional[Mapping[str, Any]]:
        if not text.startswith("{") and not text.startswith("["):
            return None
        try:
            data = json.loads(text)
        except Exception:
            return None
        if isinstance(data, Mapping):
            return data
        if isinstance(data, list) and data and isinstance(data[0], Mapping):
            if "persona" in data[0]:
                return data[0]["persona"]
            return data[0]
        return None

    def _from_json(
        self, payload: Mapping[str, Any]
    ) -> Tuple[Dict[str, Any], List[str], Dict[str, Any]]:
        profile = dict(payload)
        warnings: List[str] = []
        tag_block = profile.get("tags")
        if isinstance(tag_block, Mapping):
            profile["tags"] = merge_tag_sets(tag_block).model_dump()
        else:
            profile["tags"] = merge_tag_sets({"general": tag_block}).model_dump()
        debug = {"source": "json"}
        return profile, warnings, debug
