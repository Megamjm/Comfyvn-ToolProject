"""Convert parsed SillyTavern turns into ScenarioSpec scenes."""

from __future__ import annotations

import itertools
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from comfyvn.scenario.models import (
    ChoiceNode,
    ChoiceOptionSpec,
    EndNode,
    LineNode,
    ScenarioSpec,
)

LOGGER = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_STAGE_RE = re.compile(r"\*(?P<stage>[^\*]+)\*")
_EMOTE_RE = re.compile(r"\[(?P<emote>[^\]]+)\]")
_CHOICE_PREFIX_RE = re.compile(r"^\s*(?:>|\u2022|\u25cf|\-|\*)(?P<option>.+)$")
_CHOICE_INLINE_TAG = re.compile(r"^\s*(choice|option)\s*[:\-]\s*(?P<option>.+)$", re.I)

_ASCII_EMOJI_MAP = {
    ":)": "smile",
    ":-)": "smile",
    ":D": "grin",
    ":-D": "grin",
    ";)": "wink",
    ";-)": "wink",
    ":(": "sad",
    ":-(": "sad",
    ":'(": "cry",
    ":P": "playful",
    ":-P": "playful",
    ":|": "neutral",
    ":-|": "neutral",
    ">:(": "angry",
    ">:O": "surprised",
}

_UNICODE_EMOJI_MAP = {
    "😀": "smile",
    "😃": "smile",
    "😄": "smile",
    "😁": "grin",
    "😆": "laugh",
    "😅": "relief",
    "🤣": "laugh",
    "😂": "laugh",
    "🙂": "smile",
    "🙃": "playful",
    "😉": "wink",
    "😊": "smile",
    "😇": "angelic",
    "🥰": "love",
    "😍": "love",
    "😘": "kiss",
    "😗": "kiss",
    "😚": "kiss",
    "😙": "kiss",
    "😋": "playful",
    "😜": "playful",
    "😛": "playful",
    "🤪": "goofy",
    "😝": "playful",
    "🤑": "greedy",
    "🤗": "hug",
    "🤭": "bashful",
    "🤔": "thinking",
    "🤨": "dubious",
    "🧐": "inspect",
    "😐": "neutral",
    "😑": "neutral",
    "😶": "silent",
    "😏": "smirk",
    "😒": "unimpressed",
    "🙄": "eyeroll",
    "😬": "grimace",
    "🤥": "lying",
    "😌": "relief",
    "😔": "sad",
    "😪": "sleepy",
    "🤤": "drool",
    "😴": "sleep",
    "😷": "sick",
    "🤒": "sick",
    "🤕": "hurt",
    "🤢": "sick",
    "🤮": "sick",
    "🤧": "sneeze",
    "🥵": "hot",
    "🥶": "cold",
    "🥴": "woozy",
    "😵": "dizzy",
    "😲": "shocked",
    "😳": "embarrassed",
    "🥺": "pleading",
    "😭": "cry",
    "😡": "angry",
    "😠": "angry",
    "🤬": "rage",
    "😤": "determined",
    "😱": "scream",
    "😨": "fear",
    "😰": "anxious",
    "😥": "disappointed",
}

_USER_NAMES = {"you", "user", "player"}


def _slugify(value: Any, fallback: str = "scene") -> str:
    text = str(value or "").strip().lower()
    slug = _SLUG_RE.sub("-", text).strip("-")
    return slug or fallback


def _normalise_key(value: str) -> str:
    return _slugify(value, fallback=value.lower())


def _clean_whitespace(value: str) -> str:
    return " ".join(value.split())


def _infer_expression(text: str) -> Tuple[str, Optional[str], List[str]]:
    """Return cleaned text, inferred expression, and captured stage directions."""
    if not text:
        return "", None, []
    expression: Optional[str] = None
    stage_directions: List[str] = []
    working = text

    def _stage_repl(match: re.Match[str]) -> str:
        stage = match.group("stage").strip()
        if stage:
            stage_directions.append(stage)
        return ""

    working = _STAGE_RE.sub(_stage_repl, working)

    def _emote_repl(match: re.Match[str]) -> str:
        nonlocal expression
        emote = match.group("emote").strip()
        if emote:
            cleaned = _clean_whitespace(emote).lower()
            cleaned = cleaned.replace("emotion:", "").replace("emote:", "")
            cleaned = cleaned.replace("expression:", "").strip()
            cleaned = cleaned.replace(" ", "_")
            if cleaned:
                expression = expression or cleaned
        return ""

    working = _EMOTE_RE.sub(_emote_repl, working)

    for token, label in itertools.chain(
        _ASCII_EMOJI_MAP.items(), _UNICODE_EMOJI_MAP.items()
    ):
        if token in working:
            expression = expression or label
            working = working.replace(token, " ")

    cleaned = working.strip()
    if not cleaned and stage_directions:
        # Preserve stage direction context when text payload (after stripping)
        # would otherwise be empty.
        cleaned = " ".join(f"({entry})" for entry in stage_directions)
    return cleaned, expression, stage_directions


