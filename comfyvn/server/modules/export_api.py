from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query

from comfyvn.config.runtime_paths import data_dir
from comfyvn.core.advisory_hooks import BundleContext
from comfyvn.core.advisory_hooks import scan as scan_bundle
from comfyvn.core.policy_gate import policy_gate

router = APIRouter()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _resolve_path(value: str, default: str) -> Path:
    path = Path(value) if value else Path(default)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


@lru_cache(maxsize=1)
def _renpy_project_root() -> Path:
    root = _resolve_path(os.getenv("COMFYVN_RENPY_PROJECT_DIR", ""), "renpy_project")
    game_dir = root / "game"
    game_dir.mkdir(parents=True, exist_ok=True)
    return root


@lru_cache(maxsize=1)
def _exports_root() -> Path:
    root = _resolve_path(os.getenv("COMFYVN_EXPORT_ROOT", ""), "exports")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _bundles_dir() -> Path:
    path = _exports_root() / "bundles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _renpy_exports_dir() -> Path:
    path = _exports_root() / "renpy"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# JSON utilities
# ---------------------------------------------------------------------------


def _read_json(path: Path, *, entity: str) -> dict:
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"{entity} not found: {path.as_posix()}"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail=f"{entity} invalid JSON: {path}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


# ---------------------------------------------------------------------------
# Timeline & scene resolution
# ---------------------------------------------------------------------------


def _candidate_timeline_paths(
    timeline_id: str, project_id: Optional[str]
) -> Iterable[Path]:
    seen: set[Path] = set()
    primary = data_dir("timelines") / f"{timeline_id}.json"
    if primary not in seen:
        seen.add(primary)
        yield primary

    projects_root = data_dir("projects")
    if project_id:
        candidate = projects_root / project_id / "timelines" / f"{timeline_id}.json"
        if candidate not in seen:
            seen.add(candidate)
            yield candidate
    else:
        if projects_root.exists():
            for entry in projects_root.iterdir():
                if entry.is_dir():
                    candidate = entry / "timelines" / f"{timeline_id}.json"
                    if candidate not in seen:
                        seen.add(candidate)
                        yield candidate


def _load_timeline(timeline_id: str, project_id: Optional[str]) -> tuple[dict, Path]:
    for candidate in _candidate_timeline_paths(timeline_id, project_id):
        if candidate.exists():
            return _read_json(candidate, entity="timeline"), candidate
    raise HTTPException(status_code=404, detail=f"timeline '{timeline_id}' not found")


def _candidate_scene_paths(scene_id: str, project_id: Optional[str]) -> Iterable[Path]:
    seen: set[Path] = set()
    if project_id:
        candidate = data_dir("projects", project_id, "scenes") / f"{scene_id}.json"
        if candidate not in seen:
            seen.add(candidate)
            yield candidate
    global_scene = data_dir("scenes") / f"{scene_id}.json"
    if global_scene not in seen:
        seen.add(global_scene)
        yield global_scene


def _load_scene(scene_id: str, project_id: Optional[str]) -> tuple[dict, Path]:
    for candidate in _candidate_scene_paths(scene_id, project_id):
        if candidate.exists():
            return _read_json(candidate, entity="scene"), candidate
    raise HTTPException(status_code=404, detail=f"scene '{scene_id}' not found")


def _load_project(project_id: str) -> tuple[dict, Path]:
    projects_root = data_dir("projects")
    manifest_path = projects_root / f"{project_id}.json"
    if manifest_path.exists():
        return _read_json(manifest_path, entity="project"), manifest_path
    project_dir = projects_root / project_id / "project.json"
    if project_dir.exists():
        return _read_json(project_dir, entity="project"), project_dir
    raise HTTPException(status_code=404, detail=f"project '{project_id}' not found")


def _require_gate(action: str) -> dict:
    gate = policy_gate.evaluate_action(action)
    if gate.get("requires_ack") and not gate.get("allow"):
        raise HTTPException(
            status_code=423,
            detail={
                "message": "operation blocked until legal acknowledgement is recorded",
                "gate": gate,
            },
        )
    return gate


