"""
Shared helpers for Ren'Py export flows (CLI + HTTP).

The functions in this module are used by both the FastAPI routes and the
command-line utilities to keep provenance payloads and manifest generation
consistent.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from fastapi import HTTPException

from comfyvn.server.modules import export_api


def slugify(value: str, fallback: str = "export") -> str:
    """
    Normalise ``value`` into a filesystem-friendly slug.

    The implementation mirrors the existing export helpers: strips unsafe
    characters, collapses whitespace, and keeps the slug deterministic so
    callers can reliably reference the output directory.
    """

    if not value:
        return fallback
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    slug = slug.strip("._-")
    return slug or fallback


def _is_battle_scene(scene_id: str, label: str) -> bool:
    token = f"{scene_id} {label}".lower()
    return "battle" in token


def build_label_manifest(
    export_result: Any, *, weather_bake: bool = False
) -> Dict[str, Any]:
    """
    Construct a label manifest from a ``RenPyOrchestrator.export`` result.
    """

    manifest: Dict[str, Any] = {
        "project": export_result.project_id,
        "timeline": export_result.timeline_id,
        "generated_at": export_result.generated_at,
        "weather_bake": bool(weather_bake),
        "pov": export_result.manifest_payload.get("pov"),
        "worlds": export_result.world_selection,
        "scenes": export_result.label_map,
        "pov_labels": [],
        "battle_labels": [],
    }
    for entry in export_result.label_map or []:
        if not isinstance(entry, dict):
            continue
        scene_id = entry.get("scene_id")
        label = entry.get("label")
        if not scene_id or not label:
            continue
        manifest["pov_labels"].append(
            {
                "scene_id": scene_id,
                "label": label,
                "pov_ids": list(entry.get("pov_ids") or []),
                "pov_names": entry.get("povs") or {},
            }
        )
        if _is_battle_scene(str(scene_id), str(label)):
            digest = hashlib.sha1(f"{scene_id}:{label}".encode("utf-8")).hexdigest()
            manifest["battle_labels"].append(
                {
                    "scene_id": scene_id,
                    "label": label,
                    "hash": digest[:12],
                }
            )

    return manifest


def write_label_manifest(output_dir: Path, manifest: Dict[str, Any]) -> Path:
    """
    Persist ``manifest`` to ``<output_dir>/label_manifest.json``.
    """

    path = output_dir / "label_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def collect_scene_payloads(
    project_id: str, scene_ids: Iterable[str]
) -> Tuple[Dict[str, Any], Dict[str, Path]]:
    """
    Load scene payloads + source paths for provenance generation.
    """

    scenes: Dict[str, Any] = {}
    scene_sources: Dict[str, Path] = {}
    for scene_id in scene_ids:
        if not scene_id:
            continue
        try:
            scene, scene_path = export_api._load_scene(scene_id, project_id)
        except HTTPException:
            continue
        if scene:
            scenes[scene_id] = scene
        if scene_path:
            scene_sources[scene_id] = scene_path
    return scenes, scene_sources


def generate_provenance_bundle(
    export_result: Any,
    *,
    timeline_id: str,
    project_data: dict,
    timeline_data: dict,
    timeline_path: Path,
    bundle_path: Path | None = None,
) -> Tuple[Path, Path, Dict[str, Any]]:
    """
    Build the Studio provenance bundle + flattened ``provenance.json``.
    """

    scene_ids = export_api._scene_ids_from_timeline(timeline_data, project_data)
    scenes, scene_sources = collect_scene_payloads(export_result.project_id, scene_ids)
    renpy_info = {
        "generated_at": export_result.generated_at,
        "renpy_root": export_result.output_dir,
        "script_path": export_result.script_path,
        "labels": export_result.label_map,
        "scenes": scenes,
        "scene_sources": scene_sources,
    }
    target = (
        bundle_path
        if bundle_path is not None
        else export_result.output_dir / "provenance_bundle.zip"
    )
    bundle_path, provenance, enforcement = export_api._build_bundle_archive(
        project_id=export_result.project_id,
        project_data=project_data,
        timeline_id=timeline_id,
        timeline_data=timeline_data,
        timeline_path=timeline_path,
        renpy_info=renpy_info,
        bundle_path=target,
    )
    provenance_path = export_result.output_dir / "provenance.json"
    provenance_path.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    enforcement_payload = (
        enforcement.to_dict() if hasattr(enforcement, "to_dict") else {}
    )
    return bundle_path, provenance_path, enforcement_payload


def diff_entry_to_dict(entry: Any) -> Dict[str, Any]:
    """
    Convert ``DiffEntry`` objects to serialisable dictionaries.
    """

    payload: Dict[str, Any] = {
        "path": entry.path,
        "status": entry.status,
    }
    detail = getattr(entry, "detail", None)
    if detail:
        payload["detail"] = detail
    return payload
