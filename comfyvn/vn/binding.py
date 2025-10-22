"""
Persona asset binding helpers.

This module links persona JSON definitions emitted by the VN loader to
actual portrait assets on disk.  It guarantees that every persona inside
``data/projects/<project>/personas`` has a ``portraitRef`` pointing to a
registered asset, creates (or refreshes) metadata sidecars, and exposes
helpers that FastAPI routes can call.

When a portrait asset is missing we opportunistically invoke the
ComfyUI hardened bridge to render one based on persona hints.  If the
bridge is unavailable we fall back to writing a 1x1 transparent PNG so
that downstream tooling still has a consistent reference.  Expression
tags are normalised so that scene authors can rely on a small vocabulary
(`happy`, `sad`, `angry`, `shy`, `neutral`, `blush`) regardless of how
the upstream persona encoded their sprite names.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from comfyvn.bridge.comfy_hardening import (
    HardenedBridgeError,
    HardenedBridgeUnavailable,
    HardenedComfyBridge,
)
from comfyvn.studio.core.asset_registry import AssetRegistry

LOGGER = logging.getLogger(__name__)
_BRIDGE = HardenedComfyBridge()

_DEFAULT_STYLE = "default"
_PORTRAIT_FOLDER = Path("portraits")
_ALLOWED_EMOTION_TAGS = ("neutral", "happy", "sad", "angry", "shy", "blush")
_PLACEHOLDER_PNG = bytes.fromhex(
    "89504E470D0A1A0A0000000D4948445200000001000000010802000000907753DE"
    "0000000A49444154789C6360000002000154A20C5B0000000049454E44AE426082"
)
_STYLE_SAFE = re.compile(r"[^a-z0-9._-]+")


@dataclass(slots=True)
class PortraitResult:
    """Lightweight return object for ensure_portrait/link_personas."""

    persona_id: str
    path: str
    style: str
    expression_map: Dict[str, str]
    sidecar: Optional[str]
    registry_uid: Optional[str]
    placeholder: bool
    project_id: Optional[str] = None
    metadata: Dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}

    def as_dict(self) -> Dict[str, Any]:
        return {
            "personaId": self.persona_id,
            "path": self.path,
            "style": self.style,
            "sidecar": self.sidecar,
            "registryUid": self.registry_uid,
            "expressionMap": dict(self.expression_map),
            "placeholder": self.placeholder,
            "projectId": self.project_id,
            "meta": dict(self.metadata),
        }


class PersonaBindingError(RuntimeError):
    """Raised when persona binding operations fail."""


def ensure_portrait(
    persona_id: str,
    style: Optional[str] = None,
    *,
    persona: Optional[Dict[str, Any]] = None,
    project_id: Optional[str] = None,
    force: bool = False,
) -> PortraitResult:
    """
    Guarantee that a portrait asset exists for ``persona_id``.

    Returns a :class:`PortraitResult` describing the asset relative to the
    registry root (e.g. ``portraits/hero/default.png``).
    """

    normalised_id = _normalise_persona_id(persona_id)
    if not normalised_id:
        raise ValueError("persona_id is required")

    safe_style = _normalise_style(style)
    registry = AssetRegistry(project_id=project_id or "default")
    portrait_rel = _PORTRAIT_FOLDER / normalised_id / f"{safe_style}.png"
    portrait_path = (registry.ASSETS_ROOT / portrait_rel).resolve()
    portrait_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.debug(
        "Ensuring portrait asset -> persona=%s style=%s path=%s",
        normalised_id,
        safe_style,
        portrait_path,
    )

    provenance: Dict[str, Any] | None = None
    placeholder_written = False

    artifact_needed = force or not portrait_path.exists()
    if artifact_needed:
        render_result = _render_portrait_with_bridge(
            normalised_id,
            safe_style,
            persona=persona,
            project_id=project_id,
        )
        if render_result:
            provenance = render_result["provenance"]
            source_path = render_result["artifact_path"]
            try:
                shutil.copy2(source_path, portrait_path)
                LOGGER.info(
                    "Copied rendered portrait for %s (%s) from %s",
                    normalised_id,
                    safe_style,
                    source_path,
                )
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning(
                    "Failed to copy rendered portrait for %s (%s): %s",
                    normalised_id,
                    safe_style,
                    exc,
                )
                _write_placeholder(portrait_path)
                placeholder_written = True
        else:
            _write_placeholder(portrait_path)
            placeholder_written = True

    existing_sidecar = _read_existing_sidecar(portrait_path)
    expression_map = _resolve_expression_map(persona, existing_sidecar)
    sidecar_placeholder = False
    if existing_sidecar:
        meta_section = existing_sidecar.get("meta")
        if isinstance(meta_section, dict):
            sidecar_placeholder = bool(meta_section.get("placeholder"))
    metadata = _build_metadata(
        persona=persona,
        persona_id=normalised_id,
        style=safe_style,
        expression_map=expression_map,
        placeholder=placeholder_written or sidecar_placeholder,
        project_id=project_id,
    )

    registration = registry.register_file(
        portrait_path,
        "portraits",
        copy=False,
        metadata=metadata,
        provenance=provenance,
    )
    result = PortraitResult(
        persona_id=normalised_id,
        path=str(portrait_rel.as_posix()),
        style=safe_style,
        expression_map=expression_map,
        sidecar=registration.get("sidecar"),
        registry_uid=registration.get("uid"),
        placeholder=placeholder_written,
        project_id=project_id,
        metadata=metadata,
    )
    return result


def link_personas(
    project_id: str,
    *,
    persona_id: Optional[str] = None,
    style: Optional[str] = None,
    force: bool = False,
) -> List[PortraitResult]:
    """
    Iterate over persona JSON files for ``project_id`` and ensure portraits.
    """

    safe_project = _normalise_project_id(project_id)
    personas_dir = Path("data/projects") / safe_project / "personas"
    if not personas_dir.exists():
        raise PersonaBindingError(
            f"Persona directory not found for project '{safe_project}'"
        )

    target_ids: set[str] | None = None
    if persona_id:
        target_ids = {persona_id.strip().lower()}

    updated: List[PortraitResult] = []
    for file_path in sorted(personas_dir.glob("*.json")):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("Skipping persona file %s (unreadable: %s)", file_path, exc)
            continue
        if not isinstance(payload, dict):
            LOGGER.warning("Skipping persona file %s (expected object)", file_path)
            continue

        persona_entry = dict(payload)
        internal_id = persona_entry.get("id") or file_path.stem
        normalised_id = _normalise_persona_id(internal_id)
        persona_entry.setdefault("id", normalised_id)

        if target_ids and normalised_id.lower() not in target_ids:
            continue

        should_link = force or not persona_entry.get("portraitRef")
        try:
            portrait = ensure_portrait(
                normalised_id,
                style=style,
                persona=persona_entry,
                project_id=safe_project,
                force=force,
            )
        except ValueError as exc:
            LOGGER.warning("Persona %s skipped (invalid id): %s", normalised_id, exc)
            continue

        if should_link or persona_entry.get("portraitRef") != portrait.path:
            persona_entry["portraitRef"] = portrait.path

        persona_entry.setdefault("portraitStyle", portrait.style)
        persona_entry["portraitExpressions"] = portrait.expression_map

        try:
            file_path.write_text(
                json.dumps(persona_entry, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Failed to update persona file %s: %s", file_path, exc)
            raise PersonaBindingError(
                f"Unable to update persona file {file_path}"
            ) from exc

        updated.append(portrait)

    if target_ids and not updated:
        raise PersonaBindingError(
            f"Persona '{persona_id}' not found in project '{safe_project}'."
        )
    return updated


# --------------------------------------------------------------------------- helpers


def _normalise_persona_id(persona_id: Optional[str]) -> str:
    if not persona_id:
        return ""
    text = str(persona_id).strip()
    text = text.replace(" ", "_")
    return re.sub(r"[^a-zA-Z0-9._-]", "_", text)


def _normalise_project_id(project_id: Optional[str]) -> str:
    if not project_id:
        raise ValueError("project_id is required")
    text = str(project_id).strip()
    if not text:
        raise ValueError("project_id cannot be blank")
    return text


def _normalise_style(style: Optional[str]) -> str:
    if style is None:
        return _DEFAULT_STYLE
    text = str(style).strip().lower()
    if not text:
        return _DEFAULT_STYLE
    return _STYLE_SAFE.sub("_", text)


def _write_placeholder(target: Path) -> None:
    try:
        target.write_bytes(_PLACEHOLDER_PNG)
        LOGGER.debug("Placeholder portrait written -> %s", target)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.error("Failed to write placeholder portrait %s: %s", target, exc)
        raise PersonaBindingError(
            f"Unable to write portrait placeholder {target}"
        ) from exc


def _render_portrait_with_bridge(
    persona_id: str,
    style: str,
    *,
    persona: Optional[Dict[str, Any]],
    project_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Attempt to render a portrait via the hardened Comfy bridge.
    """

    try:
        _BRIDGE.reload()
    except Exception:  # pragma: no cover - defensive
        LOGGER.debug("Bridge reload failed; continuing with previous config.")
    if not getattr(_BRIDGE, "enabled", True):
        LOGGER.debug("Bridge disabled; skipping render for %s/%s", persona_id, style)
        return None

    workflow_id = _resolve_workflow_id(persona, style)
    payload: Dict[str, Any] = {
        "workflow_id": workflow_id,
        "metadata": {
            "persona_id": persona_id,
            "style": style,
            "project_id": project_id,
            "channel": "portrait",
        },
        "inputs": {
            "persona": persona_id,
            "style": style,
        },
        "characters": _resolve_character_refs(persona),
    }
    prompt_hint = _resolve_prompt_hint(persona)
    if prompt_hint:
        payload["inputs"]["prompt"] = prompt_hint
        payload["prompt"] = prompt_hint

    workflow_path = _resolve_workflow_path(persona)
    if workflow_path:
        payload["workflow_path"] = workflow_path

    try:
        result = _BRIDGE.submit(payload)
    except HardenedBridgeUnavailable as exc:
        LOGGER.warning("ComfyUI backend unavailable for %s: %s", persona_id, exc)
        return None
    except HardenedBridgeError as exc:
        LOGGER.warning("ComfyUI bridge rejected persona %s: %s", persona_id, exc)
        return None
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Unexpected ComfyUI failure for %s: %s", persona_id, exc)
        return None

    primary = result.get("primary_artifact") or {}
    artifact_path = Path(str(primary.get("path") or "")).expanduser()
    if not artifact_path.exists():
        LOGGER.debug(
            "Bridge reported success but artifact missing for %s (%s)",
            persona_id,
            style,
        )
        return None

    sidecar_payload = result.get("sidecar") or {}
    sidecar_path_str = sidecar_payload.get("path")
    sidecar_path = Path(sidecar_path_str).expanduser() if sidecar_path_str else None

    provenance = {
        "source": "vn.binding.ensure_portrait",
        "workflow_hash": result.get("workflow_id"),
        "inputs": {
            "persona_id": persona_id,
            "style": style,
            "project_id": project_id,
            "prompt_hint": prompt_hint,
        },
        "bridge_context": {
            key: result.get(key)
            for key in ("prompt_id", "history", "overrides", "context")
            if result.get(key) is not None
        },
    }

    return {
        "artifact_path": artifact_path,
        "sidecar_path": sidecar_path,
        "result": result,
        "provenance": provenance,
    }


