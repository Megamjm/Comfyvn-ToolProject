"""VN scenario builder.

The builder consolidates heterogeneous source payloads (ST transcripts,
VN packs, inline JSON, etc.) into the canonical schema defined in
``comfyvn.vn.schema`` and emits them to ``data/projects/<project>/``.
Modders can call the public ``build_project`` function via the HTTP
surface (see ``comfyvn/server/routes/vn_loader.py``) or directly from
Python for tooling workflows.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pydantic import ValidationError

from .schema import (
    AssetRef,
    Choice,
    Node,
    PersonaRef,
    Presentation,
    ScenarioDocument,
    Scene,
)

log = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: Optional[str], *, prefix: str, fallback_counter: int) -> str:
    if value:
        value = value.strip().lower()
        value = _SLUG_RE.sub("_", value)
        value = value.strip("_")
    if not value:
        value = f"{prefix}_{fallback_counter:03d}"
    return value


class BuildError(RuntimeError):
    """Raised when we cannot construct a viable project."""


@dataclass
class TraceEntry:
    """Tracks how a single source contributed to the build."""

    id: str
    kind: str
    origin: Optional[str]
    personas: List[str] = field(default_factory=list)
    scenes: List[str] = field(default_factory=list)
    assets: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    raw_meta: Dict[str, Any] = field(default_factory=dict)


class IdAllocator:
    """Ensures ids are unique and repeatable across project builds."""

    def __init__(self) -> None:
        self._used: set[str] = set()
        self._counters: Dict[str, int] = {}

    def ensure(self, candidate: Optional[str], *, prefix: str) -> str:
        counter = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = counter
        slug = _slugify(candidate, prefix=prefix, fallback_counter=counter)
        if slug not in self._used:
            self._used.add(slug)
            return slug
        # Resolve collisions by appending numeric suffixes.
        suffix = 2
        base = slug
        while slug in self._used:
            slug = f"{base}_{suffix}"
            suffix += 1
        self._used.add(slug)
        return slug


class BuildContext:
    """Stateful helper for project assembly."""

    def __init__(
        self,
        project_id: str,
        out_dir: Path,
        options: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.project_id = project_id
        self.out_dir = out_dir
        self.project_dir = out_dir / "data" / "projects" / project_id
        self.scenes_dir = self.project_dir / "scenes"
        self.personas_dir = self.project_dir / "personas"
        self.assets_dir = self.project_dir / "assets"

        self.options = options or {}
        self.id_alloc = IdAllocator()
        self.personas: Dict[str, PersonaRef] = {}
        self.scenes: List[Scene] = []
        self.assets: Dict[str, AssetRef] = {}
        self.traces: List[TraceEntry] = []
        self.warnings: List[str] = []

    # -- ingest -----------------------------------------------------------------

    def ingest(self, payload: Dict[str, Any], source_meta: Dict[str, Any]) -> None:
        """Parse and merge a raw payload into the context."""
        origin = source_meta.get("origin")
        kind = (source_meta.get("kind") or "inline").lower()
        source_id = source_meta.get("id") or self.id_alloc.ensure(None, prefix="source")
        trace = TraceEntry(
            id=source_id,
            kind=kind,
            origin=origin,
            raw_meta=dict(source_meta),
        )

        try:
            doc = self._coerce_document(payload, source_meta)
        except ValidationError as exc:
            message = (
                f"Failed to validate scenario payload from {origin or kind}: {exc}"
            )
            trace.warnings.append(message)
            self.warnings.append(message)
            log.warning(message)
            self.traces.append(trace)
            return

        for persona in doc.personas:
            persona_id = self._register_persona(persona, trace)
            trace.personas.append(persona_id)

        for scene in doc.scenes:
            scene_id = self._register_scene(scene, trace)
            trace.scenes.append(scene_id)

        for asset in doc.assets:
            asset_id = self._register_asset(asset)
            trace.assets.append(asset_id)

        self.traces.append(trace)

    # -- registration -----------------------------------------------------------

    def _register_persona(
        self, persona: PersonaRef, trace: Optional[TraceEntry] = None
    ) -> str:
        display = persona.displayName or persona.id
        persona_id = self.id_alloc.ensure(persona.id or display, prefix="persona")
        persona.id = persona_id
        persona.displayName = display or persona_id

        if persona_id in self.personas:
            existing = self.personas[persona_id]
            merged_tags = {*(existing.tags or []), *(persona.tags or [])}
            existing.tags = sorted(merged_tags)
            if not existing.portraitRef and persona.portraitRef:
                existing.portraitRef = persona.portraitRef
            msg = f"persona '{persona_id}' already registered; merged tags/metadata"
            self.warnings.append(msg)
            if trace:
                trace.warnings.append(msg)
            return persona_id

        self.personas[persona_id] = persona
        return persona_id

    def _register_scene(self, scene: Scene, trace: TraceEntry) -> str:
        title = scene.title or scene.id
        scene_id = self.id_alloc.ensure(scene.id or title, prefix="scene")
        scene.id = scene_id
        scene.title = title or scene_id
        scene.order = len(self.scenes) + 1

        # Normalise cast references.
        cast_refs: List[PersonaRef] = []
        for cast_entry in scene.cast:
            if isinstance(cast_entry, PersonaRef):
                persona = cast_entry
            else:
                persona = PersonaRef.model_validate(cast_entry)
            persona_id = self._ensure_persona_stub(persona)
            cast_refs.append(self.personas[persona_id])
        scene.cast = cast_refs

        # Normalise nodes / choices.
        for idx, node in enumerate(scene.nodes):
            node_id = self.id_alloc.ensure(
                node.id or f"{scene_id}_n{idx+1}", prefix="node"
            )
            node.id = node_id
            node.presentation = node.presentation or Presentation()

            if not node.choices:
                continue

            for choice_idx, choice in enumerate(node.choices):
                choice_id = self.id_alloc.ensure(
                    choice.id or f"{node_id}_c{choice_idx+1}", prefix="choice"
                )
                choice.id = choice_id
                if not choice.to:
                    choice_target = self._guess_choice_target(scene, idx)
                    choice.to = choice_target
                    msg = f"choice '{choice_id}' missing 'to'; defaulted to '{choice_target}'"
                    self.warnings.append(msg)
                    if trace:
                        trace.warnings.append(msg)
                choice.weight = choice.weight or 1.0

        # Ensure anchor ids exist.
        for idx, anchor in enumerate(scene.anchors):
            anchor_id = self.id_alloc.ensure(
                anchor.id or f"{scene_id}_a{idx+1}", prefix="anchor"
            )
            anchor.id = anchor_id

        self.scenes.append(scene)
        return scene_id

    def _register_asset(self, asset: AssetRef) -> str:
        asset_id = self.id_alloc.ensure(asset.id or asset.kind, prefix="asset")
        asset.id = asset_id
        existing = self.assets.get(asset_id)
        if existing:
            merged_meta = {**existing.meta, **asset.meta}
            existing.meta = merged_meta
            if not existing.uri and asset.uri:
                existing.uri = asset.uri
        else:
            self.assets[asset_id] = asset
        return asset_id

    # -- helpers ----------------------------------------------------------------

    def _ensure_persona_stub(self, persona: PersonaRef) -> str:
        if persona.id and persona.id in self.personas:
            return persona.id
        return self._register_persona(persona)

    def _guess_choice_target(self, scene: Scene, node_index: int) -> str:
        if node_index + 1 < len(scene.nodes):
            return scene.nodes[node_index + 1].id
        return "END"

    def _coerce_document(
        self, payload: Dict[str, Any], source_meta: Dict[str, Any]
    ) -> ScenarioDocument:
        """Normalise arbitrary payloads into a ScenarioDocument."""
        if isinstance(payload, list):
            payload = {"scenes": payload}
        elif isinstance(payload, (Scene, PersonaRef)):
            payload = (
                {"scenes": [payload]}
                if isinstance(payload, Scene)
                else {"personas": [payload]}
            )
        elif isinstance(payload, dict):
            payload = dict(payload)

        if "scene" in payload and "scenes" not in payload:
            payload["scenes"] = [payload.pop("scene")]
        if "persona" in payload and "personas" not in payload:
            payload["personas"] = [payload.pop("persona")]
        if "nodes" in payload and "scenes" not in payload:
            payload = {"scenes": [payload]}

        payload.setdefault("metadata", {})
        payload["metadata"].setdefault("source", source_meta)
        return ScenarioDocument.model_validate(payload)

    # -- output -----------------------------------------------------------------

    def write(self) -> Dict[str, Any]:
        if not self.scenes:
            raise BuildError(
                "No scenes were produced; ensure at least one source provided nodes."
            )

        self.scenes_dir.mkdir(parents=True, exist_ok=True)
        self.personas_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

        for scene in self.scenes:
            path = self.scenes_dir / f"{scene.id}.json"
            path.write_text(
                scene.model_dump_json(indent=2, exclude_unset=True), encoding="utf-8"
            )

        for persona in self.personas.values():
            path = self.personas_dir / f"{persona.id}.json"
            path.write_text(
                persona.model_dump_json(indent=2, exclude_unset=True), encoding="utf-8"
            )

        assets_payload = [
            asset.model_dump(exclude_unset=True) for asset in self.assets.values()
        ]
        if assets_payload:
            (self.assets_dir / "manifest.json").write_text(
                json.dumps({"items": assets_payload}, indent=2), encoding="utf-8"
            )

        manifest = self._build_manifest(assets_payload)
        manifest_path = self.project_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        debug_payload = {
            "projectId": self.project_id,
            "generatedAt": time.time(),
            "warnings": self.warnings,
            "trace": [trace.__dict__ for trace in self.traces],
            "options": self.options,
        }
        (self.project_dir / "debug.json").write_text(
            json.dumps(debug_payload, indent=2), encoding="utf-8"
        )

        return {
            "project": manifest,
            "scenes": [scene.model_dump(exclude_unset=True) for scene in self.scenes],
            "personas": [
                persona.model_dump(exclude_unset=True)
                for persona in self.personas.values()
            ],
            "assets": assets_payload,
            "debug": debug_payload,
        }

    def _build_manifest(self, assets_payload: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "projectId": self.project_id,
            "sceneCount": len(self.scenes),
            "personaCount": len(self.personas),
            "assetCount": len(assets_payload),
            "scenes": [
                {"id": scene.id, "title": scene.title, "order": scene.order}
                for scene in sorted(self.scenes, key=lambda s: s.order)
            ],
            "personas": [
                {"id": persona.id, "displayName": persona.displayName}
                for persona in self.personas.values()
            ],
            "assets": assets_payload,
            "hooks": {
                "events": [
                    "on_scene_enter",
                    "on_scene_exit",
                    "on_node_enter",
                    "on_choice_selected",
                    "on_asset_loaded",
                ],
                "apis": {
                    "personas": "/api/vn/personas",
                    "scenes": "/api/vn/scenes",
                    "assets": "/api/vn/assets",
                },
            },
        }


def _load_source_payload(
    source: Dict[str, Any], base_dir: Path
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    kind = (source.get("kind") or "inline").lower()
    meta = {
        "id": source.get("id"),
        "kind": kind,
        "origin": source.get("path") or source.get("origin"),
        "label": source.get("label"),
    }

    if kind in {"inline", "scenario"}:
        data = source.get("data") or source.get("payload") or {}
        meta["origin"] = meta["origin"] or "inline"
        return data, meta

    if kind in {"file", "json"}:
        path = Path(source.get("path") or "")
        if not path:
            raise BuildError("file source requires 'path'")
        if not path.is_absolute():
            path = base_dir / path
        if not path.exists():
            raise BuildError(f"source file not found: {path}")
        meta["origin"] = str(path)
        return json.loads(path.read_text(encoding="utf-8")), meta

    if kind == "directory":
        path = Path(source.get("path") or "")
        if not path:
            raise BuildError("directory source requires 'path'")
        if not path.is_absolute():
            path = base_dir / path
        if not path.exists():
            raise BuildError(f"source directory not found: {path}")
        payload: Dict[str, Any] = {"scenes": [], "personas": []}
        for file in sorted(path.glob("*.json")):
            try:
                content = json.loads(file.read_text(encoding="utf-8"))
                if "nodes" in content:
                    payload["scenes"].append(content)
                elif (
                    "displayName" in content
                    or "display_name" in content
                    or "tags" in content
                ):
                    payload["personas"].append(content)
                else:
                    payload.setdefault("assets", []).append(content)
            except json.JSONDecodeError as exc:
                raise BuildError(f"invalid JSON in {file}: {exc}") from exc
        meta["origin"] = str(path)
        return payload, meta

    raise BuildError(f"Unsupported source kind '{kind}'")


def build_project(
    project_id: str,
    sources: List[Dict[str, Any]],
    out_dir: Path,
    *,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compile imported materials into VN scenes for Mini-VN / Ren'Py."""
    ctx = BuildContext(project_id, out_dir, options)

    if not sources:
        raise BuildError("No sources supplied; provide at least one scenario source.")

    for source in sources:
        payload, meta = _load_source_payload(source, out_dir)
        ctx.ingest(payload, meta)

    return ctx.write()
