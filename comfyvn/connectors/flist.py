from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from comfyvn.persona.schema import (
    PersonaValidationError,
    build_persona_record,
    merge_tag_sets,
    normalise_tags,
    slugify,
)

LOGGER = logging.getLogger(__name__)

BB_URL_RE = re.compile(r"\[url=[^\]]+](.*?)\[/url\]", re.IGNORECASE | re.DOTALL)
BB_IMG_RE = re.compile(r"\[img[^\]]*].*?\[/img]", re.IGNORECASE | re.DOTALL)
BB_CODE_RE = re.compile(r"\[(?:/?[a-z0-9]+)(?:=[^\]]+)?\]", re.IGNORECASE)
SECTION_MARK_RE = re.compile(
    r"^\s*(?:==+\s*(?P<eq>[^=].*?)\s*==+|\[b](?P<bb>.+?)\[/b]\s*|(?P<plain>[A-Za-z][\w\s'&/-]{2,60})\s*:)\s*$"
)
KEY_VALUE_RE = re.compile(
    r"^\s*(?P<key>[A-Za-z][\w\s'&/-]{1,48})\s*[:\-]\s*(?P<value>.+?)\s*$"
)
LIST_SPLIT_RE = re.compile(r"[,\n;/•\u2022]+")
KINK_SECTION_PREFIXES = (
    "kinks - favourites",
    "kinks - favorites",
    "kinks - yes",
    "kinks - maybe",
    "kinks - no",
    "kinks - never",
)


def _strip_markup(text: str) -> str:
    if not text:
        return ""
    cleaned = BB_URL_RE.sub(lambda m: m.group(1) or "", text)
    cleaned = BB_IMG_RE.sub("", cleaned)
    cleaned = cleaned.replace("[*]", "- ")
    cleaned = re.sub(r"\[/?list[^\]]*]", "", cleaned, flags=re.IGNORECASE)
    cleaned = BB_CODE_RE.sub("", cleaned)
    return cleaned


def _normalise_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.splitlines())


def _split_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items: List[str] = []
        for entry in value:
            text = str(entry or "").strip()
            if text:
                items.append(text)
        return items
    text = str(value or "")
    chunks = [
        chunk.strip()
        for chunk in LIST_SPLIT_RE.split(text.replace(" - ", ",").replace("|", ","))
        if chunk.strip()
    ]
    # Preserve order while deduping
    seen: set[str] = set()
    result: List[str] = []
    for chunk in chunks:
        lowered = chunk.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(chunk)
    return result


def _extract_key_values(lines: Sequence[str]) -> Dict[str, str]:
    pairs: Dict[str, str] = {}
    for raw in lines:
        match = KEY_VALUE_RE.match(raw)
        if not match:
            continue
        key = match.group("key").strip().lower()
        value = match.group("value").strip()
        if not key or not value:
            continue
        if key in pairs:
            continue
        pairs[key] = value
    return pairs


def _is_section_heading(line: str) -> Optional[str]:
    stripped = line.strip()
    if not stripped:
        return None
    if KEY_VALUE_RE.match(stripped):
        return None
    match = SECTION_MARK_RE.match(stripped)
    if not match:
        return None
    heading = match.group("eq") or match.group("bb") or match.group("plain")
    if not heading:
        return None
    heading = heading.strip()
    if not heading:
        return None
    lowered = heading.lower()
    if any(
        lowered.startswith(prefix) for prefix in ("note ", "notes ", "stat ", "stats ")
    ):
        return None
    return heading


def _extract_sections(lines: Sequence[str]) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current = "profile"
    buffer: List[str] = []
    for raw in lines:
        heading = _is_section_heading(raw)
        if heading:
            if buffer:
                sections[current] = "\n".join(buffer).strip()
                buffer = []
            current = heading.lower()
            continue
        buffer.append(raw)
    if buffer:
        sections[current] = "\n".join(buffer).strip()
    return sections


def _gender_to_pronouns(value: str) -> Dict[str, str]:
    gender = (value or "").strip().lower()
    if not gender:
        return {}
    mapping = {
        "male": ("he", "him", "his", "himself"),
        "man": ("he", "him", "his", "himself"),
        "boy": ("he", "him", "his", "himself"),
        "female": ("she", "her", "her", "herself"),
        "woman": ("she", "her", "her", "herself"),
        "girl": ("she", "her", "her", "herself"),
    }
    for key, pron in mapping.items():
        if key in gender:
            return {
                "subject": pron[0],
                "object": pron[1],
                "possessive": pron[2],
                "reflexive": pron[3],
            }
    if "they" in gender or "non-binary" in gender or "nonbinary" in gender:
        return {
            "subject": "they",
            "object": "them",
            "possessive": "their",
            "reflexive": "themselves",
        }
    return {}