def _resolve_workflow_id(persona: Optional[Dict[str, Any]], style: str) -> str:
    if persona:
        candidates: Sequence[str] = (
            persona.get("portraitWorkflowId"),
            persona.get("workflowId"),
            persona.get("workflow_id"),
        )
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return f"persona.portrait.{style}"


def _resolve_workflow_path(persona: Optional[Dict[str, Any]]) -> Optional[str]:
    if not persona:
        return None
    for key in ("portraitWorkflowPath", "workflowPath", "workflow_path"):
        value = persona.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_character_refs(persona: Optional[Dict[str, Any]]) -> List[str]:
    if not persona:
        return []
    entries: List[str] = []
    for key in ("characterId", "character_id", "character", "characters"):
        value = persona.get(key)
        if isinstance(value, str) and value.strip():
            entries.append(value.strip())
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                text = str(item).strip()
                if text:
                    entries.append(text)
    deduped: List[str] = []
    seen: set[str] = set()
    for entry in entries:
        lowered = entry.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(entry)
    return deduped


def _resolve_prompt_hint(persona: Optional[Dict[str, Any]]) -> Optional[str]:
    if not persona:
        return None
    for key in (
        "portraitPrompt",
        "prompt",
        "appearancePrompt",
        "description",
        "bio",
    ):
        value = persona.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    appearance = persona.get("appearance")
    if isinstance(appearance, dict):
        for key in ("prompt", "description", "summary"):
            value = appearance.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _build_metadata(
    *,
    persona: Optional[Dict[str, Any]],
    persona_id: str,
    style: str,
    expression_map: Dict[str, str],
    placeholder: bool,
    project_id: Optional[str],
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "persona_id": persona_id,
        "style": style,
        "channel": "portrait",
        "expression_map": expression_map,
    }
    if project_id:
        metadata["project_id"] = project_id
    if placeholder:
        metadata["placeholder"] = True
    if persona and persona.get("tags"):
        metadata["tags"] = _normalise_tags(persona.get("tags"))
    if persona and persona.get("displayName"):
        metadata["display_name"] = str(persona.get("displayName")).strip()
    return metadata


