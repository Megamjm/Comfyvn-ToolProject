from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from fastapi import HTTPException

from comfyvn.server.modules import export_api

from .thumbnailer import MiniVNThumbnail, MiniVNThumbnailer

LOGGER = logging.getLogger(__name__)


def _iter_timeline_entries(
    payload: Mapping[str, Any]
) -> Iterable[Tuple[str, Mapping[str, Any]]]:
    for entry in payload.get("scene_order", []) or []:
        if isinstance(entry, str):
            yield entry, {}
            continue
        if isinstance(entry, Mapping):
            scene_id = entry.get("scene_id") or entry.get("id")
            yield str(scene_id) if scene_id else "", entry


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(canonical).hexdigest()


def _scene_digest(scene: Mapping[str, Any]) -> str:
    minimal = deepcopy(scene)
    minimal.pop("runtime", None)
    return _canonical_digest(minimal)


def _scene_preview(scene: Mapping[str, Any]) -> str:
    dialogue = scene.get("dialogue") or scene.get("lines") or []
    for entry in dialogue:
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                return text
        elif isinstance(entry, Mapping):
            text = entry.get("text") or entry.get("line") or entry.get("content")
            if isinstance(text, str) and text.strip():
                return text.strip()
    title = scene.get("title") or ""
    return title if isinstance(title, str) else ""


