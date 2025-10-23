from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from comfyvn.config import feature_flags
from comfyvn.core.policy_gate import policy_gate
from comfyvn.exporters.export_helpers import (
    build_label_manifest,
    diff_entry_to_dict,
    generate_provenance_bundle,
    slugify,
    write_label_manifest,
)
from comfyvn.exporters.renpy_orchestrator import ExportOptions, RenPyOrchestrator
from comfyvn.server.modules import export_api

router = APIRouter(prefix="/export", tags=["Exporters"])


def _default_output_dir(project_id: str, timeline_id: Optional[str]) -> Path:
    suffix = timeline_id or "timeline"
    slug = slugify(f"{project_id}_{suffix}")
    return Path("exports") / "renpy" / slug


def _default_bundle_path(
    project_id: str, timeline_id: str, *, label: Optional[str] = None
) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = slugify(label or f"{project_id}_{timeline_id}_{ts}")
    return Path("exports") / "bundles" / f"{slug}.zip"


def _asset_validation(project_data: dict, provenance_path: Path) -> Dict[str, Any]:
    expected = len(project_data.get("assets") or [])
    bundled = 0
    try:
        payload = json.loads(provenance_path.read_text(encoding="utf-8"))
        bundled = len(payload.get("assets") or [])
    except Exception:
        bundled = 0
    return {
        "expected_assets": expected,
        "bundled_assets": bundled,
        "matches": expected == bundled if expected else True,
    }


@router.post(
    "/renpy",
    summary="Export a project into a Ren'Py-ready folder under exports/.",
)
def export_renpy(
    project_id: str = Query(..., description="Project identifier to export."),
    timeline_id: Optional[str] = Query(
        None, description="Optional timeline identifier override."
    ),
    out: Optional[str] = Query(
        None,
        description="Optional output directory (defaults to exports/renpy/<project>_<timeline>).",
    ),
    dry_run: bool = Query(
        False,
        description="When true, perform a dry-run diff without writing files.",
    ),
    force: bool = Query(
        False, description="Overwrite the output directory when it already exists."
    ),
    per_scene: bool = Query(
        True, description="Include per-scene .rpy modules in the export."
    ),
    world_id: Optional[str] = Query(
        None, description="Optional worldline identifier override."
    ),
    world_mode: str = Query(
        "auto", description="World selection strategy (auto, single, multi)."
    ),
    pov_mode: str = Query(
        "auto",
        description="POV routing mode (auto, master, forks, both, disabled).",
    ),
    pov_switch_menu: bool = Query(
        True, description="Include the POV switch menu when multiple routes exist."
    ),
    acknowledged: bool = Query(
        False,
        description="Set to true once the rating warning has been acknowledged.",
    ),
    ack_token: Optional[str] = Query(
        None, description="Acknowledgement token from a previous rating gate check."
    ),
) -> Dict[str, Any]:
    output_dir = (
        Path(out).expanduser() if out else _default_output_dir(project_id, timeline_id)
    )
    orchestrator = RenPyOrchestrator()
    options = ExportOptions(
        project_id=project_id,
        timeline_id=timeline_id,
        world_id=world_id,
        world_mode=world_mode or "auto",
        output_dir=output_dir.expanduser(),
        force=force,
        dry_run=dry_run,
        policy_action="export.renpy",
        per_scene=per_scene,
        pov_mode=pov_mode,
        pov_switch_menu=pov_switch_menu,
        rating_acknowledged=acknowledged,
        rating_ack_token=ack_token,
    )
    export_result = orchestrator.export(options)
    label_manifest = build_label_manifest(export_result, weather_bake=False)

    if export_result.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "project": export_result.project_id,
            "timeline": export_result.timeline_id,
            "path": export_result.output_dir.as_posix(),
            "script": export_result.script_path.as_posix(),
            "manifest": export_result.manifest_path.as_posix(),
            "diffs": [diff_entry_to_dict(entry) for entry in export_result.diffs],
            "missing_assets": export_result.manifest_payload["missing_assets"],
            "label_manifest": label_manifest,
            "worlds": export_result.world_selection,
            "pov": export_result.manifest_payload.get("pov"),
            "gate": export_result.gate,
            "rating_gate": export_result.rating_gate,
            "rating": export_result.manifest_payload.get("rating"),
        }

    label_manifest_path = write_label_manifest(export_result.output_dir, label_manifest)

    project_data, _ = export_api._load_project(export_result.project_id)
    timeline_data, timeline_path, resolved_timeline = (
        export_api._ensure_timeline_payload(
            export_result.timeline_id,
            export_result.project_id,
            project_data,
        )
    )

    bundle_path, provenance_path, enforcement = generate_provenance_bundle(
        export_result,
        timeline_id=resolved_timeline,
        project_data=project_data,
        timeline_data=timeline_data,
        timeline_path=timeline_path,
    )

    asset_validation = _asset_validation(project_data, provenance_path)

    return {
        "ok": True,
        "dry_run": False,
        "project": export_result.project_id,
        "timeline": export_result.timeline_id,
        "path": export_result.output_dir.as_posix(),
        "script": export_result.script_path.as_posix(),
        "manifest": export_result.manifest_path.as_posix(),
        "label_manifest": label_manifest_path.as_posix(),
        "provenance_bundle": bundle_path.as_posix(),
        "provenance_json": provenance_path.as_posix(),
        "provenance_findings": enforcement.get("findings"),
        "asset_validation": asset_validation,
        "diffs": [diff_entry_to_dict(entry) for entry in export_result.diffs],
        "missing_assets": export_result.manifest_payload["missing_assets"],
        "worlds": export_result.world_selection,
        "pov": export_result.manifest_payload.get("pov"),
        "gate": export_result.gate,
        "rating_gate": export_result.rating_gate,
        "rating": export_result.manifest_payload.get("rating"),
    }