def _extract_choice_lines(text: str) -> Tuple[str, List[str]]:
    prompt_lines: List[str] = []
    choices: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        matched = False
        option = ""
        match = _CHOICE_PREFIX_RE.match(line)
        if match:
            option = match.group("option").strip()
            matched = True
        else:
            inline = _CHOICE_INLINE_TAG.match(line)
            if inline:
                option = inline.group("option").strip()
                matched = True
        if matched and option:
            # Handle multi-choice separated by pipes: "Choice: Go|Wait"
            segments = [seg.strip() for seg in option.split("|") if seg.strip()]
            if segments:
                choices.extend(segments)
            else:
                choices.append(option)
        else:
            prompt_lines.append(line)
    # For transcripts that encode a single choice inline ("Choice: Leave town"),
    # reuse entire text as both prompt and solitary option.
    if not choices and text.strip().lower().startswith("choice:"):
        residual = text.split(":", 1)[1].strip()
        if residual:
            choices.append(residual)
            prompt_lines = []
    prompt = "\n".join(prompt_lines).strip()
    return prompt, choices


def _coerce_timestamp(turn: Mapping[str, Any]) -> Optional[float]:
    ts = turn.get("ts")
    if isinstance(ts, (int, float)):
        try:
            return float(ts)
        except Exception:
            return None
    if isinstance(ts, str) and ts.strip():
        try:
            return float(ts.strip())
        except Exception:
            pass
    meta = turn.get("meta")
    if isinstance(meta, Mapping):
        hint = meta.get("timestamp_hint")
        if isinstance(hint, (int, float)):
            return float(hint)
        if isinstance(hint, str) and hint.strip():
            try:
                return float(hint)
            except Exception:
                return None
    return None


def _speaker_key(name: str) -> str:
    return _normalise_key(name or "")


def _is_player_turn(turn: Mapping[str, Any], speaker: str) -> bool:
    meta = turn.get("meta") or {}
    if isinstance(meta, Mapping):
        if meta.get("is_user") is True:
            return True
        role = str(meta.get("default_role") or meta.get("role") or "").lower()
        if role in {"user", "player"}:
            return True
    lowered = speaker.strip().lower()
    return lowered in _USER_NAMES


def _resolve_scene_title(
    segment: Sequence[Mapping[str, Any]]
) -> Tuple[str, Optional[str]]:
    session: Optional[str] = None
    title: Optional[str] = None
    for turn in segment:
        meta = turn.get("meta") or {}
        if isinstance(meta, Mapping):
            if not session:
                sess = meta.get("session") or meta.get("chat_id")
                if isinstance(sess, str) and sess.strip():
                    session = sess.strip()
            if not title:
                conv = meta.get("conversation_title") or meta.get("title")
                if isinstance(conv, str) and conv.strip():
                    title = conv.strip()
        if session and title:
            break
    if not title:
        # fallback to first non-narrator speaker line
        for turn in segment:
            speaker = str(turn.get("speaker") or "").strip()
            if speaker and speaker.lower() not in {"narrator", "system"}:
                sample_text = str(turn.get("text") or "").strip()
                if sample_text:
                    title = f"{speaker}: {sample_text[:40]}"
                    break
    # Fallback title ensures scenario validator passes.
    if not title:
        title = "Imported Chat"
    return title, session


