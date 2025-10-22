from __future__ import annotations

import json
import logging
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping

from fastapi import APIRouter, Body, HTTPException

from comfyvn.assets.persona_manager import PersonaManager
from comfyvn.config import feature_flags, runtime_paths
from comfyvn.connectors import FListConnector, FurAffinityUploadManager
from comfyvn.persona.schema import (
    PersonaValidationError,
    build_persona_record,
    merge_tag_sets,
    slugify,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connect", tags=["Community Connectors"])

FEATURE_FLAG = "enable_persona_importers"
NSFW_FLAG = "enable_nsfw_mode"

CONSENT_PATH = runtime_paths.data_dir("persona", "consent.json")
IMPORT_ROOT = runtime_paths.data_dir("persona", "imports")

_PERSONA_MANAGER = PersonaManager()
_FLIST_CONNECTOR = FListConnector()
_FA_UPLOADS = FurAffinityUploadManager(Path(IMPORT_ROOT))

try:  # Optional for CLI-only contexts
    from comfyvn.core import modder_hooks  # type: ignore
except Exception:  # pragma: no cover - optional import guard
    modder_hooks = None  # type: ignore


def _register_hooks() -> None:
    if modder_hooks is None:
        return
    spec_map = modder_hooks.HOOK_SPECS
    if "on_flist_profile_parsed" not in spec_map:
        spec_map["on_flist_profile_parsed"] = modder_hooks.HookSpec(
            name="on_flist_profile_parsed",
            description="Emitted after parsing F-List profile text via connectors.",
            payload_fields={
                "persona_id": "Proposed persona identifier.",
                "persona": "Persona payload produced from F-List text.",
                "warnings": "Warnings emitted during parsing.",
                "debug": "Parsing debug dictionary.",
                "requested_at": "Unix timestamp when parsing completed.",
            },
            ws_topic="modder.on_flist_profile_parsed",
            rest_event="on_flist_profile_parsed",
        )
    if "on_furaffinity_asset_uploaded" not in spec_map:
        spec_map["on_furaffinity_asset_uploaded"] = modder_hooks.HookSpec(
            name="on_furaffinity_asset_uploaded",
            description="Emitted after a FurAffinity image upload is stored.",
            payload_fields={
                "persona_id": "Persona slug used for storage.",
                "assets": "List of stored asset records (path/hash metadata).",
                "debug": "List of debug entries (trimmed tags, filenames).",
                "requested_at": "Unix timestamp when storage completed.",
            },
            ws_topic="modder.on_furaffinity_asset_uploaded",
            rest_event="on_furaffinity_asset_uploaded",
        )
    if "on_connector_persona_mapped" not in spec_map:
        spec_map["on_connector_persona_mapped"] = modder_hooks.HookSpec(
            name="on_connector_persona_mapped",
            description="Emitted after persona mapping via connector endpoints.",
            payload_fields={
                "persona_id": "Stored persona identifier.",
                "persona": "Persona schema payload saved to disk.",
                "character_dir": "Character directory path.",
                "provenance": "Path to persona provenance sidecar.",
                "image_assets": "Image assets considered during mapping.",
                "sources": "Source descriptors attached to persona.",
                "requested_at": "Unix timestamp when the mapping completed.",
            },
            ws_topic="modder.on_connector_persona_mapped",
            rest_event="on_connector_persona_mapped",
        )


_register_hooks()


def _emit_hook(event: str, payload: Dict[str, Any]) -> None:
    if modder_hooks is None:
        return
    try:
        modder_hooks.emit(event, payload)
    except Exception:  # pragma: no cover - defensive
        LOGGER.debug("Connector hook '%s' emission failed", event, exc_info=True)


def _feature_enabled() -> bool:
    return feature_flags.is_enabled(FEATURE_FLAG, default=False)


def _require_feature_enabled() -> None:
    if not _feature_enabled():
        raise HTTPException(
            status_code=403, detail=f"Feature flag '{FEATURE_FLAG}' disabled."
        )


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        LOGGER.debug("Failed to read JSON from %s", path, exc_info=True)
        return {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")


def _load_consent() -> Dict[str, Any]:
    return _read_json(Path(CONSENT_PATH))


def _normalise_sources(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        sources = []
        for item in value:
            text = str(item or "").strip()
            if text:
                sources.append(text)
        return sources
    return []


def _store_consent(
    connector: str,
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    existing = _load_consent()
    consent = dict(existing)
    now = time.time()

    rights = (
        str(payload.get("rights") or consent.get("rights") or "owner").strip()
        or "owner"
    )
    sources = _normalise_sources(payload.get("sources")) or consent.get("sources") or []
    nsfw_allowed = bool(payload.get("nsfw_allowed", consent.get("nsfw_allowed", False)))

    consent["accepted"] = True
    consent["rights"] = rights
    consent["sources"] = sources
    consent["nsfw_allowed"] = nsfw_allowed
    consent["updated_at"] = now
    if "accepted_at" not in consent:
        consent["accepted_at"] = now

    connectors = dict(consent.get("connectors") or {})
    connector_block = {
        "accepted": True,
        "accepted_at": now,
        "nsfw_allowed": bool(payload.get("nsfw_allowed")),
        "profile_url": (str(payload.get("profile_url") or "").strip() or None),
        "notes": (str(payload.get("notes") or "").strip() or None),
        "agent": (str(payload.get("agent") or "").strip() or None),
        "version": int(payload.get("version") or 1),
    }
    connectors[connector] = connector_block
    consent["connectors"] = connectors

    _write_json(Path(CONSENT_PATH), consent)
    return consent


def _require_consent(connector: str) -> Dict[str, Any]:
    consent = _load_consent()
    if not consent or not consent.get("accepted"):
        raise HTTPException(
            status_code=403,
            detail="Consent required before using community connectors.",
        )
    connectors = consent.get("connectors") or {}
    connector_block = connectors.get(connector)
    if not connector_block or not connector_block.get("accepted"):
        raise HTTPException(
            status_code=403,
            detail=f"Connector '{connector}' requires explicit consent.",
        )
    return consent


def _nsfw_allowed(consent: Mapping[str, Any], connector: str) -> bool:
    if not feature_flags.is_enabled(NSFW_FLAG, default=False):
        return False
    if not consent.get("nsfw_allowed"):
        return False
    connectors = consent.get("connectors") or {}
    connector_block = connectors.get(connector) or {}
    return bool(connector_block.get("nsfw_allowed", consent.get("nsfw_allowed")))


def _merge_profile(base: MutableMapping[str, Any], extra: Mapping[str, Any]) -> None:
    for key, value in extra.items():
        if value is None:
            continue
        if key == "tags":
            continue
        if isinstance(value, Mapping):
            target = base.get(key)
            merged: Dict[str, Any]
            if isinstance(target, Mapping):
                merged = dict(target)
            else:
                merged = {}
            _merge_profile(merged, value)
            base[key] = merged
        elif isinstance(value, list):
            existing = list(base.get(key) or [])
            for item in value:
                if item not in existing:
                    existing.append(item)
            base[key] = existing
        else:
            if not base.get(key):
                base[key] = value


def _prepare_tags(*tag_blocks: Mapping[str, Any]) -> Dict[str, Any]:
    prepared: List[Mapping[str, Any]] = []
    for block in tag_blocks:
        if not block:
            continue
        if isinstance(block, Mapping):
            prepared.append(block)
        else:
            model_dump = getattr(block, "model_dump", None)
            if callable(model_dump):
                prepared.append(model_dump())
    if not prepared:
        prepared.append({})
    return merge_tag_sets(*prepared).model_dump()


def _prepare_sources(
    persona_sources: Iterable[Mapping[str, Any]],
    image_assets: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    for entry in persona_sources:
        if not isinstance(entry, Mapping):
            continue
        sources.append(dict(entry))
    for asset in image_assets:
        if not isinstance(asset, Mapping):
            continue
        sources.append(
            {
                "type": "image",
                "value": asset.get("path"),
                "hash": asset.get("hash"),
                "sidecar": asset.get("sidecar"),
            }
        )
    return sources


def _persona_dir(persona_id: str) -> Path:
    return _PERSONA_MANAGER.character_manager.character_dir(persona_id)


@router.post("/flist/consent")
def record_flist_consent(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _require_feature_enabled()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object.")
    accepted = bool(
        payload.get("accepted") or payload.get("accept") or payload.get("acknowledged")
    )
    if not accepted:
        raise HTTPException(status_code=400, detail="Consent acknowledgement required.")

    consent = _store_consent("flist", payload)
    consent["feature_flag"] = _feature_enabled()
    consent["nsfw_flag"] = feature_flags.is_enabled(NSFW_FLAG, default=False)
    return {"ok": True, "consent": consent}


@router.post("/flist/import_text")
def import_flist_text(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _require_feature_enabled()
    consent = _require_consent("flist")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object.")

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="Profile text is required.")

    metadata = payload.get("metadata")
    metadata_map: Dict[str, Any] = {}
    if isinstance(metadata, Mapping):
        metadata_map.update(metadata)
    metadata_map.setdefault("source", "flist")
    if payload.get("profile_url"):
        metadata_map["profile_url"] = str(payload.get("profile_url")).strip()
    metadata_map.setdefault("rights", consent.get("rights"))
    metadata_map.setdefault("sources", consent.get("sources"))

    allow_nsfw = _nsfw_allowed(consent, "flist")

    try:
        result = _FLIST_CONNECTOR.from_text(
            text=text,
            persona_id=payload.get("persona_id"),
            metadata=metadata_map,
            nsfw_allowed=allow_nsfw,
            default_role=str(payload.get("role") or "npc"),
            source_label=metadata_map.get("source"),
        )
    except PersonaValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("F-List import failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="F-List import failed.") from exc

    persona = result.persona
    persona.setdefault("metadata", {})
    persona["metadata"]["consent"] = {
        "rights": consent.get("rights"),
        "sources": consent.get("sources"),
    }
    persona["metadata"]["import_debug"] = result.debug

    requested_at = time.time()
    _emit_hook(
        "on_flist_profile_parsed",
        {
            "persona_id": persona.get("id"),
            "persona": persona,
            "warnings": result.warnings,
            "debug": result.debug,
            "requested_at": requested_at,
        },
    )

    return {
        "ok": True,
        "persona": persona,
        "warnings": result.warnings,
        "debug": result.debug,
        "nsfw": {"allowed": allow_nsfw, "trimmed": result.trimmed},
    }


@router.post("/furaffinity/upload")
def upload_furaffinity_images(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _require_feature_enabled()
    consent = _require_consent("flist")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object.")
    images = payload.get("images")
    if not isinstance(images, list) or not images:
        raise HTTPException(status_code=400, detail="Image list is required.")

    persona_id = payload.get("persona_id") or "pending"
    persona_id = str(persona_id or "pending").strip() or "pending"
    persona_id = slugify(persona_id)

    allow_nsfw = _nsfw_allowed(consent, "flist")
    try:
        stored, debug_entries = _FA_UPLOADS.store_many(
            images,
            persona_id,
            consent=consent,
            allow_nsfw=allow_nsfw,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("FurAffinity upload failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="FurAffinity upload failed."
        ) from exc

    requested_at = time.time()
    _emit_hook(
        "on_furaffinity_asset_uploaded",
        {
            "persona_id": persona_id,
            "assets": stored,
            "debug": debug_entries,
            "requested_at": requested_at,
        },
    )

    return {
        "ok": True,
        "persona_id": persona_id,
        "assets": stored,
        "debug": debug_entries,
        "nsfw": {"allowed": allow_nsfw},
    }


@router.post("/persona/map")
def map_persona(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _require_feature_enabled()
    consent = _require_consent("flist")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object.")

    base_persona = payload.get("text_persona") or payload.get("persona")
    if not isinstance(base_persona, Mapping):
        raise HTTPException(
            status_code=400,
            detail="text_persona payload required for persona mapping.",
        )

    image_traits = payload.get("image_traits")
    if image_traits is not None and not isinstance(image_traits, Mapping):
        raise HTTPException(status_code=400, detail="image_traits must be an object.")

    tag_overrides = payload.get("tags")
    if tag_overrides is not None and not isinstance(tag_overrides, Mapping):
        raise HTTPException(status_code=400, detail="tags must be an object.")

    persona_data = dict(base_persona)
    if image_traits:
        _merge_profile(persona_data, image_traits)
    if tag_overrides:
        persona_data["tags"] = _prepare_tags(
            persona_data.get("tags") or {},
            image_traits.get("tags") if image_traits else {},
            tag_overrides,
        )
    else:
        persona_data["tags"] = _prepare_tags(
            persona_data.get("tags") or {},
            image_traits.get("tags") if image_traits else {},
        )

    persona_id = (
        payload.get("persona_id") or persona_data.get("id") or persona_data.get("name")
    )
    if not persona_id:
        raise HTTPException(status_code=400, detail="persona_id required.")
    persona_id = slugify(persona_id)
    persona_data["id"] = persona_id

    allow_nsfw = _nsfw_allowed(consent, "flist")
    try:
        persona_record, trimmed = build_persona_record(
            persona_data,
            allow_nsfw=allow_nsfw,
            default_role=str(payload.get("role") or persona_data.get("role") or "npc"),
        )
    except PersonaValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    persona_sources = persona_record.get("sources") or []
    sources = _prepare_sources(
        persona_sources,
        payload.get("image_assets") or [],
    )
    persona_record["sources"] = sources

    persona_record.setdefault("metadata", {})
    persona_record["metadata"]["image_assets"] = payload.get("image_assets") or []
    persona_record["metadata"]["consent"] = {
        "rights": consent.get("rights"),
        "sources": consent.get("sources"),
    }
    persona_record["metadata"]["nsfw_trimmed"] = trimmed

    stored = _PERSONA_MANAGER.register_persona(persona_id, persona_record)

    character_dir = _persona_dir(persona_id)
    character_dir.mkdir(parents=True, exist_ok=True)
    persona_path = character_dir / "persona.json"
    _write_json(persona_path, persona_record)

    provenance_path = character_dir / "persona.provenance.json"
    provenance_payload = {
        "persona_id": persona_id,
        "created_at": time.time(),
        "sources": sources,
        "image_assets": payload.get("image_assets") or [],
        "requested_at": payload.get("requested_at") or time.time(),
        "nsfw_allowed": allow_nsfw,
    }
    _write_json(provenance_path, provenance_payload)

    event_payload = {
        "persona_id": persona_id,
        "persona": stored,
        "character_dir": character_dir.as_posix(),
        "provenance": provenance_path.as_posix(),
        "image_assets": payload.get("image_assets") or [],
        "sources": sources,
        "requested_at": provenance_payload["requested_at"],
    }
    _emit_hook("on_connector_persona_mapped", event_payload)
    _emit_hook("on_persona_imported", event_payload)

    return {
        "ok": True,
        "persona": stored,
        "persona_path": persona_path.as_posix(),
        "provenance": provenance_path.as_posix(),
        "nsfw": {"allowed": allow_nsfw, "trimmed": trimmed},
    }
