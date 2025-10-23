"""
High-level Ren'Py export orchestrator used by both CLI and HTTP routes.

The orchestrator wraps the existing export helpers with extra features:
per-scene `.rpy` generation, asset staging, dry-run diff summaries, and a
deterministic publish preset that can optionally invoke the Ren'Py SDK CLI.
"""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from fastapi import HTTPException

from comfyvn.assets_manifest import _categorize as categorize_asset
from comfyvn.assets_manifest import _load_sidecar as load_asset_sidecar
from comfyvn.config import feature_flags
from comfyvn.config.runtime_paths import data_dir
from comfyvn.core.advisory_hooks import BundleContext
from comfyvn.core.advisory_hooks import scan as scan_bundle
from comfyvn.core.content_filter import content_filter
from comfyvn.core.policy_gate import policy_gate
from comfyvn.rating import rating_service
from comfyvn.server.modules import export_api

_IDENTIFIER_RE = re.compile(r"[^a-zA-Z0-9]+")
_IMAGE_EXTS = {".png", ".webp", ".jpg", ".jpeg"}
_ZIP_EPOCH = (2025, 1, 1, 0, 0, 0)

LOGGER = logging.getLogger(__name__)


@dataclass
class BackgroundUsage:
    name: str
    relpath: str
    source: Path
    alias: str
    output_relpath: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def target_path(self, game_dir: Path) -> Path:
        return game_dir / self.output_relpath


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

    def target_path(self, game_dir: Path) -> Path:
        return game_dir / self.output_relpath


@dataclass
class POVRoute:
    pov: str
    name: str
    slug: str
    entry_label: str
    labels: List[str]
    scenes: List[str]


@dataclass
class POVFork:
    pov: str
    name: str
    slug: str
    output_dir: Path
    game_dir: Path
    script_path: Path
    manifest_path: Path
    manifest_payload: Dict[str, Any]


@dataclass
class ForkArchive:
    pov: str
    name: str
    slug: str
    archive_path: Path
    manifest_path: Path
    checksum: str


@dataclass
class ExportOptions:
    project_id: str
    timeline_id: Optional[str] = None
    world_id: Optional[str] = None
    world_mode: str = "auto"
    output_dir: Path = Path("build/renpy_game")
    force: bool = False
    dry_run: bool = False
    policy_action: Optional[str] = "export.renpy"
    per_scene: bool = True
    pov_mode: str = "auto"
    pov_switch_menu: bool = True
    rating_acknowledged: bool = False
    rating_ack_token: Optional[str] = None


@dataclass
class PublishOptions:
    destination: Path
    label: Optional[str] = None
    platforms: Sequence[str] = ("windows", "linux", "mac")
    renpy_sdk: Optional[Path] = None
    call_sdk: bool = False
    renpy_cli_flags: Sequence[str] = ()


@dataclass
class DiffEntry:
    path: str
    status: str
    detail: Optional[str] = None


@dataclass
class ExportResult:
    ok: bool
    project_id: str
    timeline_id: str
    gate: Dict[str, Any]
    rating_gate: Dict[str, Any]
    output_dir: Path
    generated_at: str
    script_path: Path
    scene_files: Dict[str, Path]
    label_map: List[Dict[str, Any]]
    backgrounds: Dict[str, BackgroundUsage]
    portraits: Dict[str, PortraitUsage]
    manifest_path: Path
    manifest_payload: Dict[str, Any]
    missing_backgrounds: Set[str]
    missing_portraits: List[Dict[str, Optional[str]]]
    pov_mode: str = "disabled"
    pov_menu_enabled: bool = False
    pov_default: Optional[str] = None
    pov_routes: List[POVRoute] = field(default_factory=list)
    pov_forks: Dict[str, POVFork] = field(default_factory=dict)
    world_selection: Dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False
    diffs: List[DiffEntry] = field(default_factory=list)


@dataclass
class PublishResult:
    ok: bool
    archive_path: Path
    manifest_path: Path
    checksum: str
    platforms: Sequence[str]
    sdk_invoked: bool = False
    sdk_exit_code: Optional[int] = None
    sdk_stdout: Optional[str] = None
    sdk_stderr: Optional[str] = None
    fork_archives: List[ForkArchive] = field(default_factory=list)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


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
        _add_portrait_path(
            entry.get("portrait") or entry.get("portrait_path") or entry.get("image")
        )
        _add_portrait_path(directives.get("portrait"))
        _add_portrait_path(block_meta.get("portrait"))
        _add_portrait_expr(
            entry.get("speaker"),
            entry.get("emotion") or entry.get("expression"),
        )

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
        _add_portrait_expr(
            content.get("speaker"),
            content.get("emotion") or content.get("expression"),
        )

    return backgrounds, portrait_exprs, portrait_paths


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