@dataclass
class SceneBuildContext:
    project_id: str
    index: int
    persona_aliases: Dict[str, str]
    default_player_persona: Optional[str]
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    participants: List[str] = field(default_factory=list)
    persona_map: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    start_node_id: Optional[str] = None
    scene_id: Optional[str] = None
    scene_title: Optional[str] = None
    session_id: Optional[str] = None
    unresolved_personas: set[str] = field(default_factory=set)

    def register_participant(self, name: str) -> None:
        key = name.strip()
        if key and key not in self.participants:
            self.participants.append(key)

    def resolve_persona(
        self, speaker: str, turn_meta: Mapping[str, Any]
    ) -> Optional[str]:
        normalized = _speaker_key(speaker)
        if speaker in self.persona_map:
            return self.persona_map[speaker]
        if normalized in self.persona_aliases:
            persona_id = self.persona_aliases[normalized]
            self.persona_map.setdefault(speaker, persona_id)
            return persona_id
        # Check explicit mapping overrides first.
        meta_id = None
        for key in ("persona_id", "persona", "character_id", "character", "id"):
            value = turn_meta.get(key)
            if isinstance(value, str) and value.strip():
                meta_id = value.strip()
                break
        if meta_id:
            self.persona_aliases.setdefault(normalized, meta_id)
            self.persona_map.setdefault(speaker, meta_id)
            return meta_id

        if turn_meta.get("is_user") and self.default_player_persona:
            self.persona_aliases.setdefault(normalized, self.default_player_persona)
            self.persona_map.setdefault(speaker, self.default_player_persona)
            return self.default_player_persona
        return None

    def add_warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def flag_unresolved(self, speaker: str) -> None:
        name = speaker.strip()
        if not name or name.lower() in {"narrator", "system"}:
            return
        if name not in self.unresolved_personas:
            self.unresolved_personas.add(name)
            self.add_warning(f"No persona mapping found for speaker '{name}'")


def segment_scenes(
    turns: Sequence[Mapping[str, Any]],
    *,
    max_gap_seconds: float = 5400.0,
) -> List[List[Mapping[str, Any]]]:
    """
    Segment turns into sessions using chat titles or gaps between timestamps.
    """
    segments: List[List[Mapping[str, Any]]] = []
    current: List[Mapping[str, Any]] = []
    last_ts: Optional[float] = None
    last_session: Optional[str] = None
    last_title: Optional[str] = None

    for turn in turns:
        if not isinstance(turn, Mapping):
            continue
        meta = turn.get("meta") or {}
        session = None
        title = None
        if isinstance(meta, Mapping):
            session = (
                str(meta.get("session") or meta.get("chat_id") or "").strip() or None
            )
            title = (
                str(meta.get("conversation_title") or meta.get("title") or "").strip()
                or None
            )
            if str(meta.get("scene_break") or "").lower() in {"true", "1"}:
                if current:
                    segments.append(current)
                    current = []
                last_ts = None
                last_session = session
                last_title = title
                continue
        timestamp = _coerce_timestamp(turn)
        should_split = False
        if current:
            if session and last_session and session != last_session:
                should_split = True
            elif title and last_title and title != last_title:
                should_split = True
            elif (
                timestamp is not None
                and last_ts is not None
                and math.isfinite(timestamp)
                and math.isfinite(last_ts)
                and timestamp - last_ts > max_gap_seconds
            ):
                should_split = True
            else:
                text = str(turn.get("text") or "").strip()
                if text in {"---", "***", "==="}:
                    should_split = True
        if should_split and current:
            segments.append(current)
            current = []
            last_ts = None
        current.append(turn)
        last_ts = timestamp if timestamp is not None else last_ts
        last_session = session or last_session
        last_title = title or last_title
    if current:
        segments.append(current)
    return segments


def _line_node(
    node_id: str, text: str, speaker: Optional[str], expression: Optional[str]
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": node_id,
        "type": "line",
        "text": text or "...",
        "next": None,
        "tags": [],
    }
    if speaker:
        payload["speaker"] = speaker
    if expression:
        payload["expression"] = expression
    return payload


def _choice_node(
    node_id: str, prompt: Optional[str], choices: List[str]
) -> Dict[str, Any]:
    options: List[Dict[str, Any]] = []
    for index, label in enumerate(choices):
        option_id = f"{node_id}_opt{index+1:02d}"
        options.append(
            {
                "id": option_id,
                "text": label or f"Option {index+1}",
                "next": None,
                "weight": 1.0,
                "conditions": [],
                "set": {},
            }
        )
    payload: Dict[str, Any] = {
        "id": node_id,
        "type": "choice",
        "prompt": prompt or None,
        "choices": options,
    }
    return payload


def _end_node(node_id: str) -> Dict[str, Any]:
    return {
        "id": node_id,
        "type": "end",
        "result": "Imported from SillyTavern",
    }


def _build_scene_id(project_id: str, index: int, title: Optional[str]) -> str:
    base = _slugify(title or "", fallback=f"scene-{index+1:02d}")
    project_slug = _slugify(project_id or "", fallback="project")
    return f"{project_slug}-{base}"


