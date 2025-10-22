from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

from fastapi import APIRouter, Body, HTTPException

from comfyvn.assets.persona_manager import PersonaManager
from comfyvn.config import feature_flags, runtime_paths
from comfyvn.persona.importers.community import CommunityProfileImporter
from comfyvn.persona.schema import (
    PersonaValidationError,
    build_persona_record,
    merge_tag_sets,
    slugify,
    summarise_persona,
)
from comfyvn.server import jobs_api

try:  # Optional for CLI builds without GUI context
    from comfyvn.core import modder_hooks  # type: ignore
except Exception:  # pragma: no cover - optional import guard
    modder_hooks = None  # type: ignore

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/persona", tags=["Persona Importers"])

FEATURE_FLAG = "enable_persona_importers"
NSFW_FLAG = "enable_nsfw_mode"

CONSENT_PATH = runtime_paths.data_dir("persona", "consent.json")
IMPORT_ROOT = runtime_paths.data_dir("persona", "imports")

_PERSONA_MANAGER = PersonaManager()
_TEXT_IMPORTER = CommunityProfileImporter()

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_MEDIA_EXTENSION_MAP = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}


def _register_persona_hooks() -> None:
    if modder_hooks is None:
        return
    spec_map = modder_hooks.HOOK_SPECS
    if "on_persona_imported" not in spec_map:
        spec_map["on_persona_imported"] = modder_hooks.HookSpec(
            name="on_persona_imported",
            description="Emitted after community persona imports are mapped and saved.",
            payload_fields={
                "persona_id": "Stable persona identifier.",
                "persona": "Persona schema payload saved to disk.",
                "character_dir": "Folder containing persona.json + provenance.",
                "sidecar": "Path to the persona provenance sidecar.",
                "image_assets": "List of stored image assets used for inference.",
                "sources": "Source descriptors (text/image) for provenance.",
                "requested_at": "Unix timestamp when the import completed.",
            },
            ws_topic="modder.on_persona_imported",
            rest_event="on_persona_imported",
        )


_register_persona_hooks()


def _emit_hook(event: str, payload: Dict[str, Any]) -> None:
    if modder_hooks is None:
        return
    try:
        modder_hooks.emit(event, payload)
    except Exception:  # pragma: no cover - defensive
        LOGGER.debug("Persona hook '%s' emission failed", event, exc_info=True)


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


def _save_consent(payload: Mapping[str, Any]) -> Dict[str, Any]:
    data = dict(payload)
    data["saved_at"] = time.time()
    _write_json(Path(CONSENT_PATH), data)
    return data


def _require_consent() -> Dict[str, Any]:
    consent = _load_consent()
    if not consent or not consent.get("accepted"):
        raise HTTPException(
            status_code=403,
            detail="Consent required before importing personas.",
        )
    return consent


def _nsfw_allowed(consent: Mapping[str, Any]) -> bool:
    if not feature_flags.is_enabled(NSFW_FLAG, default=False):
        return False
    return bool(consent.get("nsfw_allowed"))


def _resolve_extension(filename: Optional[str], media_type: Optional[str]) -> str:
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in _IMAGE_EXTENSIONS:
            return ext
    if media_type:
        return _MEDIA_EXTENSION_MAP.get(media_type.lower(), ".png")
    return ".png"


