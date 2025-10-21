#!/usr/bin/env python3
"""CLI helper for exporting ComfyVN projects into a minimal Ren'Py layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import HTTPException

from comfyvn.assets_manifest import _categorize as categorize_asset
from comfyvn.assets_manifest import _load_sidecar as load_asset_sidecar
from comfyvn.config.runtime_paths import data_dir
from comfyvn.core.advisory_hooks import BundleContext
from comfyvn.core.advisory_hooks import scan as scan_bundle
from comfyvn.core.policy_gate import policy_gate
from comfyvn.server.modules import export_api

_IDENTIFIER_RE = re.compile(r"[^a-zA-Z0-9]+")
_IMAGE_EXTS = {".png", ".webp", ".jpg", ".jpeg"}


@dataclass
class BackgroundUsage:
    name: str
    relpath: str
    source: Path
    alias: str
    output_relpath: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PortraitUsage:
    reference: str
    relpath: str
    source: Path
    alias: str
    output_relpath: str
    character: Optional[str] = None
    expression: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a ComfyVN project to a Ren'Py-ready folder."
    )
    parser.add_argument(
        "--project", required=True, help="Project identifier to export."
    )
    parser.add_argument("--timeline", help="Optional timeline identifier override.")
    parser.add_argument(
        "--out",
        default="build/renpy_game",
        help="Output directory for Ren'Py game files (default: %(default)s).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files under the output directory if present.",
    )
    return parser.parse_args()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_output_dir(path: Path, *, force: bool) -> None:
    if path.exists():
        if not path.is_dir():
            raise RuntimeError(f"output path '{path}' exists and is not a directory")
        if force:
            shutil.rmtree(path)
        elif any(path.iterdir()):
            raise RuntimeError(
                f"output directory '{path}' is not empty (use --force to overwrite)"
            )
    path.mkdir(parents=True, exist_ok=True)


def _make_identifier(prefix: str, name: str, existing: Set[str]) -> str:
    slug = _IDENTIFIER_RE.sub("_", str(name).strip()).strip("_").lower()
    if not slug:
        slug = "asset"
    candidate = f"{prefix}_{slug}"
    if candidate not in existing:
        existing.add(candidate)
        return candidate
    counter = 2
    while True:
        alt = f"{candidate}_{counter}"
        if alt not in existing:
            existing.add(alt)
            return alt
        counter += 1


def _normalize_asset_ref(ref: str) -> Optional[str]:
    if not isinstance(ref, str):
        return None
    value = ref.strip().replace("\\", "/")
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return None
    while value.startswith("./"):
        value = value[2:]
    if value.startswith("assets/"):
        value = value[7:]
    if value.startswith("/"):
        value = value[1:]
    if not value:
        return None
    path = Path(value)
    if path.suffix.lower() in _IMAGE_EXTS:
        return path.as_posix()
    return None


def _collect_scene_assets(
    scene: dict,
) -> Tuple[Set[str], Dict[str, Set[str]], Set[str]]:
    backgrounds: Set[str] = set()
    portrait_exprs: Dict[str, Set[str]] = {}
    portrait_paths: Set[str] = set()

    def _add_background(value: Any) -> None:
        if isinstance(value, str):
            ref = value.strip()
            if ref:
                backgrounds.add(ref)

    def _add_portrait_path(value: Any) -> None:
        if isinstance(value, str):
            ref = value.strip()
            if ref:
                portrait_paths.add(ref)

    def _add_portrait_expr(speaker: Any, emotion: Any) -> None:
        if not speaker:
            return
        text = ""
        if isinstance(emotion, str):
            text = emotion.strip()
        if not text:
            text = "neutral"
        portrait_exprs.setdefault(str(speaker), set()).add(text)

    _add_background(scene.get("background"))
    meta = scene.get("meta") or {}
    _add_background(meta.get("background"))
    _add_portrait_path(meta.get("portrait"))

    lines = scene.get("dialogue") or scene.get("lines") or []
    for entry in lines:
        if not isinstance(entry, dict):
            continue
        _add_background(entry.get("background"))
        directives = entry.get("directives") or {}
        _add_background(directives.get("background"))
        block_meta = entry.get("meta") or {}
        _add_background(block_meta.get("background"))
        _add_portrait_path(entry.get("portrait") or entry.get("portrait_path") or entry.get("image"))
        _add_portrait_path(directives.get("portrait"))
        _add_portrait_path(block_meta.get("portrait"))
        _add_portrait_expr(entry.get("speaker"), entry.get("emotion") or entry.get("expression"))

    nodes = scene.get("nodes") or []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        _add_background(node.get("background"))
        directives = node.get("directives") or {}
        _add_background(directives.get("background"))
        block_meta = node.get("meta") or {}
        _add_background(block_meta.get("background"))
        content = node.get("content") or {}
        _add_background(content.get("background"))
        _add_portrait_path(content.get("portrait") or content.get("image"))
        _add_portrait_expr(content.get("speaker"), content.get("emotion") or content.get("expression"))

    return backgrounds, portrait_exprs, portrait_paths


def _normalise(value: str) -> str:
    return _IDENTIFIER_RE.sub("_", value.strip().lower())


def _resolve_asset_by_path(
    ref: str, assets_root: Path, available: Dict[str, Path]
) -> Optional[Tuple[str, Path]]:
    normalized = _normalize_asset_ref(ref)
    if not normalized:
        return None
    if normalized in available:
        return normalized, available[normalized]
    candidate = assets_root / normalized
    if candidate.exists():
        return normalized, candidate
    needle = Path(normalized).name.lower()
    for rel, path in available.items():
        if Path(rel).name.lower() == needle:
            return rel, path
    for path in assets_root.rglob(needle):
        if path.is_file():
            rel = path.relative_to(assets_root).as_posix()
            return rel, path
    return None


def _match_background_asset(
    name: str, available: Dict[str, Path], assets_root: Path
) -> Optional[Tuple[str, Path]]:
    direct = _resolve_asset_by_path(name, assets_root, available)
    if direct:
        return direct
    normalised = _normalise(name)
    for rel, path in available.items():
        info = categorize_asset(rel)
        candidate = info.get("bg_name") or Path(rel).stem
        if _normalise(str(candidate)) == normalised:
            return rel, path
    for path in assets_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _IMAGE_EXTS:
            continue
        rel = path.relative_to(assets_root).as_posix()
        info = categorize_asset(rel)
        candidate = info.get("bg_name") or Path(rel).stem
        if _normalise(str(candidate)) == normalised:
            return rel, path
    return None


def _match_portrait_asset(
    character: str,
    expression: str,
    available: Dict[str, Path],
    assets_root: Path,
) -> Optional[Tuple[str, Path]]:
    char_key = _normalise(character)
    expr_key = _normalise(expression or "neutral")

    def _check(rel: str) -> bool:
        info = categorize_asset(rel)
        if info.get("category") != "character":
            return False
        candidate_char = _normalise(str(info.get("character") or Path(rel).parts[-2]))
        if candidate_char != char_key:
            return False
        candidate_expr = _normalise(str(info.get("expression") or Path(rel).stem))
        if candidate_expr == expr_key:
            return True
        if expr_key != _normalise("neutral") and candidate_expr == _normalise("neutral"):
            return True
        return False

    for rel, path in available.items():
        if _check(rel):
            return rel, path

    for path in assets_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _IMAGE_EXTS:
            continue
        rel = path.relative_to(assets_root).as_posix()
        if _check(rel):
            return rel, path
    return None


def _rewrite_background_calls(
    lines: Sequence[str], aliases: Dict[str, str]
) -> List[str]:
    rewritten: List[str] = []
    for line in lines:
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith("scene "):
            original = stripped[6:].strip()
            alias = aliases.get(original)
            if not alias:
                normalized = _normalize_asset_ref(original)
                if normalized:
                    alias = aliases.get(normalized)
            rewritten.append(f"{indent}scene {alias or original}")
        else:
            rewritten.append(line)
    return rewritten


def _render_nodes(nodes: Sequence[Any], aliases: Dict[str, str]) -> List[str]:
    lines: List[str] = []
    indent = "    "
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = (node.get("type") or "").lower()
        content = node.get("content") or {}
        bg_ref = content.get("background") or node.get("background")
        if isinstance(bg_ref, str) and bg_ref.strip():
            alias = aliases.get(bg_ref.strip())
            if not alias:
                normalized = _normalize_asset_ref(bg_ref)
                if normalized:
                    alias = aliases.get(normalized)
            lines.append(f"{indent}scene {alias or bg_ref.strip()}")
        if node_type in {"text", "line"}:
            speaker = content.get("speaker")
            text = content.get("text") or ""
            if speaker:
                lines.append(f'{indent}"{speaker}" "{text}"')
            else:
                lines.append(f'{indent}"{text}"')
            continue
        if node_type == "choice":
            prompt = content.get("prompt")
            options = content.get("options") or []
            lines.append(f"{indent}menu:")
            if prompt:
                lines.append(f'{indent*2}"{prompt}":')
            for option in options:
                label = option.get("text") or "Continue"
                target = option.get("goto") or option.get("target")
                lines.append(f'{indent*2}"{label}":')
                if target:
                    lines.append(f"{indent*3}jump {export_api._safe_label(str(target))}")
                else:
                    lines.append(f"{indent*3}pass")
            continue
        summary = content.get("text") or node_type or "event"
        lines.append(f"{indent}# TODO: unsupported node '{node_type}': {summary}")
    if not lines:
        lines.append(f"{indent}\"...\"")
    return lines


def _render_scene_lines(scene: dict, aliases: Dict[str, str]) -> List[str]:
    if isinstance(scene.get("nodes"), list):
        return _render_nodes(scene["nodes"], aliases)
    block = export_api._render_dialogue_block(scene)
    return _rewrite_background_calls(block, aliases)


def _render_script(
    *,
    project_id: str,
    timeline_id: str,
    generated_at: str,
    backgrounds: Dict[str, BackgroundUsage],
    portraits: Dict[str, PortraitUsage],
    label_map: List[Dict[str, str]],
    scenes: Dict[str, dict],
    alias_lookup: Dict[str, str],
) -> str:
    lines: List[str] = []
    lines.append("# Auto-generated by ComfyVN Ren'Py exporter")
    lines.append(f"# project: {project_id}")
    lines.append(f"# timeline: {timeline_id}")
    lines.append(f"# generated_at: {generated_at}")
    lines.append("")

    if backgrounds:
        lines.append("# Background declarations")
        for usage in sorted(backgrounds.values(), key=lambda u: u.alias):
            lines.append(f'image {usage.alias} = "{usage.output_relpath}"')
        lines.append("")

    if portraits:
        lines.append("# Portrait declarations")
        for usage in sorted(portraits.values(), key=lambda u: u.alias):
            lines.append(f'image {usage.alias} = "{usage.output_relpath}"')
        lines.append("")

    lines.append("label start:")
    for entry in label_map:
        lines.append(f"    call {entry['label']}")
    lines.append("    return")
    lines.append("")

    for entry in label_map:
        scene_id = entry["scene_id"]
        label = entry["label"]
        scene = scenes[scene_id]
        lines.append(f"label {label}:")
        block = _render_scene_lines(scene, alias_lookup)
        if not block:
            lines.append('    "..."')
        else:
            lines.extend(block)
        lines.append("    return")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _asset_metadata(relpath: str, source: Path, assets_root: Path) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "sha256": _sha256_file(source),
        "size": source.stat().st_size,
    }
    sidecar = load_asset_sidecar(relpath, assets_root)
    if sidecar.get("seed") is not None:
        metadata["seed"] = sidecar["seed"]
    if sidecar.get("workflow_id") is not None:
        metadata["workflow_id"] = sidecar["workflow_id"]
    if sidecar.get("workflow_hash") is not None:
        metadata["workflow_hash"] = sidecar["workflow_hash"]
    if sidecar.get("extras"):
        metadata["extras"] = sidecar["extras"]
    return metadata


def main() -> int:
    args = _parse_args()

    gate = policy_gate.evaluate_action("export.renpy.cli")
    if gate.get("requires_ack") and not gate.get("allow"):
        print(
            "ERROR: Export blocked until legal acknowledgement is recorded (POST /api/policy/ack).",
            file=sys.stderr,
        )
        return 1

    try:
        project_data, project_path = export_api._load_project(args.project)
    except HTTPException as exc:
        print(f"ERROR: {exc.detail}", file=sys.stderr)
        return exc.status_code or 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"ERROR: failed to load project '{args.project}': {exc}", file=sys.stderr)
        return 1

    try:
        timeline_data, timeline_path, timeline_id = export_api._ensure_timeline_payload(
            args.timeline,
            args.project,
            project_data,
        )
    except HTTPException as exc:
        print(f"ERROR: {exc.detail}", file=sys.stderr)
        return exc.status_code or 1

    scene_ids = export_api._scene_ids_from_timeline(timeline_data, project_data)
    if not scene_ids:
        print("ERROR: timeline contains no scenes to export", file=sys.stderr)
        return 1

    scenes: Dict[str, dict] = {}
    scene_sources: Dict[str, Path] = {}
    background_refs: Set[str] = set()
    portrait_exprs: Dict[str, Set[str]] = {}
    portrait_paths: Set[str] = set()
    label_map: List[Dict[str, str]] = []

    for scene_id in scene_ids:
        scene, scene_path = export_api._load_scene(scene_id, args.project)
        scenes[scene_id] = scene
        scene_sources[scene_id] = scene_path
        label = export_api._safe_label(scene_id)
        label_map.append(
            {
                "scene_id": scene_id,
                "label": label,
                "source": scene_path.as_posix(),
                "title": scene.get("title"),
            }
        )
        bgs, portraits, paths = _collect_scene_assets(scene)
        background_refs.update(bgs)
        for character, expressions in portraits.items():
            portrait_exprs.setdefault(character, set()).update(expressions)
        portrait_paths.update(paths)

    output_dir = Path(args.out).expanduser().resolve()
    try:
        _ensure_output_dir(output_dir, force=args.force)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    game_dir = output_dir / "game"
    game_dir.mkdir(parents=True, exist_ok=True)

    assets_root = data_dir("assets")
    available_assets_list = export_api._collect_assets(project_data.get("assets") or [])
    available_assets = {rel: path for rel, path in available_assets_list}

    alias_pool: Set[str] = set()
    backgrounds: Dict[str, BackgroundUsage] = {}
    alias_lookup: Dict[str, str] = {}
    copied_asset_map: Dict[str, Path] = {}
    missing_backgrounds: Set[str] = set()

    for bg_ref in sorted(background_refs):
        match = _match_background_asset(bg_ref, available_assets, assets_root)
        if not match:
            missing_backgrounds.add(bg_ref)
            continue
        relpath, source = match
        alias = _make_identifier("bg", bg_ref, alias_pool)
        output_rel = Path("images") / relpath
        target = game_dir / output_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        metadata = _asset_metadata(relpath, source, assets_root)
        backgrounds[bg_ref] = BackgroundUsage(
            name=bg_ref,
            relpath=relpath,
            source=source,
            alias=alias,
            output_relpath=output_rel.as_posix(),
            metadata=metadata,
        )
        alias_lookup[bg_ref] = alias
        normalized = _normalize_asset_ref(bg_ref)
        if normalized:
            alias_lookup[normalized] = alias
        copied_asset_map[relpath] = source

    portraits: Dict[str, PortraitUsage] = {}
    missing_portraits: List[Dict[str, Optional[str]]] = []

    for character, expressions in sorted(portrait_exprs.items(), key=lambda item: item[0].lower()):
        for expression in sorted(expressions):
            match = _match_portrait_asset(character, expression, available_assets, assets_root)
            if not match:
                missing_portraits.append(
                    {"character": character, "expression": expression, "reference": None}
                )
                continue
            relpath, source = match
            if relpath in copied_asset_map:
                continue
            alias = _make_identifier("portrait", f"{character}_{expression}", alias_pool)
            output_rel = Path("images") / relpath
            target = game_dir / output_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            metadata = _asset_metadata(relpath, source, assets_root)
            usage = PortraitUsage(
                reference=f"{character}:{expression}",
                relpath=relpath,
                source=source,
                alias=alias,
                output_relpath=output_rel.as_posix(),
                character=character,
                expression=expression,
                metadata=metadata,
            )
            portraits[alias] = usage
            copied_asset_map[relpath] = source

    for ref in sorted(portrait_paths):
        match = _resolve_asset_by_path(ref, assets_root, available_assets)
        if not match:
            missing_portraits.append({"character": None, "expression": None, "reference": ref})
            continue
        relpath, source = match
        if relpath in copied_asset_map:
            continue
        info = categorize_asset(relpath)
        character = info.get("character") or Path(relpath).parent.name
        expression = info.get("expression") or Path(relpath).stem
        alias = _make_identifier("portrait", f"{character}_{expression}", alias_pool)
        output_rel = Path("images") / relpath
        target = game_dir / output_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        metadata = _asset_metadata(relpath, source, assets_root)
        usage = PortraitUsage(
            reference=ref,
            relpath=relpath,
            source=source,
            alias=alias,
            output_relpath=output_rel.as_posix(),
            character=character,
            expression=expression,
            metadata=metadata,
        )
        portraits[alias] = usage
        copied_asset_map[relpath] = source

    generated_at = datetime.now(timezone.utc).isoformat()
    script_path = game_dir / "script.rpy"
    script_text = _render_script(
        project_id=args.project,
        timeline_id=timeline_id,
        generated_at=generated_at,
        backgrounds=backgrounds,
        portraits=portraits,
        label_map=label_map,
        scenes=scenes,
        alias_lookup=alias_lookup,
    )
    script_path.write_text(script_text, encoding="utf-8")

    export_api._ensure_base_game_files(game_dir)

    manifest_path = output_dir / "export_manifest.json"
    manifest_payload: Dict[str, Any] = {
        "project": {
            "id": args.project,
            "title": project_data.get("title") or args.project,
            "source": project_path.as_posix(),
        },
        "timeline": {
            "id": timeline_id,
            "title": timeline_data.get("title") or timeline_id,
            "source": timeline_path.as_posix(),
        },
        "generated_at": generated_at,
        "output_dir": output_dir.as_posix(),
        "script": {
            "path": script_path.relative_to(output_dir).as_posix(),
            "labels": label_map,
        },
        "assets": {
            "backgrounds": [
                {
                    "name": usage.name,
                    "alias": usage.alias,
                    "source": usage.source.as_posix(),
                    "relpath": usage.relpath,
                    "output": usage.output_relpath,
                    **usage.metadata,
                }
                for usage in sorted(backgrounds.values(), key=lambda u: u.alias)
            ],
            "portraits": [
                {
                    "reference": usage.reference,
                    "alias": usage.alias,
                    "source": usage.source.as_posix(),
                    "relpath": usage.relpath,
                    "output": usage.output_relpath,
                    "character": usage.character,
                    "expression": usage.expression,
                    **usage.metadata,
                }
                for usage in sorted(portraits.values(), key=lambda u: u.alias)
            ],
        },
        "missing_assets": {
            "backgrounds": sorted(missing_backgrounds),
            "portraits": sorted(
                missing_portraits,
                key=lambda item: (
                    (item.get("character") or "").lower(),
                    (item.get("expression") or "").lower(),
                    str(item.get("reference") or ""),
                ),
            ),
        },
        "gate": gate,
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    scan_bundle(
        BundleContext(
            project_id=args.project,
            timeline_id=timeline_id,
            scenes=scenes,
            scene_sources=scene_sources,
            licenses=project_data.get("licenses") or [],
            assets=list(copied_asset_map.items()),
            metadata={
                "source": "export.renpy.cli",
                "project_path": project_path.as_posix(),
                "timeline_path": timeline_path.as_posix(),
                "output_dir": output_dir.as_posix(),
                "script_path": script_path.as_posix(),
                "manifest_path": manifest_path.as_posix(),
            },
        )
    )

    summary: Dict[str, Any] = {
        "ok": True,
        "project": args.project,
        "timeline": timeline_id,
        "output_dir": output_dir.as_posix(),
        "script": script_path.as_posix(),
        "backgrounds_copied": len(backgrounds),
        "portraits_copied": len(portraits),
        "manifest": manifest_path.as_posix(),
        "missing_assets": manifest_payload["missing_assets"],
        "gate": gate,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