# ---------------------------------------------------------------------------
# Ren'Py script generation helpers
# ---------------------------------------------------------------------------


def _safe_label(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip())
    if not slug:
        slug = "section"
    if not slug[0].isalpha():
        slug = f"section_{slug}"
    return slug.lower()


def _escape_text(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return escaped


def _iter_scene_dialogue(scene: dict) -> Iterable[dict]:
    if isinstance(scene.get("dialogue"), list):
        yield from (item for item in scene["dialogue"] if isinstance(item, (dict, str)))
        return
    if isinstance(scene.get("lines"), list):
        yield from (item for item in scene["lines"] if isinstance(item, (dict, str)))
        return
    # fallback: treat entire scene as narrator line using title
    yield {
        "type": "line",
        "speaker": None,
        "text": scene.get("title") or scene.get("id") or "",
    }


def _render_dialogue_block(scene: dict, *, indent: str = "    ") -> List[str]:
    lines: List[str] = []
    background = scene.get("background")
    if background:
        lines.append(f"{indent}scene {background}")
    music = scene.get("music")
    if music:
        lines.append(f'{indent}play music "{_escape_text(str(music))}"')

    for entry in _iter_scene_dialogue(scene):
        if isinstance(entry, str):
            text = _escape_text(entry)
            if text:
                lines.append(f'{indent}"{text}"')
            continue

        entry_type = entry.get("type", "line")
        if entry_type == "line":
            text = _escape_text(str(entry.get("text", "")))
            speaker = entry.get("speaker")
            if speaker:
                lines.append(f'{indent}"{_escape_text(str(speaker))}" "{text}"')
            else:
                lines.append(f'{indent}"{text}"')
            continue

        if entry_type == "choice":
            prompt = _escape_text(str(entry.get("prompt", "")))
            options = entry.get("options") or []
            lines.append(f"{indent}menu:")
            if prompt:
                lines.append(f'{indent*2}"{prompt}":')
            for option in options:
                label = _escape_text(str(option.get("text", "")))
                target = option.get("goto") or option.get("label")
                lines.append(f'{indent*2}"{label}":')
                if target:
                    lines.append(f"{indent*3}jump {_safe_label(str(target))}")
                else:
                    lines.append(f"{indent*3}pass")
            continue

        # Unhandled event: preserve as comment for manual follow-up
        summary = entry.get("text") or entry_type
        lines.append(f"{indent}# TODO: handle {entry_type}: {summary}")

    if not lines:
        lines.append(f'{indent}"..."')
    return lines


def _ensure_base_game_files(game_dir: Path) -> None:
    options_path = game_dir / "options.rpy"
    if not options_path.exists():
        options_path.write_text(
            "# Auto-generated options for ComfyVN exports\n"
            'define config.name = "ComfyVN Export"\n'
            'define config.version = "1.0"\n',
            encoding="utf-8",
        )

    screens_path = game_dir / "screens.rpy"
    if not screens_path.exists():
        screens_path.write_text(
            "# Minimal screens file generated by ComfyVN exports\n"
            "screen comfyvn_placeholder():\n"
            '    text "Exported via ComfyVN" align (0.5, 0.5)\n',
            encoding="utf-8",
        )

    readme_path = game_dir / "README.txt"
    if not readme_path.exists():
        readme_path.write_text(
            "ComfyVN auto-generated Ren'Py project.\n"
            "Files in this directory are safe to edit after export.\n",
            encoding="utf-8",
        )


def _scene_ids_from_timeline(timeline: dict, project_data: Optional[dict]) -> List[str]:
    order: List[str] = []
    seen: set[str] = set()

    def _append(scene_id: str) -> None:
        if scene_id and scene_id not in seen:
            seen.add(scene_id)
            order.append(scene_id)

    if isinstance(timeline.get("scene_order"), list):
        for item in timeline["scene_order"]:
            if isinstance(item, dict):
                _append(str(item.get("scene_id") or item.get("id") or ""))
            elif isinstance(item, str):
                _append(item)

    if not order and isinstance(timeline.get("scenes"), list):
        for item in timeline["scenes"]:
            _append(str(item))

    if not order and project_data and isinstance(project_data.get("scenes"), list):
        for item in project_data["scenes"]:
            _append(str(item))

    return order


def _build_renpy_project(
    *,
    timeline_id: str,
    timeline: dict,
    project_id: Optional[str],
    project_data: Optional[dict],
) -> dict:
    renpy_root = _renpy_project_root()
    game_dir = renpy_root / "game"
    script_path = game_dir / "script.rpy"

    scene_ids = _scene_ids_from_timeline(timeline, project_data)
    if not scene_ids:
        raise HTTPException(
            status_code=400, detail="timeline contains no scenes to export"
        )

    lines: List[str] = []
    timestamp = datetime.now(timezone.utc).isoformat()
    lines.append("# Auto-generated by ComfyVN export pipeline")
    lines.append(f"# timeline: {timeline_id}")
    if project_id:
        lines.append(f"# project: {project_id}")
    lines.append(f"# generated_at: {timestamp}")
    lines.append("")
    lines.append("label start:")
    for scene_id in scene_ids:
        label = _safe_label(scene_id)
        lines.append(f"    call {label}")
    lines.append("    return")
    lines.append("")

    scene_payloads: Dict[str, dict] = {}
    scene_sources: Dict[str, Path] = {}
    label_map: List[dict] = []
    for scene_id in scene_ids:
        scene, scene_path = _load_scene(scene_id, project_id)
        scene_payloads[scene_id] = scene
        scene_sources[scene_id] = scene_path
        label = _safe_label(scene_id)
        lines.append(f"label {label}:")
        lines.extend(_render_dialogue_block(scene))
        lines.append("    return")
        lines.append("")
        label_map.append(
            {
                "scene_id": scene_id,
                "label": label,
                "source": scene_path.as_posix(),
                "title": scene.get("title"),
            }
        )

    script_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    _ensure_base_game_files(game_dir)

    export_dir = _renpy_exports_dir()
    export_dir.mkdir(parents=True, exist_ok=True)
    snapshot = export_dir / f"{timeline_id}.json"
    snapshot.write_text(
        json.dumps(
            {
                "timeline_id": timeline_id,
                "project_id": project_id,
                "generated_at": timestamp,
                "script": script_path.as_posix(),
                "labels": label_map,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return {
        "script_path": script_path,
        "renpy_root": renpy_root,
        "labels": label_map,
        "scene_ids": scene_ids,
        "generated_at": timestamp,
        "scenes": scene_payloads,
        "scene_sources": scene_sources,
    }


# ---------------------------------------------------------------------------
# Bundle assembly helpers
# ---------------------------------------------------------------------------


def _load_character(
    character_id: str, project_id: Optional[str]
) -> tuple[Optional[dict], Optional[Path]]:
    candidates = []
    if project_id:
        candidates.append(
            data_dir("projects", project_id, "characters") / f"{character_id}.json"
        )
    candidates.append(data_dir("characters") / f"{character_id}.json")
    for path in candidates:
        if path.exists():
            return _read_json(path, entity="character"), path
    return None, None


def _collect_assets(asset_refs: Iterable[str]) -> List[Tuple[str, Path]]:
    assets: List[Tuple[str, Path]] = []
    for ref in asset_refs:
        rel = Path(ref)
        source = data_dir("assets") / rel
        if source.exists():
            assets.append((rel.as_posix(), source))
    return assets


def _bundle_readme(project_id: str, timeline_id: str, generated_at: str) -> str:
    lines = [
        "ComfyVN Studio Bundle",
        "======================",
        "",
        f"Project: {project_id}",
        f"Timeline: {timeline_id}",
        f"Generated: {generated_at}",
        "",
        "Contents:",
        "- manifest.json            Bundle manifest (scenes, assets, metadata)",
        "- provenance.json          Provenance payload + advisory findings",
        "- timelines/, scenes/, characters/ JSON exports",
        "- assets/                  Referenced project assets",
        "- renpy_project/           Generated Ren'Py script snapshot",
        "",
        "Review provenance.json before distribution and honour any license metadata in manifest.json.",
        "Exported via ComfyVN Studio.",
    ]
    return "\n".join(lines) + "\n"


def _ensure_timeline_payload(
    timeline_id: Optional[str],
    project_id: str,
    project_data: dict,
) -> tuple[dict, Path, str]:
    candidate_id = (
        timeline_id or project_data.get("timeline_id") or f"{project_id}_timeline"
    )
    try:
        payload, path = _load_timeline(candidate_id, project_id)
        return payload, path, candidate_id
    except HTTPException:
        scenes = project_data.get("scenes") or []
        payload = {
            "timeline_id": candidate_id,
            "title": project_data.get("title") or candidate_id,
            "scene_order": [{"scene_id": sid} for sid in scenes],
            "project_id": project_id,
            "generated": True,
        }
        path = data_dir("projects", project_id, "timelines")
        path.mkdir(parents=True, exist_ok=True)
        timeline_path = path / f"{candidate_id}.json"
        timeline_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return payload, timeline_path, candidate_id


def _build_bundle_archive(
    *,
    project_id: str,
    project_data: dict,
    timeline_id: str,
    timeline_data: dict,
    timeline_path: Path,
    renpy_info: dict,
    bundle_path: Optional[Path] = None,
) -> Tuple[Path, dict, List[Dict[str, Any]]]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if bundle_path is None:
        bundles_dir = _bundles_dir()
        bundle_path = bundles_dir / f"{project_id}_{timeline_id}_{ts}.zip"
    else:
        bundle_path = Path(bundle_path)
        if not bundle_path.suffix:
            bundle_path = bundle_path.with_suffix(".zip")
    bundle_path = bundle_path.expanduser()
    bundle_path.parent.mkdir(parents=True, exist_ok=True)

    scenes: Dict[str, dict] = dict(renpy_info.get("scenes") or {})
    scene_sources: Dict[str, Path] = {
        scene_id: path if isinstance(path, Path) else Path(path)
        for scene_id, path in (renpy_info.get("scene_sources") or {}).items()
    }

    characters: Dict[str, dict] = {}
    character_sources: Dict[str, Path] = {}
    for char_id in project_data.get("characters") or []:
        payload, path = _load_character(char_id, project_id)
        if payload and path:
            characters[char_id] = payload
            character_sources[char_id] = path

    assets = _collect_assets(project_data.get("assets") or [])

    manifest = {
        "id": project_id,
        "title": project_data.get("title") or project_id,
        "engine": "RenPy",
        "timeline_id": timeline_id,
        "generated_at": renpy_info["generated_at"],
        "scenes": list(scenes.keys()),
        "characters": list(characters.keys()),
        "assets": [entry[0] for entry in assets],
        "licenses": project_data.get("licenses") or [],
    }

    provenance = {
        "version": 1,
        "generated_at": renpy_info["generated_at"],
        "project": {
            "id": project_id,
            "title": project_data.get("title") or project_id,
            "source": project_data.get("source"),
        },
        "timeline": {
            "id": timeline_id,
            "source": timeline_path.as_posix(),
            "sha256": _sha256_file(timeline_path),
        },
        "scenes": {},
        "characters": {},
        "assets": [],
        "renpy_project": {
            "root": renpy_info["renpy_root"].as_posix(),
            "script": renpy_info["script_path"].as_posix(),
            "script_sha256": _sha256_file(renpy_info["script_path"]),
            "labels": renpy_info["labels"],
        },
    }

    for scene_id, scene_path in scene_sources.items():
        provenance["scenes"][scene_id] = {
            "source": scene_path.as_posix(),
            "sha256": _sha256_file(scene_path),
        }

    for char_id, char_path in character_sources.items():
        provenance["characters"][char_id] = {
            "source": char_path.as_posix(),
            "sha256": _sha256_file(char_path),
        }

    for rel, source in assets:
        provenance["assets"].append(
            {
                "path": rel,
                "source": source.as_posix(),
                "sha256": _sha256_file(source),
                "size": source.stat().st_size if source.exists() else 0,
            }
        )

    findings = scan_bundle(
        BundleContext(
            project_id=project_id,
            timeline_id=timeline_id,
            scenes=scenes,
            scene_sources=scene_sources,
            characters=characters,
            licenses=manifest["licenses"],
            assets=assets,
            metadata={"source": "export.bundle", "bundle_path": bundle_path.as_posix()},
        )
    )
    provenance["findings"] = findings

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False)
        )
        archive.writestr(
            "provenance.json", json.dumps(provenance, indent=2, ensure_ascii=False)
        )

        archive.writestr(
            f"timelines/{timeline_id}.json",
            json.dumps(timeline_data, indent=2, ensure_ascii=False),
        )

        for scene_id, payload in scenes.items():
            archive.writestr(
                f"scenes/{scene_id}.json",
                json.dumps(payload, indent=2, ensure_ascii=False),
            )

        for char_id, payload in characters.items():
            archive.writestr(
                f"characters/{char_id}.json",
                json.dumps(payload, indent=2, ensure_ascii=False),
            )

        for rel, source in assets:
            if source.exists():
                archive.write(source, f"assets/{rel}")

        # Embed Ren'Py project snapshot for convenience.
        renpy_root = renpy_info["renpy_root"]
        for file_path in renpy_root.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(renpy_root)
                archive.write(file_path, f"renpy_project/{rel.as_posix()}")
        archive.writestr(
            "README.txt",
            _bundle_readme(project_id, timeline_id, renpy_info["generated_at"]),
        )
        license_path = Path("LICENSE")
        if license_path.exists():
            archive.write(license_path, "LICENSE.txt")

    return bundle_path, provenance, findings


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@router.post("/api/export/renpy")
def export_renpy(
    timeline_id: str = Query(..., description="Timeline identifier to export"),
    project_id: Optional[str] = Query(
        None, description="Optional project context for scene lookups"
    ),
):
    gate = _require_gate("export.renpy")
    project_data: Optional[dict] = None
    if project_id:
        project_data, _ = _load_project(project_id)

    timeline, _ = (
        _load_timeline(timeline_id, project_id) if timeline_id else ({}, Path())
    )

    renpy_info = _build_renpy_project(
        timeline_id=timeline_id,
        timeline=timeline,
        project_id=project_id,
        project_data=project_data,
    )

    assets: List[Tuple[str, Path]] = []
    licenses: List[Any] = []
    if project_data:
        assets = _collect_assets(project_data.get("assets") or [])
        licenses = list(project_data.get("licenses") or [])

    scan_bundle(
        BundleContext(
            project_id=project_id,
            timeline_id=timeline_id,
            scenes=renpy_info.get("scenes") or {},
            scene_sources=renpy_info.get("scene_sources") or {},
            licenses=licenses,
            assets=assets,
            metadata={"source": "export.renpy"},
        )
    )

    return {
        "ok": True,
        "script": renpy_info["script_path"].as_posix(),
        "renpy_project": renpy_info["renpy_root"].as_posix(),
        "labels": renpy_info["labels"],
        "scene_ids": renpy_info["scene_ids"],
        "generated_at": renpy_info["generated_at"],
        "gate": gate,
    }


@router.post("/api/export/bundle")
def export_bundle(
    project_id: str = Query(..., description="Project identifier to bundle"),
    timeline_id: Optional[str] = Query(
        None, description="Optional timeline identifier to prioritise"
    ),
):
    gate = _require_gate("export.bundle")
    project_data, _ = _load_project(project_id)

    timeline_data, timeline_path, resolved_timeline_id = _ensure_timeline_payload(
        timeline_id,
        project_id,
        project_data,
    )

    renpy_info = _build_renpy_project(
        timeline_id=resolved_timeline_id,
        timeline=timeline_data,
        project_id=project_id,
        project_data=project_data,
    )

    bundle_path, provenance, findings = _build_bundle_archive(
        project_id=project_id,
        project_data=project_data,
        timeline_id=resolved_timeline_id,
        timeline_data=timeline_data,
        timeline_path=timeline_path,
        renpy_info=renpy_info,
    )

    return {
        "ok": True,
        "bundle": bundle_path.as_posix(),
        "provenance": provenance,
        "findings": findings,
        "generated_at": renpy_info["generated_at"],
        "gate": gate,
    }