def _normalise_timeline_entry(raw: Any, index: int) -> Optional[Dict[str, Any]]:
    entry: Dict[str, Any] = {
        "index": index,
        "pov_values": [],
        "pov_names": {},
    }

    def _register(pov_value: Any, display: Any) -> None:
        if not pov_value:
            return
        key = str(pov_value).strip()
        if not key:
            return
        if key not in entry["pov_values"]:
            entry["pov_values"].append(key)
        if isinstance(display, str):
            label = display.strip()
            if label and key not in entry["pov_names"]:
                entry["pov_names"][key] = label

    def _collect(source: Any) -> None:
        if not source:
            return
        if isinstance(source, str):
            _register(source, None)
            return
        if isinstance(source, Mapping):
            _register(
                source.get("id") or source.get("pov") or source.get("value"),
                source.get("name") or source.get("label") or source.get("title"),
            )
            return
        if isinstance(source, Iterable):
            for item in source:
                _collect(item)

    if isinstance(raw, str):
        scene_id = raw.strip()
        if not scene_id:
            return None
        entry["scene_id"] = scene_id
        return entry

    if isinstance(raw, Mapping):
        scene_id = (
            raw.get("scene_id")
            or raw.get("id")
            or raw.get("scene")
            or raw.get("sceneId")
        )
        if not scene_id:
            return None
        entry["scene_id"] = str(scene_id).strip()
        entry["title"] = raw.get("title") or raw.get("name")
        entry["raw"] = raw
        _register(
            raw.get("pov") or raw.get("perspective"),
            raw.get("pov_name")
            or raw.get("perspective_name")
            or raw.get("label")
            or raw.get("title"),
        )
        _collect(raw.get("povs") or raw.get("perspectives"))
        return entry

    return None


def _timeline_scene_entries(
    timeline: Mapping[str, Any], project_data: Optional[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    scene_order = timeline.get("scene_order")
    if isinstance(scene_order, Iterable) and not isinstance(scene_order, (str, bytes)):
        for index, raw in enumerate(scene_order):
            entry = _normalise_timeline_entry(raw, index)
            if entry:
                entries.append(entry)

    if not entries:
        scenes_field = timeline.get("scenes")
        if isinstance(scenes_field, Iterable) and not isinstance(
            scenes_field, (str, bytes)
        ):
            for index, raw in enumerate(scenes_field):
                entry = _normalise_timeline_entry(raw, index)
                if entry:
                    entries.append(entry)
                elif isinstance(raw, str):
                    scene_id = raw.strip()
                if scene_id:
                    entries.append(
                        {
                            "scene_id": scene_id,
                            "index": index,
                            "pov_values": [],
                            "pov_names": {},
                        }
                    )

    if not entries:
        fallback = export_api._scene_ids_from_timeline(timeline, project_data)
        for index, scene_id in enumerate(fallback):
            entries.append(
                {
                    "scene_id": scene_id,
                    "index": index,
                    "pov_values": [],
                    "pov_names": {},
                }
            )

    return entries


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
        if expr_key != _normalise("neutral") and candidate_expr == _normalise(
            "neutral"
        ):
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
                    lines.append(
                        f"{indent*3}jump {export_api._safe_label(str(target))}"
                    )
                else:
                    lines.append(f"{indent*3}pass")
            continue
        summary = content.get("text") or node_type or "event"
        lines.append(f"{indent}# TODO: unsupported node '{node_type}': {summary}")
    if not lines:
        lines.append(f'{indent}"..."')
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
    label_map: List[Dict[str, Any]],
    scenes: Dict[str, dict],
    alias_lookup: Dict[str, str],
    pov_routes: Sequence[POVRoute] = (),
    include_switch_menu: bool = False,
    active_branch: Optional[POVRoute] = None,
) -> str:
    lines: List[str] = []
    lines.append("# Auto-generated by ComfyVN Ren'Py exporter")
    lines.append(f"# project: {project_id}")
    lines.append(f"# timeline: {timeline_id}")
    lines.append(f"# generated_at: {generated_at}")
    lines.append("")

    routes = list(pov_routes)
    if routes and active_branch is None:
        lines.append("# POV routes detected:")
        for route in routes:
            lines.append(f"#  - {route.pov}: {route.name} ({len(route.labels)} scenes)")
        lines.append("")

    if active_branch is not None:
        lines.append(
            f"# Active POV branch: {active_branch.pov} :: {active_branch.name}"
        )
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

    default_route = active_branch or (routes[0] if routes else None)
    multi_route = len(routes) >= 2

    if active_branch is not None:
        lines.append("label start:")
        if not active_branch.labels:
            lines.append('    "..."')
        else:
            for label in active_branch.labels:
                lines.append(f"    call {label}")
        lines.append("    return")
        lines.append("")
    elif multi_route and include_switch_menu:
        lines.append("label start:")
        lines.append("    call comfyvn_pov_menu")
        lines.append("    return")
        lines.append("")
        lines.append("label comfyvn_pov_menu:")
        lines.append("    menu:")
        lines.append('        "Select POV branch":')
        for route in routes:
            lines.append(f'            "{route.name}":')
            lines.append(f"                call {route.entry_label}")
        lines.append('            "Exit POV menu":')
        lines.append("                return")
        lines.append("    jump comfyvn_pov_menu")
        lines.append("")
        for route in routes:
            lines.append(f"label {route.entry_label}:")
            if not route.labels:
                lines.append('    "..."')
            else:
                for label in route.labels:
                    lines.append(f"    call {label}")
            lines.append("    return")
            lines.append("")
    elif default_route is not None:
        lines.append("label start:")
        if not default_route.labels:
            lines.append('    "..."')
        else:
            for label in default_route.labels:
                lines.append(f"    call {label}")
        lines.append("    return")
        lines.append("")
        if multi_route:
            for route in routes:
                lines.append(f"label {route.entry_label}:")
                if not route.labels:
                    lines.append('    "..."')
                else:
                    for label in route.labels:
                        lines.append(f"    call {label}")
                lines.append("    return")
                lines.append("")
    else:
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


def _render_scene_module(
    *,
    scene_id: str,
    label: str,
    scene: dict,
    alias_lookup: Dict[str, str],
    povs: Sequence[str] = (),
) -> str:
    title = scene.get("title") or scene_id
    lines = [f"# Scene: {title}", f"# Label: {label}"]
    if povs:
        joined = ", ".join(sorted(povs))
        lines.append(f"# POV: {joined}")
    lines.append("")
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


def _ensure_output_dir(path: Path, *, force: bool) -> None:
    if path.exists():
        if not path.is_dir():
            raise HTTPException(
                status_code=400, detail=f"output path '{path}' is not a directory"
            )
        if force:
            shutil.rmtree(path)
        elif any(path.iterdir()):
            raise HTTPException(
                status_code=400,
                detail=f"output directory '{path}' is not empty (use --force to overwrite)",
            )
    path.mkdir(parents=True, exist_ok=True)


def _diff_text(path: Path, new_text: str) -> DiffEntry:
    if not path.exists():
        return DiffEntry(path=path.as_posix(), status="new", detail=new_text)
    old_text = path.read_text(encoding="utf-8")
    if old_text == new_text:
        return DiffEntry(path=path.as_posix(), status="unchanged")
    diff_lines = list(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=path.as_posix(),
            tofile=f"{path.as_posix()} (planned)",
            lineterm="",
            n=3,
        )
    )
    snippet = "\n".join(diff_lines[:200])
    return DiffEntry(path=path.as_posix(), status="modified", detail=snippet)


