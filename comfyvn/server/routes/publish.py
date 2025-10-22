from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from comfyvn.config import feature_flags
from comfyvn.core.policy_gate import policy_gate
from comfyvn.exporters.publish_common import PackageOptions
from comfyvn.exporters.renpy_orchestrator import ExportOptions, RenPyOrchestrator
from comfyvn.exporters.web_packager import (
    WebPackageResult,
    WebRedactionOptions,
)
from comfyvn.exporters.web_packager import (
    build as build_web_package,
)

router = APIRouter(prefix="/api/publish/web", tags=["Publish"])


class _BaseRequest(BaseModel):
    project: str = Field(..., description="Project identifier to export.")
    timeline: Optional[str] = Field(
        None, description="Optional timeline identifier; defaults to project setting."
    )
    world: Optional[str] = Field(
        None, description="Optional worldline identifier used during export."
    )
    world_mode: Optional[str] = Field(
        "auto", description="World selection strategy (auto, single, multi)."
    )
    out: Optional[str] = Field(
        None,
        description="Override export output directory (defaults to build/renpy_game).",
    )
    per_scene: bool = Field(
        True, description="Whether to include per-scene .rpy modules in the export."
    )
    label: Optional[str] = Field(
        None, description="Human-readable label for the generated web bundle."
    )
    version: Optional[str] = Field(
        None, description="Semantic version string recorded in manifests."
    )
    publish_root: Optional[str] = Field(
        None,
        description="Root directory used for packaged archives (defaults to exports/publish).",
    )
    include_debug: bool = Field(
        False,
        description="Include modder hook catalogue alongside the bundle for debugging.",
    )
    dry_run: bool = Field(
        False, description="When true, compute bundle diffs without writing artefacts."
    )
    provenance_inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extra provenance inputs embedded into manifests (redaction permitting).",
    )
    metadata_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Reserved for downstream automation; ignored by the web packager.",
    )
    rating_acknowledged: bool = Field(
        False,
        description="Mark the rating gate as acknowledged when exporting restricted content.",
    )
    rating_ack_token: Optional[str] = Field(
        None,
        description="Token returned by rating preview endpoints when acknowledgement is required.",
    )


class WebBuildRequest(_BaseRequest):
    pass


class WebRedactRequest(_BaseRequest):
    strip_nsfw: bool = Field(
        True,
        description="When enabled, omit assets flagged as NSFW (metadata tags or rating).",
    )
    remove_provenance: bool = Field(
        True,
        description="Drop provenance and workflow identifiers from shipped metadata.",
    )
    watermark_text: Optional[str] = Field(
        None,
        max_length=160,
        description="Optional watermark text rendered across the preview surface.",
    )
    exclude_paths: List[str] = Field(
        default_factory=list,
        description="Asset relpaths to omit from the bundle regardless of NSFW metadata.",
    )


def _ensure_feature_enabled() -> None:
    if not feature_flags.is_enabled("enable_publish_web", default=False):
        raise HTTPException(status_code=403, detail="enable_publish_web disabled")


def _diff_to_dict(entry: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"path": entry.path, "status": entry.status}
    if entry.detail:
        payload["detail"] = entry.detail
    return payload


def _package_result_to_dict(result: WebPackageResult) -> Dict[str, Any]:
    return {
        "target": result.target,
        "slug": result.slug,
        "label": result.label,
        "version": result.version,
        "archive_path": result.archive_path.as_posix() if result.archive_path else None,
        "manifest_path": result.manifest_path.as_posix(),
        "content_map_path": result.content_map_path.as_posix(),
        "preview_path": result.preview_path.as_posix(),
        "redaction_path": result.redaction_path.as_posix(),
        "hooks_path": result.hooks_path.as_posix() if result.hooks_path else None,
        "checksum": result.checksum,
        "dry_run": result.dry_run,
        "diffs": [_diff_to_dict(entry) for entry in result.diffs],
        "manifest": result.manifest,
        "content_map": result.content_map,
        "preview": result.preview,
        "redaction": result.redaction,
    }


def _export_project(payload: _BaseRequest) -> Any:
    output_dir = (
        Path(payload.out).expanduser() if payload.out else Path("build/renpy_game")
    )
    orchestrator = RenPyOrchestrator()
    options = ExportOptions(
        project_id=payload.project,
        timeline_id=payload.timeline,
        world_id=payload.world,
        world_mode=payload.world_mode or "auto",
        output_dir=output_dir,
        force=not payload.dry_run,
        dry_run=payload.dry_run,
        per_scene=payload.per_scene,
        rating_acknowledged=payload.rating_acknowledged,
        rating_ack_token=payload.rating_ack_token,
    )
    return orchestrator.export(options)