def _parse_pronouns(value: str) -> Dict[str, str]:
    text = (value or "").strip()
    if not text:
        return {}
    if "/" in text:
        parts = [part.strip().lower() for part in text.split("/") if part.strip()]
    elif "," in text:
        parts = [part.strip().lower() for part in text.split(",") if part.strip()]
    else:
        parts = text.lower().split()
    if not parts:
        return {}
    subject = parts[0]
    object_ = parts[1] if len(parts) > 1 else subject
    possessive = parts[2] if len(parts) > 2 else object_
    reflexive = parts[3] if len(parts) > 3 else f"{subject}self"
    return {
        "subject": subject,
        "object": object_,
        "possessive": possessive,
        "reflexive": reflexive,
    }


def _gather_traits(section: Optional[str]) -> Tuple[Optional[str], List[str]]:
    if not section:
        return None, []
    cleaned = section.strip()
    lines = [
        line.strip("-•\u2022 \t")
        for line in cleaned.splitlines()
        if line.strip("-•\u2022 \t")
    ]
    traits: List[str] = []
    for line in lines:
        if len(line.split()) > 12:
            continue
        if len(traits) >= 16:
            break
        traits.append(line)
    return cleaned, traits


def _prepare_preferences(
    pairs: Mapping[str, str], sections: Mapping[str, str]
) -> Dict[str, List[str]]:
    likes: List[str] = []
    dislikes: List[str] = []
    nope: List[str] = []
    for key in ("likes", "favorite themes", "favourites", "enjoys"):
        if key in pairs:
            likes.extend(_split_list(pairs[key]))
    for key in ("dislikes", "avoid", "less likes"):
        if key in pairs:
            dislikes.extend(_split_list(pairs[key]))
    for key in ("no", "never", "nope", "limits", "won't do", "hard limits"):
        if key in pairs:
            nope.extend(_split_list(pairs[key]))

    rp_section = sections.get("rp preferences") or sections.get("roleplay preferences")
    if rp_section:
        for line in rp_section.splitlines():
            lower = line.lower()
            if ":" not in line and "-" not in line:
                continue
            if any(
                label in lower for label in ("like", "prefer", "favourite", "favorite")
            ):
                likes.extend(_split_list(line.split(":", 1)[-1]))
            if any(label in lower for label in ("dislike", "avoid", "less keen")):
                dislikes.extend(_split_list(line.split(":", 1)[-1]))
            if any(label in lower for label in ("won't", "hard", "never", "nope")):
                nope.extend(_split_list(line.split(":", 1)[-1]))

    def _dedupe(values: Sequence[str]) -> List[str]:
        seen: set[str] = set()
        ordered: List[str] = []
        for item in values:
            text = str(item or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            ordered.append(text)
        return ordered

    return {
        "likes": _dedupe(likes),
        "dislikes": _dedupe(dislikes),
        "nope": _dedupe(nope),
    }


def _extract_kink_sets(sections: Mapping[str, str]) -> Dict[str, List[str]]:
    favourites = []
    yes = []
    maybe = []
    nope = []
    for key, payload in sections.items():
        lowered = key.lower()
        if lowered.startswith("kinks - favourites") or lowered.startswith(
            "kinks - favorites"
        ):
            favourites.extend(_split_list(payload))
        elif lowered.startswith("kinks - yes"):
            yes.extend(_split_list(payload))
        elif lowered.startswith("kinks - maybe") or lowered.startswith(
            "kinks - maybe/unsure"
        ):
            maybe.extend(_split_list(payload))
        elif lowered.startswith("kinks - no") or lowered.startswith("kinks - never"):
            nope.extend(_split_list(payload))

    def _unique(values: Sequence[str]) -> List[str]:
        seen: set[str] = set()
        ordered: List[str] = []
        for item in values:
            text = str(item or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            ordered.append(text)
        return ordered

    return {
        "favourites": _unique(favourites),
        "yes": _unique(yes),
        "maybe": _unique(maybe),
        "no": _unique(nope),
    }


def _collect_tag_sets(
    pairs: Mapping[str, str],
    preferences: Mapping[str, Sequence[str]],
    kinks: Mapping[str, Sequence[str]],
) -> Dict[str, List[str]]:
    general: List[str] = []
    style: List[str] = []
    gender = pairs.get("gender") or pairs.get("sex")
    orientation = pairs.get("orientation") or pairs.get("sexual orientation")
    occupation = pairs.get("occupation") or pairs.get("job")
    listed_species = pairs.get("species") or pairs.get("race")

    for value in (gender, orientation, occupation):
        general.extend(_split_list(value))
    general.extend(preferences.get("likes", []))
    if listed_species:
        general.extend(_split_list(listed_species))
    style.extend(preferences.get("dislikes", []))
    style.extend(preferences.get("nope", []))

    nsfw = []
    nsfw.extend(kinks.get("favourites", []))
    nsfw.extend(kinks.get("yes", []))
    return merge_tag_sets(
        {"general": general, "style": style, "nsfw": nsfw}
    ).model_dump()


def _collect_nsfw_payload(kinks: Mapping[str, Sequence[str]]) -> Dict[str, Any]:
    favourites = list(kinks.get("favourites", []))
    yes = list(kinks.get("yes", []))
    notes_segments: List[str] = []
    if favourites:
        notes_segments.append(f"Favourites: {', '.join(favourites[:20])}")
    if yes:
        notes_segments.append(f"Yes: {', '.join(yes[:20])}")
    maybe = list(kinks.get("maybe", []))
    if maybe:
        notes_segments.append(f"Maybe: {', '.join(maybe[:20])}")
    no = list(kinks.get("no", []))
    if no:
        notes_segments.append(f"Nope: {', '.join(no[:20])}")
    notes = "\n".join(notes_segments) if notes_segments else None
    nsfw_tags = normalise_tags(favourites + yes)
    return {"tags": nsfw_tags, "notes": notes}


def _resolve_species(
    pairs: Mapping[str, str], sections: Mapping[str, str]
) -> List[str]:
    species_fields = (
        pairs.get("species"),
        pairs.get("race"),
        pairs.get("type"),
    )
    result: List[str] = []
    for entry in species_fields:
        result.extend(_split_list(entry))
    if not result:
        bio_section = sections.get("profile") or sections.get("summary")
        if bio_section:
            match = re.search(
                r"(?:species|race)\s*:\s*([A-Za-z0-9 \-/]+)", bio_section, re.IGNORECASE
            )
            if match:
                result.extend(_split_list(match.group(1)))
    return result


@dataclass
class FListParseResult:
    persona: Dict[str, Any]
    warnings: List[str]
    trimmed: Dict[str, Any]
    debug: Dict[str, Any]


class FListConnector:
    """Parse F-List profile exports into Persona payloads."""

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
    ) -> FListParseResult:
        stripped = _strip_markup(text or "")
        normalised = _normalise_text(stripped)
        lines = normalised.splitlines()
        key_values = _extract_key_values(lines)
        sections = _extract_sections(lines)

        warnings: List[str] = []
        debug: Dict[str, Any] = {
            "sections": list(sections.keys()),
            "keys": list(key_values.keys()),
        }

        name = key_values.get("name") or key_values.get("full name")
        if not name:
            first_line = next((ln.strip() for ln in lines if ln.strip()), "")
            if first_line:
                name = first_line.split(":", 1)[0]
        if not name:
            warnings.append("Name missing from F-List profile; using placeholder.")
            name = "F-List Persona"

        profile: Dict[str, Any] = {"name": name.strip()}
        summary_section = sections.get("profile") or sections.get("summary")
        if summary_section:
            profile["summary"] = summary_section.strip()
        else:
            first_nonempty = next((ln.strip() for ln in lines if ln.strip()), "")
            profile["summary"] = first_nonempty or None

        species = _resolve_species(key_values, sections)
        profile["species"] = species
        if not species:
            warnings.append("Species not specified in F-List export.")

        pronouns = {}
        if "pronouns" in key_values:
            pronouns = _parse_pronouns(key_values["pronouns"])
        if not pronouns and ("gender" in key_values or "sex" in key_values):
            pronouns = _gender_to_pronouns(
                key_values.get("gender") or key_values.get("sex")
            )
        if pronouns:
            profile["pronouns"] = pronouns

        appearance_section = (
            sections.get("appearance")
            or sections.get("physical description")
            or sections.get("body")
            or sections.get("character description")
        )
        appearance_summary, appearance_traits = _gather_traits(appearance_section)
        if appearance_summary or appearance_traits:
            profile["appearance"] = {
                "summary": appearance_summary,
                "traits": appearance_traits,
            }

        lore_section = (
            sections.get("history")
            or sections.get("background")
            or sections.get("bio")
            or sections.get("personality")
        )
        if lore_section:
            profile["lore"] = {
                "backstory": lore_section.strip(),
            }

        preferences = _prepare_preferences(key_values, sections)
        profile["preferences"] = preferences

        kinks = _extract_kink_sets(sections)
        debug["kink_counts"] = {key: len(val) for key, val in kinks.items()}

        tags = _collect_tag_sets(key_values, preferences, kinks)
        profile["tags"] = tags

        nsfw_payload = _collect_nsfw_payload(kinks)
        if nsfw_payload["tags"] or nsfw_payload["notes"]:
            profile["nsfw"] = nsfw_payload

        # Compose metadata and sources
        metadata_block: Dict[str, Any] = {"importer": "flist"}
        if metadata:
            for key, value in metadata.items():
                if isinstance(key, str):
                    metadata_block[key] = value
        profile["metadata"] = metadata_block

        sources = [
            {
                "type": "text",
                "value": metadata_block.get("profile_url")
                or metadata_block.get("source")
                or source_label
                or "flist",
                "rights": metadata_block.get("rights"),
            }
        ]
        profile["sources"] = sources

        if persona_id:
            profile["id"] = slugify(persona_id)

        try:
            persona, trimmed = build_persona_record(
                profile,
                allow_nsfw=nsfw_allowed,
                default_role=default_role,
            )
        except Exception as exc:  # pragma: no cover - defensive
            raise PersonaValidationError(str(exc)) from exc

        # restore metadata to include debug hints
        persona.setdefault("metadata", {})
        persona["metadata"].setdefault("importer", "flist")
        persona["metadata"]["connector"] = "flist"

        return FListParseResult(
            persona=persona,
            warnings=warnings,
            trimmed=trimmed,
            debug=debug,
        )