@router.post(
    "/bundle",
    summary="Build a Studio bundle zip (scenes, assets, provenance).",
)
def export_bundle(
    project_id: str = Query(..., description="Project identifier to bundle."),
    timeline_id: Optional[str] = Query(
        None, description="Optional timeline identifier override."
    ),
    out: Optional[str] = Query(
        None,
        description="Optional bundle path (defaults to exports/bundles/<project>_<timeline>_<timestamp>.zip).",
    ),
    dry_run: bool = Query(
        False,
        description="When true, compute export diffs without writing the bundle.",
    ),
    world_id: Optional[str] = Query(
        None, description="Optional worldline identifier override."
    ),
    world_mode: str = Query(
        "auto", description="World selection strategy (auto, single, multi)."
    ),
    per_scene: bool = Query(
        True, description="Include per-scene .rpy modules when staging the export."
    ),
    acknowledged: bool = Query(
        False,
        description="Set once the operator acknowledged any rating warning.",
    ),
    ack_token: Optional[str] = Query(
        None, description="Acknowledgement token returned by the rating gate."
    ),
) -> Dict[str, Any]:
    if not feature_flags.is_enabled("enable_export_bundle", default=True):
        raise HTTPException(
            status_code=403,
            detail="enable_export_bundle flag disabled",
        )

    gate = policy_gate.evaluate_action("export.bundle")
    if gate.get("requires_ack") and not gate.get("allow"):
        raise HTTPException(
            status_code=423,
            detail={
                "message": "export bundle blocked until legal acknowledgement is recorded",
                "gate": gate,
            },
        )

    export_dir = _default_output_dir(project_id, timeline_id)
    orchestrator = RenPyOrchestrator()
    options = ExportOptions(
        project_id=project_id,
        timeline_id=timeline_id,
        world_id=world_id,
        world_mode=world_mode or "auto",
        output_dir=export_dir.expanduser(),
        force=not dry_run,
        dry_run=dry_run,
        policy_action="export.bundle",
        per_scene=per_scene,
        rating_acknowledged=acknowledged,
        rating_ack_token=ack_token,
    )
    export_result = orchestrator.export(options)
    label_manifest = build_label_manifest(export_result, weather_bake=False)

    if export_result.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "project": export_result.project_id,
            "timeline": export_result.timeline_id,
            "path": export_result.output_dir.as_posix(),
            "diffs": [diff_entry_to_dict(entry) for entry in export_result.diffs],
            "missing_assets": export_result.manifest_payload["missing_assets"],
            "label_manifest": label_manifest,
            "worlds": export_result.world_selection,
            "pov": export_result.manifest_payload.get("pov"),
            "gate": gate,
            "rating_gate": export_result.rating_gate,
            "rating": export_result.manifest_payload.get("rating"),
        }

    label_manifest_path = write_label_manifest(export_result.output_dir, label_manifest)
    project_data, _ = export_api._load_project(export_result.project_id)
    timeline_data, timeline_path, resolved_timeline = (
        export_api._ensure_timeline_payload(
            export_result.timeline_id,
            export_result.project_id,
            project_data,
        )
    )

    bundle_target = (
        Path(out).expanduser()
        if out
        else _default_bundle_path(project_id, resolved_timeline)
    )
    bundle_path, provenance_path, enforcement = generate_provenance_bundle(
        export_result,
        timeline_id=resolved_timeline,
        project_data=project_data,
        timeline_data=timeline_data,
        timeline_path=timeline_path,
        bundle_path=bundle_target,
    )
    asset_validation = _asset_validation(project_data, provenance_path)

    return {
        "ok": True,
        "dry_run": False,
        "project": export_result.project_id,
        "timeline": resolved_timeline,
        "path": bundle_path.as_posix(),
        "renpy_path": export_result.output_dir.as_posix(),
        "script": export_result.script_path.as_posix(),
        "manifest": export_result.manifest_path.as_posix(),
        "label_manifest": label_manifest_path.as_posix(),
        "provenance_json": provenance_path.as_posix(),
        "provenance_findings": enforcement.get("findings"),
        "asset_validation": asset_validation,
        "diffs": [diff_entry_to_dict(entry) for entry in export_result.diffs],
        "missing_assets": export_result.manifest_payload["missing_assets"],
        "worlds": export_result.world_selection,
        "pov": export_result.manifest_payload.get("pov"),
        "gate": gate,
        "rating_gate": export_result.rating_gate,
        "rating": export_result.manifest_payload.get("rating"),
    }