def _collect_scene_povs(scene: Mapping[str, Any]) -> Dict[str, str]:
    povs: Dict[str, str] = {}

    def _register(pov_id: Any, display: Any) -> None:
        if not pov_id:
            return
        key = str(pov_id).strip()
        if not key:
            return
        label = ""
        if isinstance(display, str):
            label = display.strip()
        if key not in povs or not povs[key]:
            povs[key] = label or key

    def _register_collection(payload: Any) -> None:
        if isinstance(payload, str):
            _register(payload, None)
            return
        if isinstance(payload, Mapping):
            _register(
                payload.get("id") or payload.get("pov"),
                payload.get("name") or payload.get("label") or payload.get("title"),
            )
            return
        if isinstance(payload, Iterable):
            for entry in payload:
                _register_collection(entry)

    def _scan(payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        _register(
            payload.get("pov"),
            payload.get("pov_name") or payload.get("name") or payload.get("title"),
        )
        _register_collection(payload.get("povs") or payload.get("perspectives"))
        nested = payload.get("meta") or payload.get("metadata")
        if nested:
            _scan(nested)

    _scan(scene)
    meta = scene.get("meta") or scene.get("metadata")
    if meta:
        _scan(meta)
    nodes = scene.get("nodes") or []
    for node in nodes:
        _scan(node)
        content = node.get("content") if isinstance(node, Mapping) else None
        if content:
            _scan(content)
    dialogue = scene.get("dialogue") or scene.get("lines") or []
    for entry in dialogue:
        _scan(entry)

    return povs


def _placement_povs(placement: Mapping[str, Any]) -> Dict[str, str]:
    values = placement.get("povs") or placement.get("pov_values") or []
    names = placement.get("pov_names") or {}
    catalog: Dict[str, str] = {}
    if isinstance(values, (list, tuple, set)):
        for value in values:
            key = str(value).strip()
            if not key:
                continue
            display = names.get(value) if isinstance(names, Mapping) else None
            if display is None and isinstance(names, Mapping):
                display = names.get(key)
            label = str(display).strip() if isinstance(display, str) else ""
            catalog[key] = label or key
    return catalog


class MiniVNPlayer:
    """Deterministic Mini-VN player for viewer fallbacks and thumbnail capture."""

    def __init__(
        self,
        project_id: str,
        *,
        project_path: Optional[Path] = None,
        timeline_id: Optional[str] = None,
    ) -> None:
        self.project_id = project_id
        self.project_path = Path(project_path) if project_path else None
        self._explicit_timeline = timeline_id
        self._thumbnailer = MiniVNThumbnailer()

    def generate_snapshot(
        self,
        *,
        seed: int = 0,
        pov: Optional[str] = None,
        timeline_id: Optional[str] = None,
    ) -> Tuple[dict[str, Any], Dict[str, MiniVNThumbnail]]:
        project_data, _ = self._load_project()
        timeline_payload, _, resolved_timeline = export_api._ensure_timeline_payload(
            timeline_id or self._explicit_timeline,
            self.project_id,
            project_data,
        )

        scenes_payload: List[dict[str, Any]] = []
        thumbnail_records: Dict[str, MiniVNThumbnail] = {}
        active_keys: List[str] = []
        pov_catalog: Dict[str, str] = {}
        digest_material: List[dict[str, str]] = []

        for index, (scene_id, placement) in enumerate(
            _iter_timeline_entries(timeline_payload)
        ):
            if not scene_id:
                continue
            try:
                scene_data, scene_path = export_api._load_scene(
                    scene_id, self.project_id
                )
            except HTTPException as exc:
                LOGGER.debug(
                    "Mini-VN missing scene %s for project %s: %s",
                    scene_id,
                    self.project_id,
                    exc,
                )
                scenes_payload.append(
                    {
                        "scene_id": scene_id,
                        "order": index,
                        "missing": True,
                        "error": str(exc.detail if hasattr(exc, "detail") else exc),
                    }
                )
                continue

            scene_digest = _scene_digest(scene_data)
            digest_material.append({"scene_id": scene_id, "digest": scene_digest})
            scene_povs = _collect_scene_povs(scene_data)
            placement_pov_map = _placement_povs(placement)
            for pov_id, label in placement_pov_map.items():
                scene_povs.setdefault(pov_id, label)
            for pov_id, label in scene_povs.items():
                if pov_id and pov_id not in pov_catalog:
                    pov_catalog[pov_id] = label

            preview_text = _scene_preview(scene_data)
            thumbnail = self._thumbnailer.capture(
                scene_id=scene_id,
                digest=scene_digest,
                title=scene_data.get("title") or scene_id,
                subtitle=preview_text,
                pov=next(iter(scene_povs.keys())) if scene_povs else None,
                seed=int(seed),
                timeline_id=resolved_timeline,
            )
            thumbnail_records[thumbnail.key] = thumbnail
            active_keys.append(thumbnail.key)

            scenes_payload.append(
                {
                    "scene_id": scene_id,
                    "order": index,
                    "title": scene_data.get("title") or scene_id,
                    "digest": scene_digest,
                    "pov_values": sorted(scene_povs.keys()),
                    "pov_names": scene_povs,
                    "preview_text": preview_text,
                    "source": scene_path.as_posix(),
                    "thumbnail": thumbnail.to_dict(),
                }
            )

        self._thumbnailer.purge(active_keys)

        canonical_digest = hashlib.sha256(
            json.dumps(
                {
                    "project": self.project_id,
                    "timeline": resolved_timeline,
                    "seed": int(seed),
                    "pov": pov or "",
                    "scenes": digest_material,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        snapshot = {
            "project_id": self.project_id,
            "timeline_id": resolved_timeline,
            "title": timeline_payload.get("title") or resolved_timeline,
            "seed": int(seed),
            "pov": pov,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scenes": scenes_payload,
            "povs": [
                {"id": pid, "name": name or pid} for pid, name in pov_catalog.items()
            ],
            "thumbnails": [record.to_dict() for record in thumbnail_records.values()],
            "digest": canonical_digest,
        }
        return snapshot, thumbnail_records

    def _load_project(self) -> Tuple[dict[str, Any], Optional[Path]]:
        try:
            return export_api._load_project(self.project_id)
        except HTTPException as exc:
            LOGGER.debug(
                "Mini-VN project manifest missing for %s: %s", self.project_id, exc
            )
            placeholder = {
                "id": self.project_id,
                "title": self.project_id,
                "timeline_id": self._explicit_timeline or "main",
                "scenes": [],
            }
            return placeholder, None


__all__ = ["MiniVNPlayer"]