def _normalise_tags(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = re.split(r"[,\|;]", value)
    elif isinstance(value, Iterable):
        values = value
    else:
        values = [value]
    tags: List[str] = []
    seen: set[str] = set()
    for entry in values:
        text = str(entry or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        tags.append(text)
    return tags


def _resolve_expression_map(
    persona: Optional[Dict[str, Any]], existing_sidecar: Optional[Dict[str, Any]]
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if persona:
        mapping.update(_extract_expression_map(persona))

    if existing_sidecar:
        meta = existing_sidecar.get("meta")
        if isinstance(meta, dict):
            sidecar_map = _extract_expression_map(meta)
            if sidecar_map:
                mapping.update(sidecar_map)

    normalised: Dict[str, str] = {}
    for tag in _ALLOWED_EMOTION_TAGS:
        value = mapping.get(tag)
        if not value:
            value = _default_expression_name(tag)
        normalised[tag] = value
    return normalised


def _default_expression_name(tag: str) -> str:
    defaults = {
        "neutral": "neutral",
        "happy": "smile",
        "sad": "frown",
        "angry": "angry",
        "shy": "shy",
        "blush": "blush",
    }
    return defaults.get(tag, tag)


def _extract_expression_map(payload: Dict[str, Any]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    candidates: Sequence[Any] = (
        payload.get("portraitExpressions"),
        payload.get("expressionMap"),
        payload.get("emotionMap"),
        payload.get("expressions"),
        payload.get("expression_map"),
        payload.get("emotion_map"),
    )
    for candidate in candidates:
        mapping.update(_coerce_expression_entries(candidate))

    # Handle nested structures such as {"portrait": {"happy": "smile"}}
    nested = payload.get("portrait")
    if isinstance(nested, dict):
        mapping.update(_coerce_expression_entries(nested.get("expressions")))

    return {k: v for k, v in mapping.items() if k in _ALLOWED_EMOTION_TAGS}


def _coerce_expression_entries(value: Any) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if value is None:
        return result
    if isinstance(value, dict):
        for key, raw in value.items():
            tag = str(key or "").strip().lower()
            expr = str(raw or "").strip()
            if tag and expr:
                result[tag] = expr
        return result
    if isinstance(value, list):
        for entry in value:
            if isinstance(entry, dict):
                tag = (
                    str(
                        entry.get("tag")
                        or entry.get("emotion")
                        or entry.get("name")
                        or ""
                    )
                    .strip()
                    .lower()
                )
                expr = str(
                    entry.get("expression")
                    or entry.get("value")
                    or entry.get("sprite")
                    or entry.get("name")
                    or ""
                ).strip()
                if tag and expr:
                    result[tag] = expr
    return result


def _read_existing_sidecar(portrait_path: Path) -> Optional[Dict[str, Any]]:
    sidecar_path = portrait_path.with_suffix(portrait_path.suffix + ".asset.json")
    if not sidecar_path.exists():
        return None
    try:
        return json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover - defensive
        LOGGER.debug("Failed to parse existing sidecar %s", sidecar_path)
        return None
