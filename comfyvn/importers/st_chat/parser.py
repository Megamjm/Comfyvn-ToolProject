"""Parser for SillyTavern chat exports (.json / .txt)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

LOGGER = logging.getLogger(__name__)

# Common SillyTavern role labels for participants.
_USER_NAMES = {"you", "user", "player", "narrator (you)"}
_SYSTEM_NAMES = {"system", "narrator", "storyteller", "assistant"}

_TIMESTAMP_KEYS = (
    "timestamp",
    "datetime",
    "created",
    "updated",
    "time",
    "ts",
    "ms",
    "created_at",
    "send_date",
    "edited",
)

_JSON_MESSAGE_KEYS = (
    "entries",
    "messages",
    "chat",
    "history",
    "turns",
    "log",
    "transcript",
)

_JSON_INLINE_TEXT_KEYS = (
    "mes",
    "text",
    "content",
    "message",
    "body",
    "msg",
    "value",
)

_JSON_SPEAKER_KEYS = (
    "name",
    "speaker",
    "author",
    "role",
    "character",
    "username",
    "display_name",
)

_TEXT_SPEAKER_PATTERN = re.compile(
    r"""
    ^
    (?:\[(?P<ts>[^\]]+)\]\s*)?          # Optional [timestamp]
    (?P<speaker>[^:\-\u2014]+?)        # Speaker up to colon/dash/em dash
    \s*(?:[:\-\u2014]\s+)\s*
    (?P<text>.+?)\s*$
    """,
    re.VERBOSE,
)

_TEXT_INLINE_TIMESTAMP = re.compile(r"^\s*\[(?P<ts>[^\]]+)\]\s*(?P<rest>.*)$")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _coerce_timestamp(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    # Numeric string (seconds or milliseconds).
    try:
        if text.isdigit() or (
            text.replace(".", "", 1).isdigit() and text.count(".") <= 1
        ):
            number = float(text)
            # Milliseconds heuristic.
            if number > 2_000_000_000_000:
                return number / 1000.0
            return number
    except Exception:
        pass
    # ISO 8601 and common date formats.
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt).astimezone().timestamp()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        LOGGER.debug("Unable to parse timestamp: %s", text)
        return None


def _extract_text(entry: Mapping[str, Any]) -> str:
    for key in _JSON_INLINE_TEXT_KEYS:
        value = entry.get(key)
        if isinstance(value, str):
            return value
    # Some SillyTavern exports use {"comment": {"body": ...}}
    comment = entry.get("comment")
    if isinstance(comment, Mapping):
        body = comment.get("body")
        if isinstance(body, str):
            return body
    return ""


def _extract_speaker(entry: Mapping[str, Any], default: str = "") -> str:
    for key in _JSON_SPEAKER_KEYS:
        value = entry.get(key)
        if isinstance(value, Mapping):
            nested_name = value.get("name") or value.get("display_name")
            if isinstance(nested_name, str) and nested_name.strip():
                return nested_name.strip()
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    # Extensions sometimes keep the speaker in role metadata.
    meta = entry.get("meta") or entry.get("metadata") or {}
    if isinstance(meta, Mapping):
        for key in _JSON_SPEAKER_KEYS:
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return default


def _normalise_role(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    return text


def _is_user_entry(
    entry: Mapping[str, Any],
    speaker: str,
    default_role: Optional[str],
) -> bool:
    meta = entry.get("extensions") or entry.get("metadata") or entry.get("meta") or {}
    if isinstance(meta, Mapping):
        role = meta.get("role")
        if isinstance(role, str):
            role = role.lower()
            if role in {"user", "player"}:
                return True
            if role in {"assistant", "npc"}:
                return False
    role_hint = entry.get("role") or entry.get("speaker_type")
    role_text = _normalise_role(role_hint) or default_role
    if role_text in {"user", "player"}:
        return True
    if role_text in {"assistant", "npc", "bot"}:
        return False
    if entry.get("is_user") is True:
        return True
    if entry.get("is_bot") is True:
        return False
    lower = speaker.lower()
    if lower in _USER_NAMES:
        return True
    if lower in _SYSTEM_NAMES:
        return False
    return False


def _coerce_session_id(payload: Mapping[str, Any]) -> Optional[str]:
    for key in ("session", "session_id", "chat_id", "id", "uuid"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _coerce_title(payload: Mapping[str, Any]) -> Optional[str]:
    for key in ("title", "name", "summary", "conversation", "chat"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalise_json_message(
    entry: Mapping[str, Any],
    *,
    index: int,
    session_id: Optional[str],
    conversation_title: Optional[str],
    default_role: Optional[str],
) -> Optional[Dict[str, Any]]:
    text = _extract_text(entry)
    speaker = _extract_speaker(entry, default="Narrator" if not text else "")
    if not speaker:
        speaker = "Narrator"

    timestamp = None
    for key in _TIMESTAMP_KEYS:
        if key in entry:
            timestamp = _coerce_timestamp(entry.get(key))
            if timestamp is not None:
                break
    if timestamp is None:
        meta = entry.get("meta") or entry.get("metadata") or entry.get("extensions")
        if isinstance(meta, Mapping):
            for key in _TIMESTAMP_KEYS:
                if key in meta:
                    timestamp = _coerce_timestamp(meta.get(key))
                    if timestamp is not None:
                        break

    payload_meta: Dict[str, Any] = {
        "source": "st_json",
        "index": index,
    }
    if session_id:
        payload_meta["session"] = session_id
    if conversation_title:
        payload_meta["conversation_title"] = conversation_title
    entry_id = entry.get("id") or entry.get("uuid")
    if isinstance(entry_id, (int, float)):
        payload_meta["message_id"] = str(entry_id)
    elif isinstance(entry_id, str) and entry_id.strip():
        payload_meta["message_id"] = entry_id.strip()

    for key in ("is_user", "is_bot", "stay", "swipes", "candidates"):
        if key in entry:
            payload_meta[key] = entry[key]

    extensions = entry.get("extensions")
    if isinstance(extensions, Mapping):
        payload_meta["extensions"] = dict(extensions)

    metadata = entry.get("metadata")
    if isinstance(metadata, Mapping):
        payload_meta["metadata"] = dict(metadata)

    meta_payload = entry.get("meta")
    if isinstance(meta_payload, Mapping):
        payload_meta.setdefault("metadata", {}).update(dict(meta_payload))

    payload_meta["default_role"] = default_role
    if timestamp is not None:
        payload_meta["timestamp_hint"] = timestamp

    user_entry = _is_user_entry(entry, speaker, default_role)
    payload_meta["is_user"] = user_entry

    if not text.strip() and not user_entry:
        # Skip empty assistant/system chatter to keep timelines clean.
        LOGGER.debug(
            "Skipping empty message for speaker '%s' (index %d)", speaker, index
        )
        return None

    return {
        "speaker": speaker,
        "text": text.strip(),
        "ts": timestamp,
        "meta": payload_meta,
    }


def _iter_json_messages(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for key in _JSON_MESSAGE_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            yield from value
        elif isinstance(value, Mapping):
            yield value
    if isinstance(payload.get("log"), list):
        yield from payload["log"]


def _parse_json_payload(data: Any) -> List[Dict[str, Any]]:
    if data is None:
        return []

    def _normalise_sequence(
        entries: Iterable[Mapping[str, Any]],
        base_meta: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        session_id = _coerce_session_id(base_meta)
        conversation_title = _coerce_title(base_meta)
        default_role = _normalise_role(
            base_meta.get("role")
            or base_meta.get("default_role")
            or base_meta.get("speaker_role")
        )

        turns: List[Dict[str, Any]] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                continue
            normalised = _normalise_json_message(
                entry,
                index=index,
                session_id=session_id,
                conversation_title=conversation_title,
                default_role=default_role,
            )
            if normalised:
                turns.append(normalised)
        return turns

    if isinstance(data, list):
        return _normalise_sequence(data, {})

    if isinstance(data, Mapping):
        base_meta = dict(data)
        entries: List[Mapping[str, Any]] = []
        for item in _iter_json_messages(data):
            if isinstance(item, list):
                entries.extend([entry for entry in item if isinstance(entry, Mapping)])
            elif isinstance(item, Mapping):
                entries.append(item)
        if not entries:
            # If no recognised entries, treat dict as single message.
            return _normalise_sequence([data], base_meta)
        return _normalise_sequence(entries, base_meta)

    return []


def _parse_json_text(text: str) -> List[Dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return _parse_json_payload(data)
    except json.JSONDecodeError:
        # Attempt JSONL fallback.
        turns: List[Dict[str, Any]] = []
        for index, line in enumerate(text.splitlines()):
            ln = line.strip()
            if not ln:
                continue
            try:
                entry = json.loads(ln)
            except json.JSONDecodeError:
                LOGGER.debug(
                    "Skipping non-JSON line %d when reading JSONL payload", index
                )
                continue
            if not isinstance(entry, Mapping):
                continue
            normalised = _normalise_json_message(
                entry,
                index=len(turns),
                session_id=None,
                conversation_title=None,
                default_role=None,
            )
            if normalised:
                turns.append(normalised)
        return turns


def _parse_roleplay_text(text: str) -> List[Dict[str, Any]]:
    turns: List[Dict[str, Any]] = []
    current: Optional[MutableMapping[str, Any]] = None
    line_index = 0

    for raw_line in text.splitlines():
        original = raw_line.rstrip("\n")
        stripped = original.strip()
        if not stripped:
            current = None
            continue

        timestamp_hint: Optional[float] = None
        ts_match = _TEXT_INLINE_TIMESTAMP.match(stripped)
        if ts_match:
            timestamp_hint = _coerce_timestamp(ts_match.group("ts"))
            stripped = ts_match.group("rest").strip()

        match = _TEXT_SPEAKER_PATTERN.match(stripped)
        if match:
            speaker = match.group("speaker").strip()
            text_body = match.group("text").strip()
            payload = {
                "speaker": speaker or "Narrator",
                "text": text_body,
                "ts": timestamp_hint,
                "meta": {
                    "source": "st_txt",
                    "index": len(turns),
                    "line": line_index,
                },
            }
            if timestamp_hint is not None:
                payload["meta"]["timestamp_hint"] = timestamp_hint
            turns.append(payload)
            current = payload
        else:
            if current is None:
                current = {
                    "speaker": "Narrator",
                    "text": stripped,
                    "ts": timestamp_hint,
                    "meta": {
                        "source": "st_txt",
                        "index": len(turns),
                        "line": line_index,
                    },
                }
                if timestamp_hint is not None:
                    current["meta"]["timestamp_hint"] = timestamp_hint
                turns.append(current)
            else:
                current["text"] = f"{current['text']}\n{stripped}"
                if timestamp_hint is not None and not current.get("ts"):
                    current["ts"] = timestamp_hint
                    current["meta"]["timestamp_hint"] = timestamp_hint
        line_index += 1
    return turns


def parse_st_payload(
    payload: Any, *, source_hint: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Parse a SillyTavern payload (dict/list/JSON/text) into canonical turn dicts.
    """
    if payload is None:
        return []

    if isinstance(payload, (dict, list)):
        return _parse_json_payload(payload)

    if isinstance(payload, bytes):
        try:
            return parse_st_payload(payload.decode("utf-8"), source_hint=source_hint)
        except Exception:
            return parse_st_payload(
                payload.decode("utf-8", errors="replace"), source_hint=source_hint
            )

    if isinstance(payload, str):
        hint = (source_hint or "").lower()
        if hint.startswith("json"):
            return _parse_json_text(payload)
        if hint in {"txt", "text"}:
            return _parse_roleplay_text(payload)

        trimmed = payload.lstrip()
        if trimmed.startswith("{") or trimmed.startswith("["):
            turns = _parse_json_text(payload)
            if turns:
                return turns
        return _parse_roleplay_text(payload)

    LOGGER.debug("Unsupported payload type for ST parser: %s", type(payload))
    return []


def parse_st_file(path: str | Path) -> List[Dict[str, Any]]:
    """
    Load and parse a SillyTavern export file (.json/.txt) into canonical turns.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"ST chat file not found: {file_path}")

    suffix = file_path.suffix.lower()
    text = _read_text(file_path)
    if suffix in {".json", ".jsonl"}:
        return parse_st_payload(text, source_hint="json")
    if suffix in {".txt", ".log"}:
        return parse_st_payload(text, source_hint="txt")
    # Fallback: attempt JSON first then text.
    turns = parse_st_payload(text, source_hint="json")
    if turns:
        return turns
    return parse_st_payload(text, source_hint="txt")


__all__ = ["parse_st_file", "parse_st_payload"]