def _diff_binary(path: Path, source: Path) -> DiffEntry:
    if not path.exists():
        return DiffEntry(path=path.as_posix(), status="new")
    try:
        target_hash = _sha256_file(path)
    except OSError:
        target_hash = ""
    source_hash = _sha256_file(source)
    if target_hash == source_hash:
        return DiffEntry(path=path.as_posix(), status="unchanged")
    return DiffEntry(path=path.as_posix(), status="modified")


def _zip_write_bytes(zf: ZipFile, arcname: str, payload: bytes) -> None:
    info = ZipInfo(arcname)
    info.date_time = _ZIP_EPOCH
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, payload)


def _zip_write_file(zf: ZipFile, arcname: str, source: Path) -> None:
    info = ZipInfo(arcname)
    info.date_time = _ZIP_EPOCH
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    with source.open("rb") as handle:
        data = handle.read()
    zf.writestr(info, data)


class RenPyOrchestrator:
    """Coordinates Ren'Py exports across CLI and server entrypoints."""

    def _resolve_world_selection(self, options: ExportOptions) -> Dict[str, Any]:
        try:
            from comfyvn.pov import (
                WORLDLINES,  # type: ignore import not required at build time
            )
        except Exception:
            return {"mode": "none", "active": None, "worlds": []}

        registry = WORLDLINES
        worlds = registry.list_payloads()
        if not worlds:
            return {"mode": "none", "active": None, "worlds": []}

        requested_id = (options.world_id or "").strip()
        mode = (options.world_mode or "auto").strip().lower()

        active_snapshot = registry.active_snapshot()
        active_id = active_snapshot.get("id") if active_snapshot else None

        if requested_id:
            try:
                registry.ensure(requested_id)
            except KeyError as exc:
                raise HTTPException(
                    status_code=404, detail=f"world '{requested_id}' not found"
                ) from exc
            active_id = requested_id

        if mode not in {"auto", "single", "multi"}:
            raise HTTPException(
                status_code=400, detail=f"unsupported world mode '{mode}'"
            )

        if active_id is None:
            active_id = worlds[0]["id"]

        resolved_mode = mode
        if mode == "auto":
            if requested_id:
                resolved_mode = "single"
            elif len(worlds) > 1:
                resolved_mode = "multi"
            else:
                resolved_mode = "single"

        if resolved_mode == "single":
            world = registry.ensure(active_id)
            snapshot = world.snapshot()
            snapshot["active"] = True
            return {
                "mode": "single",
                "active": active_id,
                "worlds": [snapshot],
            }

        items: List[Dict[str, Any]] = []
        for world in registry.list():
            snapshot = world.snapshot()
            snapshot["active"] = world.id == active_id
            items.append(snapshot)
        return {
            "mode": "multi",
            "active": active_id,
            "worlds": items,
        }

    def export(self, options: ExportOptions) -> ExportResult:
        if not options.project_id:
            raise HTTPException(status_code=400, detail="project id is required")

        gate: Dict[str, Any] = {}
        rating_gate: Dict[str, Any] = {}
        if options.policy_action:
            gate = policy_gate.evaluate_action(options.policy_action)
            if gate.get("requires_ack"):
                LOGGER.warning(
                    "Advisory disclaimer not yet acknowledged for action=%s",
                    options.policy_action,
                )

        try:
            project_data, project_path = export_api._load_project(options.project_id)
        except HTTPException:
            raise

        if feature_flags.is_enabled("enable_rating_api"):
            try:
                rating_gate = rating_service().evaluate(
                    f"export:{options.project_id}",
                    {
                        "title": project_data.get("title"),
                        "summary": project_data.get("summary"),
                        "meta": project_data.get("meta") or {},
                        "tags": project_data.get("tags")
                        or project_data.get("categories"),
                    },
                    mode=content_filter.mode(),
                    acknowledged=options.rating_acknowledged,
                    action=options.policy_action or "export.renpy",
                    ack_token=options.rating_ack_token,
                )
            except Exception:
                LOGGER.warning(
                    "Rating evaluation failed for project %s",
                    options.project_id,
                    exc_info=True,
                )
                rating_gate = {
                    "ok": False,
                    "error": "rating evaluation failed",
                    "allowed": True,
                }
        else:
            rating_gate = {"ok": False, "allowed": True, "feature": "enable_rating_api"}
        if rating_gate and not rating_gate.get("allowed", True):
            LOGGER.warning(
                "Rating gate blocked export project=%s rating=%s ack=%s",
                options.project_id,
                (rating_gate.get("rating") or {}).get("rating"),
                rating_gate.get("ack_status"),
            )
            raise HTTPException(
                status_code=423,
                detail={
                    "message": "rating gate blocked export",
                    "gate": rating_gate,
                },
            )

        timeline_payload = export_api._ensure_timeline_payload(
            options.timeline_id,
            options.project_id,
            project_data,
        )
        timeline_data, timeline_path, resolved_timeline = timeline_payload

        timeline_entries = _timeline_scene_entries(timeline_data, project_data)
        if not timeline_entries:
            raise HTTPException(
                status_code=400, detail="timeline contains no scenes to export"
            )

        world_selection = self._resolve_world_selection(options)

        scenes: Dict[str, dict] = {}
        scene_sources: Dict[str, Path] = {}
        scene_labels: Dict[str, Dict[str, Any]] = {}
        scene_pov_map: Dict[str, Dict[str, str]] = {}
        background_refs: Set[str] = set()
        portrait_exprs: Dict[str, Set[str]] = {}
        portrait_paths: Set[str] = set()
        label_map: List[Dict[str, Any]] = []
        pov_catalog: Dict[str, Dict[str, str]] = {}
        pov_order: List[str] = []

        def _register_pov_value(pov_id: Optional[str], display: Optional[str]) -> None:
            if not pov_id:
                return
            key = str(pov_id).strip()
            if not key:
                return
            label = (
                display.strip()
                if isinstance(display, str) and display.strip()
                else None
            )
            entry = pov_catalog.setdefault(key, {"id": key, "name": label or key})
            if label and entry["name"] in {entry["id"], ""}:
                entry["name"] = label
            if key not in pov_order:
                pov_order.append(key)

        seen_scene_ids: Set[str] = set()
        unique_scene_ids: List[str] = []
        for placement in timeline_entries:
            scene_id = placement.get("scene_id")
            if not scene_id:
                continue
            if scene_id not in seen_scene_ids:
                seen_scene_ids.add(scene_id)
                unique_scene_ids.append(scene_id)

        for scene_id in unique_scene_ids:
            scene, scene_path = export_api._load_scene(scene_id, options.project_id)
            scenes[scene_id] = scene
            scene_sources[scene_id] = scene_path
            label = export_api._safe_label(scene_id)
            entry: Dict[str, Any] = {
                "scene_id": scene_id,
                "label": label,
                "source": scene_path.as_posix(),
                "title": scene.get("title"),
                "pov_ids": [],
                "povs": [],
            }
            label_map.append(entry)
            scene_labels[scene_id] = entry
            scene_povs = _collect_scene_povs(scene)
            for pov_id, name in scene_povs.items():
                _register_pov_value(pov_id, name)
            scene_pov_map[scene_id] = scene_povs
            bgs, portraits, paths = _collect_scene_assets(scene)
            background_refs.update(bgs)
            for character, expressions in portraits.items():
                portrait_exprs.setdefault(character, set()).update(expressions)
            portrait_paths.update(paths)

        sequence_entries: List[Dict[str, Any]] = []
        sequence_pov_ids: Set[str] = set()
        for placement in timeline_entries:
            scene_id = placement.get("scene_id")
            if not scene_id or scene_id not in scene_labels:
                continue
            label_info = scene_labels[scene_id]
            placement_povs = list(placement.get("pov_values") or [])
            placement_names: Dict[str, str] = dict(placement.get("pov_names") or {})
            scene_povs = scene_pov_map.get(scene_id, {})
            if not placement_povs:
                placement_povs = list(scene_povs.keys())
            else:
                for pov_id in placement_povs:
                    if pov_id not in placement_names and pov_id in scene_povs:
                        placement_names[pov_id] = scene_povs[pov_id]
            for pov_id in placement_povs:
                sequence_pov_ids.add(pov_id)
                _register_pov_value(
                    pov_id, placement_names.get(pov_id) or scene_povs.get(pov_id)
                )
                if pov_id not in scene_povs:
                    scene_povs[pov_id] = (
                        placement_names.get(pov_id) or pov_catalog[pov_id]["name"]
                    )
            sequence_entries.append(
                {
                    "scene_id": scene_id,
                    "label": label_info["label"],
                    "povs": list(placement_povs),
                    "pov_names": placement_names,
                }
            )

        for scene_id, entry in scene_labels.items():
            scene_povs = scene_pov_map.get(scene_id, {})
            pov_ids = list(scene_povs.keys())
            entry["pov_ids"] = pov_ids
            entry["povs"] = [
                {"id": pov_id, "name": scene_povs[pov_id]} for pov_id in pov_ids
            ]

        existing_labels: Set[str] = {item["label"] for item in label_map}
        slug_pool: Set[str] = set()
        pov_routes: List[POVRoute] = []
        for pov_id in pov_order:
            if pov_id not in sequence_pov_ids:
                continue
            labels_seq: List[str] = []
            scenes_seq: List[str] = []
            for placement in sequence_entries:
                entry_povs = placement.get("povs") or []
                if entry_povs:
                    if pov_id in entry_povs:
                        labels_seq.append(placement["label"])
                        scenes_seq.append(placement["scene_id"])
                else:
                    labels_seq.append(placement["label"])
                    scenes_seq.append(placement["scene_id"])
            if not labels_seq:
                continue
            slug_base = export_api._safe_label(pov_id)
            slug = slug_base
            suffix = 2
            while slug in slug_pool:
                slug = f"{slug_base}_{suffix}"
                suffix += 1
            slug_pool.add(slug)
            entry_label_base = export_api._safe_label(f"comfyvn_pov_{pov_id}")
            entry_label = entry_label_base
            counter = 2
            while entry_label in existing_labels:
                entry_label = f"{entry_label_base}_{counter}"
                counter += 1
            existing_labels.add(entry_label)
            route_name = pov_catalog.get(pov_id, {}).get("name") or pov_id
            pov_routes.append(
                POVRoute(
                    pov=pov_id,
                    name=route_name,
                    slug=slug,
                    entry_label=entry_label,
                    labels=labels_seq,
                    scenes=scenes_seq,
                )
            )

        routes_present = bool(pov_routes)
        multi_route = len(pov_routes) >= 2
        requested_mode = (options.pov_mode or "auto").strip().lower()
        include_switch_menu = options.pov_switch_menu if multi_route else False
        create_forks = False
        effective_mode = "disabled"

        if routes_present:
            if multi_route:
                if requested_mode == "disabled":
                    include_switch_menu = False
                    create_forks = False
                    effective_mode = "disabled"
                elif requested_mode == "master":
                    include_switch_menu = options.pov_switch_menu
                    create_forks = False
                    effective_mode = "master"
                elif requested_mode == "forks":
                    include_switch_menu = False
                    create_forks = True
                    effective_mode = "forks"
                elif requested_mode == "both":
                    include_switch_menu = options.pov_switch_menu
                    create_forks = True
                    effective_mode = "both" if include_switch_menu else "forks"
                else:
                    include_switch_menu = options.pov_switch_menu
                    create_forks = True
                    effective_mode = "both" if include_switch_menu else "forks"
            else:
                include_switch_menu = False
                create_forks = False
                effective_mode = "single"
        else:
            include_switch_menu = False
            create_forks = False
            effective_mode = "disabled"

        if not multi_route:
            create_forks = False
            include_switch_menu = False

        output_dir = options.output_dir.expanduser().resolve()
        game_dir = output_dir / "game"

        if not options.dry_run:
            _ensure_output_dir(output_dir, force=options.force)
            game_dir.mkdir(parents=True, exist_ok=True)

        assets_root = data_dir("assets")
        available_assets_list = export_api._collect_assets(
            project_data.get("assets") or []
        )
        available_assets = {rel: path for rel, path in available_assets_list}

        alias_pool: Set[str] = set()
        backgrounds: Dict[str, BackgroundUsage] = {}
        alias_lookup: Dict[str, str] = {}
        copied_asset_map: Dict[str, Path] = {}
        missing_backgrounds: Set[str] = set()
        diffs: List[DiffEntry] = []

        for bg_ref in sorted(background_refs):
            match = _match_background_asset(bg_ref, available_assets, assets_root)
            if not match:
                missing_backgrounds.add(bg_ref)
                continue
            relpath, source = match
            alias = _make_identifier("bg", bg_ref, alias_pool)
            output_rel = Path("images") / relpath
            target = game_dir / output_rel
            metadata = _asset_metadata(relpath, source, assets_root)
            usage = BackgroundUsage(
                name=bg_ref,
                relpath=relpath,
                source=source,
                alias=alias,
                output_relpath=output_rel.as_posix(),
                metadata=metadata,
            )
            backgrounds[bg_ref] = usage
            alias_lookup[bg_ref] = alias
            normalized = _normalize_asset_ref(bg_ref)
            if normalized:
                alias_lookup[normalized] = alias
            if options.dry_run:
                diffs.append(_diff_binary(target, source))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            copied_asset_map[relpath] = source

        portraits: Dict[str, PortraitUsage] = {}
        missing_portraits: List[Dict[str, Optional[str]]] = []

        for character, expressions in sorted(
            portrait_exprs.items(), key=lambda item: item[0].lower()
        ):
            for expression in sorted(expressions):
                match = _match_portrait_asset(
                    character, expression, available_assets, assets_root
                )
                if not match:
                    missing_portraits.append(
                        {
                            "character": character,
                            "expression": expression,
                            "reference": None,
                        }
                    )
                    continue
                relpath, source = match
                if relpath in copied_asset_map:
                    continue
                alias = _make_identifier(
                    "portrait", f"{character}_{expression}", alias_pool
                )
                output_rel = Path("images") / relpath
                target = game_dir / output_rel
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
                if options.dry_run:
                    diffs.append(_diff_binary(target, source))
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                copied_asset_map[relpath] = source

        for ref in sorted(portrait_paths):
            match = _resolve_asset_by_path(ref, assets_root, available_assets)
            if not match:
                missing_portraits.append(
                    {"character": None, "expression": None, "reference": ref}
                )
                continue
            relpath, source = match
            if relpath in copied_asset_map:
                continue
            info = categorize_asset(relpath)
            character = info.get("character") or Path(relpath).parent.name
            expression = info.get("expression") or Path(relpath).stem
            alias = _make_identifier(
                "portrait", f"{character}_{expression}", alias_pool
            )
            output_rel = Path("images") / relpath
            target = game_dir / output_rel
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
            if options.dry_run:
                diffs.append(_diff_binary(target, source))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            copied_asset_map[relpath] = source

        generated_at = datetime.now(timezone.utc).isoformat()
        script_text = _render_script(
            project_id=options.project_id,
            timeline_id=resolved_timeline,
            generated_at=generated_at,
            backgrounds=backgrounds,
            portraits=portraits,
            label_map=label_map,
            scenes=scenes,
            alias_lookup=alias_lookup,
            pov_routes=pov_routes,
            include_switch_menu=include_switch_menu,
        )
        script_path = game_dir / "script.rpy"
        if options.dry_run:
            diffs.append(_diff_text(script_path, script_text))
        else:
            script_path.write_text(script_text, encoding="utf-8")

        scene_files: Dict[str, Path] = {}
        if options.per_scene:
            scenes_dir = game_dir / "scenes"
            if not options.dry_run:
                scenes_dir.mkdir(parents=True, exist_ok=True)
            for entry in label_map:
                scene_id = entry["scene_id"]
                label = entry["label"]
                scene = scenes[scene_id]
                scene_text = _render_scene_module(
                    scene_id=scene_id,
                    label=label,
                    scene=scene,
                    alias_lookup=alias_lookup,
                    povs=entry.get("pov_ids", []),
                )
                scene_path = scenes_dir / f"{label}.rpy"
                scene_files[scene_id] = scene_path
                if options.dry_run:
                    diffs.append(_diff_text(scene_path, scene_text))
                else:
                    scene_path.write_text(scene_text, encoding="utf-8")

        if not options.dry_run:
            export_api._ensure_base_game_files(game_dir)

        manifest_pov_routes = [
            {
                "id": route.pov,
                "name": route.name,
                "slug": route.slug,
                "entry_label": route.entry_label,
                "scene_labels": route.labels,
                "scenes": route.scenes,
            }
            for route in pov_routes
        ]
        manifest_pov_section: Dict[str, Any] = {
            "mode": effective_mode,
            "menu_enabled": include_switch_menu,
            "active": None,
            "default": pov_routes[0].pov if pov_routes else None,
            "routes": manifest_pov_routes,
            "forks": [],
        }

        manifest_payload: Dict[str, Any] = {
            "project": {
                "id": options.project_id,
                "title": project_data.get("title") or options.project_id,
                "source": project_path.as_posix(),
            },
            "timeline": {
                "id": resolved_timeline,
                "title": timeline_data.get("title") or resolved_timeline,
                "source": timeline_path.as_posix(),
            },
            "generated_at": generated_at,
            "output_dir": output_dir.as_posix(),
            "script": {
                "path": script_path.relative_to(output_dir).as_posix(),
                "labels": label_map,
            },
            "pov": manifest_pov_section,
            "worlds": world_selection,
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
            "rating": rating_gate.get("rating"),
            "rating_gate": {
                "mode": rating_gate.get("mode"),
                "allowed": rating_gate.get("allowed"),
                "requires_ack": rating_gate.get("requires_ack"),
                "ack_status": rating_gate.get("ack_status"),
            },
        }

        pov_forks: Dict[str, POVFork] = {}
        if create_forks and pov_routes:
            forks_root = output_dir / "forks"
            for route in pov_routes:
                branch_root = forks_root / route.slug
                branch_game_dir = branch_root / "game"
                branch_script_path = branch_game_dir / "script.rpy"
                branch_manifest_path = branch_root / "export_manifest.json"
                branch_script_text = _render_script(
                    project_id=options.project_id,
                    timeline_id=resolved_timeline,
                    generated_at=generated_at,
                    backgrounds=backgrounds,
                    portraits=portraits,
                    label_map=label_map,
                    scenes=scenes,
                    alias_lookup=alias_lookup,
                    pov_routes=pov_routes,
                    include_switch_menu=False,
                    active_branch=route,
                )
                if options.dry_run:
                    diffs.append(_diff_text(branch_script_path, branch_script_text))
                else:
                    branch_root.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(game_dir, branch_game_dir)
                    branch_script_path.write_text(branch_script_text, encoding="utf-8")

                branch_manifest_payload = copy.deepcopy(manifest_payload)
                branch_manifest_payload["pov"] = {
                    "mode": "single",
                    "menu_enabled": False,
                    "active": route.pov,
                    "default": route.pov,
                    "routes": [
                        {
                            "id": route.pov,
                            "name": route.name,
                            "slug": route.slug,
                            "entry_label": route.entry_label,
                            "scene_labels": route.labels,
                            "scenes": route.scenes,
                        }
                    ],
                    "forks": [],
                }
                branch_manifest_json = json.dumps(branch_manifest_payload, indent=2)
                if options.dry_run:
                    diffs.append(_diff_text(branch_manifest_path, branch_manifest_json))
                else:
                    branch_manifest_path.write_text(
                        branch_manifest_json, encoding="utf-8"
                    )
                manifest_pov_section["forks"].append(
                    {
                        "id": route.pov,
                        "name": route.name,
                        "slug": route.slug,
                        "manifest": branch_manifest_path.relative_to(
                            output_dir
                        ).as_posix(),
                        "script": branch_script_path.relative_to(output_dir).as_posix(),
                        "game_dir": branch_game_dir.relative_to(output_dir).as_posix(),
                    }
                )
                pov_forks[route.pov] = POVFork(
                    pov=route.pov,
                    name=route.name,
                    slug=route.slug,
                    output_dir=branch_root,
                    game_dir=branch_game_dir,
                    script_path=branch_script_path,
                    manifest_path=branch_manifest_path,
                    manifest_payload=branch_manifest_payload,
                )

        manifest_path = output_dir / "export_manifest.json"
        manifest_json = json.dumps(manifest_payload, indent=2)
        if options.dry_run:
            diffs.append(_diff_text(manifest_path, manifest_json))
        else:
            manifest_path.write_text(manifest_json, encoding="utf-8")

        if not options.dry_run:
            scan_bundle(
                BundleContext(
                    project_id=options.project_id,
                    timeline_id=resolved_timeline,
                    scenes=scenes,
                    scene_sources=scene_sources,
                    licenses=project_data.get("licenses") or [],
                    assets=list(copied_asset_map.items()),
                    metadata={
                        "source": "export.renpy.orchestrator",
                        "project_path": project_path.as_posix(),
                        "timeline_path": timeline_path.as_posix(),
                        "output_dir": output_dir.as_posix(),
                        "script_path": script_path.as_posix(),
                        "manifest_path": manifest_path.as_posix(),
                        "pov_mode": effective_mode,
                        "pov_routes": manifest_pov_routes,
                        "worlds": world_selection,
                    },
                )
            )

        return ExportResult(
            ok=True,
            project_id=options.project_id,
            timeline_id=resolved_timeline,
            gate=gate,
            rating_gate=rating_gate,
            output_dir=output_dir,
            generated_at=generated_at,
            script_path=script_path,
            scene_files=scene_files,
            label_map=label_map,
            backgrounds=backgrounds,
            portraits=portraits,
            manifest_path=manifest_path,
            manifest_payload=manifest_payload,
            missing_backgrounds=missing_backgrounds,
            missing_portraits=missing_portraits,
            pov_mode=effective_mode,
            pov_menu_enabled=include_switch_menu,
            pov_default=pov_routes[0].pov if pov_routes else None,
            pov_routes=pov_routes,
            pov_forks=pov_forks,
            world_selection=world_selection,
            dry_run=options.dry_run,
            diffs=diffs,
        )

    def publish(
        self, export_result: ExportResult, options: PublishOptions
    ) -> PublishResult:
        output_dir = export_result.output_dir
        game_dir = output_dir / "game"
        if not game_dir.exists():
            raise HTTPException(
                status_code=400, detail="export output missing 'game' directory"
            )

        destination = options.destination.expanduser()
        if not destination.suffix:
            destination = destination.with_suffix(".zip")
        destination.parent.mkdir(parents=True, exist_ok=True)

        manifest = {
            "project": export_result.manifest_payload.get("project"),
            "timeline": export_result.manifest_payload.get("timeline"),
            "generated_at": export_result.generated_at,
            "assets": export_result.manifest_payload.get("assets"),
            "provenance": {
                "script": export_result.script_path.relative_to(output_dir).as_posix(),
                "labels": export_result.label_map,
                "manifest": export_result.manifest_path.relative_to(
                    output_dir
                ).as_posix(),
            },
            "platforms": list(options.platforms),
            "label": options.label or export_result.project_id,
        }

        platform_entries = []
        for platform in sorted(options.platforms):
            text = (
                f"Placeholder for {platform} build.\n"
                "Use the Ren'Py SDK to produce platform packages and drop them here.\n"
            )
            platform_entries.append(
                (f"platforms/{platform}/README.txt", text.encode("utf-8"))
            )

        arcname_root = options.label or export_result.project_id
        if not arcname_root:
            arcname_root = "renpy_build"

        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        manifest_file = destination.with_suffix(".manifest.json")
        manifest_file.write_bytes(manifest_bytes)

        with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=9) as zf:
            for file_path in sorted(game_dir.rglob("*")):
                if file_path.is_dir():
                    continue
                rel = file_path.relative_to(game_dir).as_posix()
                arcname = f"{arcname_root}/game/{rel}"
                _zip_write_file(zf, arcname, file_path)
            _zip_write_bytes(
                zf, f"{arcname_root}/publish_manifest.json", manifest_bytes
            )
            for arcname, payload in platform_entries:
                _zip_write_bytes(zf, f"{arcname_root}/{arcname}", payload)

        checksum = _sha256_file(destination)

        fork_archives: List[ForkArchive] = []
        if export_result.pov_forks:
            base_label = manifest["label"]
            base_stem = destination.stem
            base_suffix = destination.suffix or ".zip"
            for fork in export_result.pov_forks.values():
                if not fork.game_dir.exists():
                    continue
                fork_dest = destination.with_name(
                    f"{base_stem}__pov_{fork.slug}{base_suffix}"
                )
                fork_dest.parent.mkdir(parents=True, exist_ok=True)
                fork_arcname_root = f"{arcname_root}__{fork.slug}"
                fork_manifest = {
                    "project": export_result.manifest_payload.get("project"),
                    "timeline": export_result.manifest_payload.get("timeline"),
                    "generated_at": export_result.generated_at,
                    "assets": export_result.manifest_payload.get("assets"),
                    "provenance": {
                        "script": fork.script_path.relative_to(output_dir).as_posix(),
                        "labels": export_result.label_map,
                        "manifest": fork.manifest_path.relative_to(
                            output_dir
                        ).as_posix(),
                    },
                    "platforms": list(options.platforms),
                    "label": f"{base_label}__{fork.slug}",
                    "pov": fork.manifest_payload.get("pov"),
                }
                fork_manifest_bytes = json.dumps(fork_manifest, indent=2).encode(
                    "utf-8"
                )
                fork_manifest_file = destination.with_name(
                    f"{base_stem}__pov_{fork.slug}.manifest.json"
                )
                fork_manifest_file.write_bytes(fork_manifest_bytes)
                with ZipFile(
                    fork_dest, "w", compression=ZIP_DEFLATED, compresslevel=9
                ) as zf:
                    for file_path in sorted(fork.game_dir.rglob("*")):
                        if file_path.is_dir():
                            continue
                        rel = file_path.relative_to(fork.game_dir).as_posix()
                        arcname = f"{fork_arcname_root}/game/{rel}"
                        _zip_write_file(zf, arcname, file_path)
                    _zip_write_bytes(
                        zf,
                        f"{fork_arcname_root}/publish_manifest.json",
                        fork_manifest_bytes,
                    )
                    for arcname, payload in platform_entries:
                        _zip_write_bytes(zf, f"{fork_arcname_root}/{arcname}", payload)
                fork_checksum = _sha256_file(fork_dest)
                fork_archives.append(
                    ForkArchive(
                        pov=fork.pov,
                        name=fork.name,
                        slug=fork.slug,
                        archive_path=fork_dest,
                        manifest_path=fork_manifest_file,
                        checksum=fork_checksum,
                    )
                )

        sdk_invoked = False
        exit_code: Optional[int] = None
        stdout_text: Optional[str] = None
        stderr_text: Optional[str] = None

        if options.call_sdk:
            renpy_exec = self._resolve_renpy_executable(options.renpy_sdk)
            command = [
                str(renpy_exec),
                "launcher",
                "distribute",
                str(game_dir),
            ]
            command.extend(str(flag) for flag in options.renpy_cli_flags)
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                sdk_invoked = True
                exit_code = completed.returncode
                stdout_text = completed.stdout
                stderr_text = completed.stderr
            except FileNotFoundError as exc:
                raise HTTPException(
                    status_code=404,
                    detail=f"renpy executable not found: {exc}",
                ) from exc

        return PublishResult(
            ok=True,
            archive_path=destination,
            manifest_path=manifest_file,
            checksum=checksum,
            platforms=list(options.platforms),
            sdk_invoked=sdk_invoked,
            sdk_exit_code=exit_code,
            sdk_stdout=stdout_text,
            sdk_stderr=stderr_text,
            fork_archives=fork_archives,
        )

    def _resolve_renpy_executable(self, sdk_path: Optional[Path]) -> Path:
        if sdk_path is None:
            sdk_path = data_dir("renpy_sdk")
        sdk_path = sdk_path.expanduser().resolve()
        if not sdk_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Ren'Py SDK not found at {sdk_path}"
            )
        candidates = [
            sdk_path / "renpy.sh",
            sdk_path / "renpy.exe",
            sdk_path / "renpy",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise HTTPException(
            status_code=404, detail=f"No Ren'Py executable found under {sdk_path}"
        )