def _package_options(payload: _BaseRequest) -> PackageOptions:
    publish_root = (
        Path(payload.publish_root).expanduser()
        if payload.publish_root
        else Path("exports/publish")
    )
    return PackageOptions(
        label=payload.label,
        version=payload.version,
        platforms=("web",),
        publish_root=publish_root,
        include_debug=payload.include_debug,
        dry_run=payload.dry_run,
        provenance_inputs=dict(payload.provenance_inputs),
        metadata_overrides=dict(payload.metadata_overrides),
    )


@router.post(
    "/build",
    summary="Build a deterministic Mini-VN web bundle without applying redaction rules.",
)
def build_bundle(payload: WebBuildRequest) -> Dict[str, Any]:
    _ensure_feature_enabled()
    gate = policy_gate.evaluate_action("publish.web")
    if gate.get("requires_ack") and not gate.get("allow"):
        raise HTTPException(
            status_code=423,
            detail={
                "message": "publish.web blocked until advisory acknowledgement is recorded",
                "gate": gate,
            },
        )

    export_result = _export_project(payload)
    package_options = _package_options(payload)
    package_result = build_web_package(
        export_result,
        package_options,
        redaction=WebRedactionOptions(),
    )
    return {
        "gate": gate,
        "result": _package_result_to_dict(package_result),
    }


@router.post(
    "/redact",
    summary="Build a deterministic Mini-VN web bundle with redaction toggles applied.",
)
def redact_bundle(payload: WebRedactRequest) -> Dict[str, Any]:
    _ensure_feature_enabled()
    gate = policy_gate.evaluate_action("publish.web")
    if gate.get("requires_ack") and not gate.get("allow"):
        raise HTTPException(
            status_code=423,
            detail={
                "message": "publish.web blocked until advisory acknowledgement is recorded",
                "gate": gate,
            },
        )

    export_result = _export_project(payload)
    package_options = _package_options(payload)
    redaction = WebRedactionOptions(
        strip_nsfw=payload.strip_nsfw,
        remove_provenance=payload.remove_provenance,
        watermark_text=payload.watermark_text,
        exclude_paths=tuple(payload.exclude_paths),
    )
    package_result = build_web_package(
        export_result,
        package_options,
        redaction=redaction,
    )
    return {
        "gate": gate,
        "result": _package_result_to_dict(package_result),
    }


@router.get(
    "/preview",
    summary="Inspect the latest Mini-VN web bundle and its health snapshot.",
)
def preview_bundle(
    slug: Optional[str] = Query(
        None,
        description="Optional slug to inspect. When omitted, returns known bundles.",
    ),
    publish_root: Optional[str] = Query(
        None,
        description="Override publish root used when searching for bundles.",
    ),
) -> Dict[str, Any]:
    _ensure_feature_enabled()
    base_root = (
        Path(publish_root).expanduser() if publish_root else Path("exports/publish")
    )
    web_root = base_root / "web"
    if not web_root.exists():
        return {
            "bundles": [],
            "base_root": base_root.as_posix(),
            "message": "No web bundles found.",
        }

    if slug:
        manifest_path = web_root / f"{slug}.web.manifest.json"
        content_map_path = web_root / f"{slug}.web.content_map.json"
        preview_path = web_root / f"{slug}.web.preview.json"
        redaction_path = web_root / f"{slug}.web.redaction.json"

        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail="Bundle manifest not found.")

        return {
            "slug": slug,
            "archive_path": _path_if_exists(web_root / f"{slug}.web.zip"),
            "hooks_path": _path_if_exists(web_root / f"{slug}.web.hooks.json"),
            "manifest": _load_json(manifest_path),
            "content_map": _load_json(content_map_path),
            "preview": _load_json(preview_path),
            "redaction": _load_json(redaction_path),
        }

    bundles: List[Dict[str, Any]] = []
    for manifest_path in sorted(web_root.glob("*.web.manifest.json")):
        slug_name = manifest_path.name.replace(".web.manifest.json", "")
        preview_path = web_root / f"{slug_name}.web.preview.json"
        preview_payload = _load_json(preview_path)
        bundles.append(
            {
                "slug": slug_name,
                "manifest_path": manifest_path.as_posix(),
                "preview": preview_payload,
            }
        )
    return {
        "bundles": bundles,
        "base_root": base_root.as_posix(),
    }


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8") or "{}")


def _path_if_exists(path: Path) -> Optional[str]:
    return path.as_posix() if path.exists() else None