def _store_image_asset(
    entry: Mapping[str, Any],
    persona_id: str,
    consent: Mapping[str, Any],
) -> Dict[str, Any]:
    data_field = entry.get("data") or entry.get("base64")
    if not isinstance(data_field, str) or not data_field.strip():
        raise HTTPException(status_code=400, detail="Image entry missing base64 data.")
    try:
        blob = base64.b64decode(data_field, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 payload.") from exc
    if not blob:
        raise HTTPException(status_code=400, detail="Image payload is empty.")

    sha = hashlib.sha256(blob).hexdigest()
    filename = entry.get("filename")
    ext = _resolve_extension(filename, entry.get("media_type"))
    persona_folder = Path(IMPORT_ROOT) / persona_id
    persona_folder.mkdir(parents=True, exist_ok=True)
    target = persona_folder / f"{sha}{ext}"
    target.write_bytes(blob)

    sidecar = target.with_suffix(target.suffix + ".meta.json")
    sidecar_payload = {
        "hash": sha,
        "persona_id": persona_id,
        "created_at": time.time(),
        "size": len(blob),
        "filename": filename,
        "media_type": entry.get("media_type"),
        "source": entry.get("source") or "upload",
        "rights": consent.get("rights"),
        "consent_sources": consent.get("sources"),
    }
    _write_json(sidecar, sidecar_payload)

    return {
        "hash": sha,
        "path": target.as_posix(),
        "sidecar": sidecar.as_posix(),
        "size": len(blob),
        "filename": filename or f"{sha}{ext}",
        "created_at": sidecar_payload["created_at"],
    }


def _persona_dir(persona_id: str) -> Path:
    return _PERSONA_MANAGER.character_manager.character_dir(persona_id)


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


@router.post("/consent")
def record_consent(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _require_feature_enabled()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object.")
    accepted = bool(
        payload.get("accepted") or payload.get("accept") or payload.get("acknowledged")
    )
    if not accepted:
        raise HTTPException(status_code=400, detail="Consent acknowledgement required.")

    sources = payload.get("sources")
    if isinstance(sources, str):
        sources = [sources]
    if not isinstance(sources, list):
        sources = []
    resolved_sources = [
        str(item).strip() for item in sources if str(item or "").strip()
    ]

    consent = {
        "accepted": True,
        "rights": str(payload.get("rights") or "owner").strip() or "owner",
        "sources": resolved_sources,
        "notes": str(payload.get("notes") or "").strip() or None,
        "agent": str(payload.get("agent") or "").strip() or None,
        "accepted_at": time.time(),
        "nsfw_allowed": bool(payload.get("nsfw_allowed")),
        "version": 1,
    }
    stored = _save_consent(consent)
    stored["feature_flag"] = _feature_enabled()
    stored["nsfw_flag"] = feature_flags.is_enabled(NSFW_FLAG, default=False)
    return {"ok": True, "consent": stored}


@router.post("/import/text")
def import_text(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _require_feature_enabled()
    consent = _require_consent()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object.")
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="Profile text is required.")

    metadata = payload.get("metadata")
    metadata_map: Dict[str, Any] = {}
    if isinstance(metadata, Mapping):
        metadata_map.update(metadata)
    metadata_map.setdefault("source", payload.get("source") or "user")
    metadata_map.setdefault("rights", consent.get("rights"))
    metadata_map.setdefault("sources", consent.get("sources"))

    allow_nsfw = _nsfw_allowed(consent)

    try:
        result = _TEXT_IMPORTER.from_text(
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
        LOGGER.warning("Persona text import failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Persona import failed.") from exc

    persona = result["persona"]
    persona.setdefault("metadata", {})
    persona["metadata"]["consent"] = {
        "rights": consent.get("rights"),
        "sources": consent.get("sources"),
    }
    persona["metadata"]["import_debug"] = result["debug"]

    return {
        "ok": True,
        "persona": persona,
        "warnings": result["warnings"],
        "nsfw": {"allowed": allow_nsfw, "trimmed": result["trimmed"]},
    }


@router.post("/import/images")
def import_images(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _require_feature_enabled()
    consent = _require_consent()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object.")
    images = payload.get("images")
    if not isinstance(images, list) or not images:
        raise HTTPException(status_code=400, detail="Image list is required.")

    persona_id = payload.get("persona_id") or "pending"
    persona_id = str(persona_id or "pending").strip() or "pending"
    persona_id = slugify(persona_id)

    stored: List[Dict[str, Any]] = []
    for entry in images:
        if not isinstance(entry, Mapping):
            raise HTTPException(
                status_code=400, detail="Image entries must be objects."
            )
        stored.append(_store_image_asset(entry, persona_id, consent))

    allow_nsfw = _nsfw_allowed(consent)
    job_payload = {
        "type": "persona.image2persona",
        "persona_id": persona_id,
        "images": stored,
        "nsfw_allowed": allow_nsfw,
        "requested_at": time.time(),
    }
    job_result = jobs_api.submit(job_payload)

    return {
        "ok": True,
        "persona_id": persona_id,
        "images": stored,
        "job": job_result,
        "nsfw": {"allowed": allow_nsfw},
    }


def _prepare_map_sources(
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


@router.post("/map")
def map_persona(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _require_feature_enabled()
    consent = _require_consent()
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

    allow_nsfw = _nsfw_allowed(consent)
    try:
        persona_record, trimmed = build_persona_record(
            persona_data,
            allow_nsfw=allow_nsfw,
            default_role=str(payload.get("role") or persona_data.get("role") or "npc"),
        )
    except PersonaValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sources = _prepare_map_sources(
        persona_record.get("sources") or [],
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

    _emit_hook(
        "on_persona_imported",
        {
            "persona_id": persona_id,
            "persona": stored,
            "character_dir": character_dir.as_posix(),
            "sidecar": provenance_path.as_posix(),
            "image_assets": payload.get("image_assets") or [],
            "sources": sources,
            "requested_at": provenance_payload["requested_at"],
        },
    )

    return {
        "ok": True,
        "persona": stored,
        "persona_path": persona_path.as_posix(),
        "provenance": provenance_path.as_posix(),
    }


@router.post("/preview")
def preview_persona(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    _require_feature_enabled()
    consent = _require_consent()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object.")
    base_persona = payload.get("text_persona") or payload.get("persona")
    if not isinstance(base_persona, Mapping):
        raise HTTPException(status_code=400, detail="text_persona payload required.")

    preview_data = dict(base_persona)
    overlay = payload.get("image_traits")
    if isinstance(overlay, Mapping):
        _merge_profile(preview_data, overlay)
    if "tags" in payload and isinstance(payload["tags"], Mapping):
        preview_data["tags"] = _prepare_tags(
            preview_data.get("tags") or {},
            overlay.get("tags") if overlay else {},
            payload["tags"],
        )
    else:
        preview_data["tags"] = _prepare_tags(
            preview_data.get("tags") or {}, overlay.get("tags") if overlay else {}
        )

    preview_data["id"] = slugify(
        payload.get("persona_id") or preview_data.get("id") or preview_data.get("name")
    )

    allow_nsfw = _nsfw_allowed(consent)
    try:
        persona_record, trimmed = build_persona_record(
            preview_data,
            allow_nsfw=allow_nsfw,
            default_role=str(preview_data.get("role") or "npc"),
        )
    except PersonaValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summary = summarise_persona(persona_record)
    summary["nsfw"] = {"allowed": allow_nsfw, "trimmed": trimmed}

    return {"ok": True, "persona": persona_record, "summary": summary}