def _prepare_persona_aliases(
    persona_aliases: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    catalog: Dict[str, str] = {}
    if persona_aliases:
        for key, value in persona_aliases.items():
            if not key or not value:
                continue
            catalog[_normalise_key(str(key))] = str(value)
    return catalog


def map_to_scenes(
    project_id: str,
    turns: Sequence[Mapping[str, Any]],
    *,
    persona_aliases: Optional[Mapping[str, str]] = None,
    default_player_persona: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Convert parsed ST turns to ScenarioSpec-compatible scene dictionaries.
    """
    persona_catalog = _prepare_persona_aliases(persona_aliases)
    segments = segment_scenes(turns)
    scenes: List[Dict[str, Any]] = []
    used_scene_ids: set[str] = set()

    for index, segment in enumerate(segments):
        if not segment:
            continue

        context = SceneBuildContext(
            project_id=project_id,
            index=index,
            persona_aliases=persona_catalog,
            default_player_persona=default_player_persona,
        )
        title, session_id = _resolve_scene_title(segment)
        provisional_scene_id = _build_scene_id(project_id, index, title)
        scene_id = provisional_scene_id
        suffix = 2
        while scene_id in used_scene_ids:
            scene_id = f"{provisional_scene_id}-{suffix}"
            suffix += 1
        used_scene_ids.add(scene_id)
        context.scene_title = title
        context.scene_id = scene_id
        context.session_id = session_id

        for turn_index, turn in enumerate(segment):
            text = str(turn.get("text") or "").strip()
            speaker = str(turn.get("speaker") or "Narrator").strip() or "Narrator"
            meta = turn.get("meta") if isinstance(turn.get("meta"), Mapping) else {}

            context.register_participant(speaker)
            persona_id = context.resolve_persona(speaker, meta or {})
            if persona_id is None:
                context.flag_unresolved(speaker)

            cleaned_text, expression, stage_notes = _infer_expression(text)

            is_player = _is_player_turn(turn, speaker)
            prompt, choice_lines = _extract_choice_lines(cleaned_text)
            use_choice_node = is_player and choice_lines

            node_id = f"{scene_id}_n{len(context.nodes)+1:03d}"
            if context.start_node_id is None:
                context.start_node_id = node_id

            if use_choice_node:
                node_payload = _choice_node(node_id, prompt or None, choice_lines)
                if not choice_lines:
                    context.add_warning(
                        f"Choice inferred at turn {turn_index} but no options detected."
                    )
            else:
                speaker_ref = persona_id or speaker
                node_payload = _line_node(
                    node_id, cleaned_text, speaker_ref, expression
                )
                if not cleaned_text:
                    context.add_warning(
                        f"Empty text detected for {speaker} at turn {turn_index}; substituted placeholder."
                    )

            context.nodes.append(node_payload)
            if stage_notes:
                context.annotations[node_id] = {"stage": stage_notes}

        # Append end node
        end_id = f"{scene_id}_end"
        context.nodes.append(_end_node(end_id))

        # Wire sequential next pointers
        for idx, node in enumerate(context.nodes):
            if node["type"] == "end":
                continue
            next_node = context.nodes[idx + 1] if idx + 1 < len(context.nodes) else None
            next_id = next_node["id"] if next_node else end_id
            if node["type"] == "line":
                node["next"] = next_id
            elif node["type"] == "choice":
                for choice in node["choices"]:
                    if not choice.get("next"):
                        choice["next"] = next_id

        # Validate nodes via ScenarioSpec
        node_models = []
        for node in context.nodes:
            node_type = node.get("type")
            if node_type == "line":
                node_models.append(LineNode(**node))
            elif node_type == "choice":
                choices = [
                    ChoiceOptionSpec(**choice) for choice in node.get("choices", [])
                ]
                node_models.append(
                    ChoiceNode(
                        id=node["id"],
                        prompt=node.get("prompt"),
                        choices=choices,
                    )
                )
            elif node_type == "end":
                node_models.append(EndNode(**node))
            else:
                context.add_warning(f"Unsupported node type '{node_type}' dropped.")

        scenario = ScenarioSpec(
            id=context.scene_id,
            title=context.scene_title,
            start=context.start_node_id or node_models[0].id,
            nodes=node_models,
            variables={},
            meta={},
        )
        payload = scenario.model_dump(mode="json", exclude_none=True)
        payload["meta"] = {
            "project_id": project_id,
            "source": "st_chat_importer",
            "participants": sorted(context.participants, key=lambda s: s.lower()),
            "persona_map": {
                name: context.persona_map[name]
                for name in sorted(context.persona_map, key=lambda s: s.lower())
            },
            "session": context.session_id,
            "annotations": context.annotations,
            "warnings": list(context.warnings),
            "unresolved_personas": sorted(context.unresolved_personas),
        }
        scenes.append(payload)

    return scenes


__all__ = ["segment_scenes", "map_to_scenes"]
