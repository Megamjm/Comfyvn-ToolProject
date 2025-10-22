"""Converters for SillyTavern personas and chats into ComfyVN assets."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from comfyvn.assets.persona_manager import PersonaManager
from comfyvn.core.scene_store import SceneStore

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_EMOTION_RE = re.compile(r"\[\[\s*(?:e|emotion)\s*:\s*([^\]]+)\s*\]\]", re.IGNORECASE)


def _slugify(value: Any, fallback: str = "item") -> str:
    text = str(value or "").strip().lower()
    if not text:
        return fallback
    slug = _SLUG_RE.sub("-", text).strip("-")
    return slug or fallback


def _ensure_unique(base: str, existing: Iterable[str]) -> str:
    base = base or "item"
    if base not in existing:
        return base
    index = 2
    while f"{base}-{index}" in existing:
        index += 1
    return f"{base}-{index}"


def _first_present(payload: Dict[str, Any], keys: Sequence[str]) -> Optional[Any]:
    for key in keys:
        value = payload.get(key)
        if value:
            return value
    return None


def _normalise_tags(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        parts = [chunk.strip() for chunk in value.replace("|", ",").split(",")]
        return [chunk for chunk in parts if chunk]
    if isinstance(value, (list, tuple, set)):
        tags = []
        for entry in value:
            if not entry:
                continue
            if isinstance(entry, str):
                chunk = entry.strip()
                if chunk:
                    tags.append(chunk)
        return tags
    return []


def _extract_emotion(text: str) -> Tuple[Optional[str], str]:
    if not text:
        return None, ""
    match = _EMOTION_RE.search(text)
    if not match:
        return None, text
    emotion = match.group(1).strip()
    cleaned = _EMOTION_RE.sub("", text, count=1).strip()
    return (emotion or None), cleaned


def iter_persona_payloads(payload: Any) -> Iterator[Dict[str, Any]]:
    """Yield persona dictionaries from heterogeneous SillyTavern payloads."""
    if payload is None:
        return
    if isinstance(payload, dict):
        if "personas" in payload:
            yield from iter_persona_payloads(payload["personas"])
            return
        if all(isinstance(v, dict) for v in payload.values()):
            for name, data in payload.items():
                entry = dict(data or {})
                entry.setdefault("name", name)
                yield entry
            return
        yield dict(payload)
        return
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield dict(item)
        return
    # Fallback: unsupported types are ignored.


def iter_chat_payloads(payload: Any) -> Iterator[Dict[str, Any]]:
    """Yield chat transcript dictionaries from SillyTavern payloads."""
    if payload is None:
        return
    if isinstance(payload, dict):
        if "chats" in payload:
            yield from iter_chat_payloads(payload["chats"])
            return
        if all(isinstance(v, dict) for v in payload.values()):
            for name, data in payload.items():
                entry = dict(data or {})
                entry.setdefault("id", entry.get("id") or name)
                yield entry
            return
        yield dict(payload)
        return
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield dict(item)
        return
    # Unsupported shape → ignore


class SillyPersonaImporter:
    """Map SillyTavern persona payloads onto PersonaManager + CharacterManager."""

    def __init__(self, persona_manager: PersonaManager):
        self.persona_manager = persona_manager
        self.character_manager = persona_manager.character_manager

    def import_many(self, payload: Any) -> dict[str, Any]:
        personas: List[dict[str, Any]] = []
        characters: List[dict[str, Any]] = []
        errors: List[dict[str, Any]] = []
        for entry in iter_persona_payloads(payload):
            try:
                result = self.import_one(entry)
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(
                    {
                        "error": str(exc),
                        "name": entry.get("name") or entry.get("id"),
                    }
                )
                continue
            personas.append(result["persona"])
            characters.append(result["character"])
        status = "ok" if personas else "empty"
        return {
            "status": status,
            "imported": len(personas),
            "personas": personas,
            "characters": characters,
            "errors": errors,
        }

    def import_one(self, payload: Dict[str, Any]) -> dict[str, Any]:
        record = dict(payload or {})
        display_name = (
            _first_present(record, ("display_name", "name", "title", "char_name", "id"))
            or "persona"
        )
        base_persona_id = record.get("id") or _slugify(display_name, "persona")
        persona_id = _ensure_unique(
            _slugify(base_persona_id, "persona"), self.persona_manager.personas.keys()
        )

        base_char_id = (
            record.get("character_id")
            or record.get("char_id")
            or record.get("char")  # legacy key
            or _slugify(display_name, "character")
        )
        character_id = _ensure_unique(
            _slugify(base_char_id, "character"),
            self.character_manager.characters.keys(),
        )

        tags = _normalise_tags(
            record.get("tags")
            or record.get("character_tags")
            or record.get("persona_tags")
        )
        avatar = _first_present(
            record,
            (
                "avatar",
                "avatar_url",
                "character_avatar",
                "profile_picture",
            ),
        )

        now = time.time()
        character_payload: Dict[str, Any] = {
            "id": character_id,
            "name": display_name,
            "display_name": display_name,
            "description": _first_present(
                record,
                (
                    "description",
                    "persona",
                    "char_persona",
                    "bio",
                    "summary",
                ),
            )
            or "",
            "tags": tags,
            "avatars": [avatar] if avatar else [],
            "metadata": {
                "source": "SillyTavern",
                "imported_at": now,
                "raw_keys": sorted(record.keys()),
            },
        }
        creator = record.get("creator") or record.get("author")
        if creator:
            character_payload["creator"] = creator
        character = self.character_manager.register_character(
            character_id, character_payload
        )

        role_hint = _first_present(record, ("role", "kind", "persona_role"))
        if not role_hint and record.get("is_player"):
            role_hint = "player"

        greeting = _first_present(record, ("greeting", "first_mes", "intro"))
        persona_profile: Dict[str, Any] = {
            "display_name": display_name,
            "name": display_name,
            "role": role_hint or "npc",
            "summary": character_payload["description"],
            "prompt": _first_present(
                record,
                (
                    "persona",
                    "prompt",
                    "char_persona",
                    "instructions",
                ),
            )
            or character_payload["description"],
            "greeting": greeting or "",
            "tags": tags,
            "metadata": {
                "source": "SillyTavern",
                "imported_at": now,
                "raw_keys": sorted(record.keys()),
            },
        }
        if avatar:
            persona_profile.setdefault("avatar", avatar)
        examples = record.get("example_dialogue") or record.get("mes_example")
        if isinstance(examples, list):
            persona_profile["examples"] = examples

        persona = self.persona_manager.register_persona(
            persona_id,
            persona_profile,
            character_id=character_id,
            role=persona_profile.get("role"),
        )

        return {
            "persona_id": persona_id,
            "character_id": character_id,
            "persona": persona,
            "character": character,
        }


def build_scene_from_chat(chat: Dict[str, Any], store: SceneStore) -> Dict[str, Any]:
    """Convert a SillyTavern chat payload into a ComfyVN scene and persist it."""
    record = dict(chat or {})
    messages = (
        record.get("messages")
        or record.get("chat")
        or record.get("dialogue")
        or record.get("entries")
        or []
    )
    if isinstance(messages, dict):
        # Some exports wrap messages under {"items": [...]}
        messages = messages.get("items") or []

    fallback_title = record.get("title") or record.get("name") or "SillyTavern Chat"
    base_id = record.get("id") or fallback_title
    scene_id = _slugify(base_id, "st-chat")
    dialogue: List[dict[str, Any]] = []
    character_name = record.get("character_name") or record.get("character") or None
    for idx, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        raw_text = (
            message.get("mes")
            or message.get("text")
            or message.get("message")
            or message.get("content")
            or ""
        )
        if not raw_text:
            continue
        emotion, clean_text = _extract_emotion(str(raw_text))
        if not clean_text:
            clean_text = str(raw_text)
        role = message.get("role")
        is_user = bool(
            message.get("is_user") or (isinstance(role, str) and role == "user")
        )
        speaker = (
            message.get("name")
            or (
                message.get("sender")
                if isinstance(message.get("sender"), str)
                else None
            )
            or ("User" if is_user else character_name or "Narrator")
        )
        dialogue.append(
            {
                "index": idx,
                "type": "line",
                "speaker": speaker,
                "text": clean_text.strip(),
                "emotion": emotion,
                "meta": {
                    "is_user": is_user,
                    "id": message.get("id"),
                    "timestamp": message.get("timestamp") or message.get("created_at"),
                },
            }
        )

    scene_payload: Dict[str, Any] = {
        "id": scene_id,
        "title": fallback_title,
        "source": "SillyTavern",
        "created_at": record.get("created_at") or time.time(),
        "dialogue": dialogue,
        "metadata": {
            "sillytavern": {
                "chat_id": record.get("id"),
                "character_name": character_name,
                "user_id": record.get("user_id"),
            }
        },
    }
    saved_id = store.save(scene_id, scene_payload)
    scene_payload["id"] = saved_id
    return scene_payload


def import_chat_scenes(store: SceneStore, payload: Any) -> dict[str, Any]:
    """Import chat payloads into SceneStore entries."""
    scenes: List[dict[str, Any]] = []
    errors: List[dict[str, Any]] = []
    for entry in iter_chat_payloads(payload):
        try:
            scene = build_scene_from_chat(entry, store)
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(
                {"error": str(exc), "id": entry.get("id"), "title": entry.get("title")}
            )
            continue
        scenes.append(scene)
    status = "ok" if scenes else "empty"
    return {
        "status": status,
        "imported": len(scenes),
        "scenes": scenes,
        "errors": errors,
    }


__all__ = [
    "SillyPersonaImporter",
    "build_scene_from_chat",
    "import_chat_scenes",
    "iter_persona_payloads",
    "iter_chat_payloads",
]
