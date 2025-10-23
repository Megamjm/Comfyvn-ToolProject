from __future__ import annotations

from dataclasses import replace
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from comfyvn.advisory.policy import evaluate_action, gate_status
from comfyvn.config import feature_flags
from comfyvn.core import modder_hooks
from comfyvn.core.policy_gate import policy_gate
from comfyvn.exporters import itch_packager, steam_packager
from comfyvn.exporters.publish_common import PackageOptions, PackageResult
from comfyvn.exporters.renpy_orchestrator import (
    DiffEntry,
    ExportOptions,
    RenPyOrchestrator,
)
from comfyvn.obs.structlog_adapter import get_logger

LOGGER = get_logger("export.publish.api", component="export.publish")
PUBLISH_LOG_PATH = Path("logs/export/publish.log")

router = APIRouter(prefix="/api/export", tags=["Export"])


def _diff_to_dict(entry: DiffEntry) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"path": entry.path, "status": entry.status}
    if entry.detail:
        payload["detail"] = entry.detail
    return payload


def _cli_command(
    project: str,
    timeline: Optional[str],
    world: Optional[str],
    world_mode: Optional[str],
    out_dir: Path,
    per_scene: bool,
) -> List[str]:
    command = [
        "python",
        "scripts/export_renpy.py",
        "--project",
        project,
        "--out",
        out_dir.as_posix(),
    ]
    if timeline:
        command.extend(["--timeline", timeline])
    if world:
        command.extend(["--world", world])
    if world_mode and world_mode != "auto":
        command.extend(["--world-mode", world_mode])
    if not per_scene:
        command.append("--no-per-scene")
    return command


class PublishTarget(str, Enum):
    steam = "steam"
    itch = "itch"


class PublishRequest(BaseModel):
    project: str = Field(..., description="Project identifier to export.")
    timeline: Optional[str] = Field(
        None,
        description="Optional timeline identifier; defaults to active project timeline.",
    )
    world: Optional[str] = Field(
        None, description="Optional worldline identifier to lock during export."
    )
    world_mode: Optional[str] = Field(
        "auto", description="World selection strategy (auto, single, multi)."
    )
    out: Optional[str] = Field(
        None,
        description="Optional output directory for the Ren'Py export (defaults to build/renpy_game).",
    )
    per_scene: bool = Field(
        True, description="Whether to include per-scene .rpy modules."
    )
    label: Optional[str] = Field(
        None,
        description="Human-readable label for the packaged build (defaults to project title).",
    )
    version: Optional[str] = Field(
        None, description="Semantic version string recorded in manifests."
    )
    targets: List[PublishTarget] = Field(
        default_factory=lambda: [PublishTarget.steam, PublishTarget.itch],
        description="Publish targets to build (steam, itch).",
    )
    platforms: List[str] = Field(
        default_factory=lambda: ["windows", "linux"],
        description="Platform builds to include (windows, linux, mac).",
    )
    publish_root: Optional[str] = Field(
        None,
        description="Root directory to store packaged archives (defaults to exports/publish).",
    )
    icon: Optional[str] = Field(
        None, description="Optional path to an icon file injected into the package."
    )
    eula: Optional[str] = Field(
        None, description="Optional path to a EULA text file injected into the package."
    )
    license_path: Optional[str] = Field(
        None,
        description="Optional path to a license text file overriding the generated summary.",
    )
    include_debug: bool = Field(
        False,
        description="Include debug artefacts (modder hooks manifest, advisory notes).",
    )
    dry_run: bool = Field(
        False,
        description="When true, compute diffs without writing archives to disk.",
    )
    provenance_inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional provenance inputs attached to generated sidecars.",
    )
    metadata_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata blob merged into package manifests for downstream automation.",
    )


def _path_or_none(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    return Path(value).expanduser()


def _dedupe_targets(targets: Sequence[PublishTarget]) -> List[str]:
    resolved: List[str] = []
    for entry in targets:
        value = entry.value if isinstance(entry, PublishTarget) else str(entry)
        if value not in resolved:
            resolved.append(value)
    return resolved


def _package_to_dict(result: PackageResult) -> Dict[str, Any]:
    return {
        "target": result.target,
        "label": result.label,
        "version": result.version,
        "archive_path": result.archive_path.as_posix() if result.archive_path else None,
        "manifest_path": result.manifest_path.as_posix(),
        "license_manifest_path": result.license_manifest_path.as_posix(),
        "checksum": result.checksum,
        "dry_run": result.dry_run,
        "diffs": [_diff_to_dict(entry) for entry in result.diffs],
        "provenance_sidecars": result.provenance_sidecars,
        "hooks_path": result.hooks_path,
        "manifest": result.manifest,
        "license_manifest": result.license_manifest,
    }


@router.get(
    "/renpy/preview",
    summary="Dry-run Ren'Py export and return diff summary without writing files.",
)
def renpy_preview(
    project: str = Query(..., description="Project identifier for the export preview."),
    timeline: Optional[str] = Query(
        None,
        description="Optional timeline to preview; defaults to the project's active timeline.",
    ),
    world: Optional[str] = Query(
        None, description="Optional worldline identifier to preview."
    ),
    world_mode: Optional[str] = Query(
        "auto", description="World selection strategy (auto, single, multi)."
    ),
    out: Optional[str] = Query(
        None,
        description="Output directory used for diff context (defaults to build/renpy_game).",
    ),
    per_scene: bool = Query(
        True,
        description="Whether to include per-scene .rpy modules in the preview.",
    ),
    acknowledged: bool = Query(
        False,
        description="Set to true once the reviewer acknowledged the rating warning.",
    ),
    ack_token: Optional[str] = Query(
        None,
        description="Acknowledgement token returned by a previous preview attempt.",
    ),
) -> Dict[str, Any]:
    orchestrator = RenPyOrchestrator()
    output_dir = Path(out).expanduser() if out else Path("build/renpy_game")
    options = ExportOptions(
        project_id=project,
        timeline_id=timeline,
        world_id=world,
        world_mode=world_mode or "auto",
        output_dir=output_dir,
        force=False,
        dry_run=True,
        policy_action="export.renpy",
        per_scene=per_scene,
        rating_acknowledged=acknowledged,
        rating_ack_token=ack_token,
    )
    result = orchestrator.export(options)
    return {
        "ok": True,
        "project": result.project_id,
        "timeline": result.timeline_id,
        "output_dir": result.output_dir.as_posix(),
        "diffs": [_diff_to_dict(entry) for entry in result.diffs],
        "missing_assets": result.manifest_payload["missing_assets"],
        "gate": result.gate,
        "rating_gate": result.rating_gate,
        "rating": result.manifest_payload.get("rating"),
        "worlds": result.world_selection,
        "recommended_command": _cli_command(
            project, timeline, world, world_mode, output_dir, per_scene
        ),
    }


@router.post(
    "/publish",
    summary="Export Ren'Py content and package deterministic builds for Steam and itch.",
)
def export_publish(payload: PublishRequest) -> Dict[str, Any]:
    if not feature_flags.is_enabled("enable_export_publish", default=False):
        raise HTTPException(status_code=403, detail="enable_export_publish disabled")

    publish_gate = policy_gate.evaluate_action("export.publish")
    if publish_gate.get("requires_ack"):
        LOGGER.warning("Advisory disclaimer pending for export.publish")

    output_dir = (
        Path(payload.out).expanduser() if payload.out else Path("build/renpy_game")
    )
    orchestrator = RenPyOrchestrator()
    export_options = ExportOptions(
        project_id=payload.project,
        timeline_id=payload.timeline,
        world_id=payload.world,
        world_mode=payload.world_mode or "auto",
        output_dir=output_dir,
        force=not payload.dry_run,
        dry_run=payload.dry_run,
        per_scene=payload.per_scene,
    )

    LOGGER.info(
        "Export publish requested",
        project=payload.project,
        timeline=payload.timeline,
        targets=[t.value for t in payload.targets],
        dry_run=payload.dry_run,
    )

    export_result = orchestrator.export(export_options)

    targets = _dedupe_targets(payload.targets)
    if not targets:
        raise HTTPException(status_code=400, detail="no publish targets requested")

    publish_root = (
        Path(payload.publish_root).expanduser()
        if payload.publish_root
        else Path("exports/publish")
    )
    base_options = PackageOptions(
        label=payload.label,
        version=payload.version,
        platforms=tuple(payload.platforms or ["windows", "linux"]),
        publish_root=publish_root,
        icon_path=_path_or_none(payload.icon),
        eula_path=_path_or_none(payload.eula),
        license_path=_path_or_none(payload.license_path),
        include_debug=payload.include_debug,
        dry_run=payload.dry_run,
        provenance_inputs=dict(payload.provenance_inputs),
        metadata_overrides=dict(payload.metadata_overrides),
    )

    packages: Dict[str, PackageResult] = {}

    for target in targets:
        if target == "steam":
            if not feature_flags.is_enabled(
                "enable_export_publish_steam", default=False
            ):
                raise HTTPException(
                    status_code=403, detail="enable_export_publish_steam disabled"
                )
            options = replace(base_options)
            result = steam_packager.package(export_result, options)
            packages[target] = result
        elif target == "itch":
            if not feature_flags.is_enabled(
                "enable_export_publish_itch", default=False
            ):
                raise HTTPException(
                    status_code=403, detail="enable_export_publish_itch disabled"
                )
            options = replace(base_options)
            result = itch_packager.package(export_result, options)
            packages[target] = result
        else:
            raise HTTPException(
                status_code=400, detail=f"unsupported publish target '{target}'"
            )

    log_path = PUBLISH_LOG_PATH.expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    response_packages = {
        key: _package_to_dict(value) for key, value in packages.items()
    }

    if payload.dry_run:
        modder_hooks.emit(
            "on_export_publish_preview",
            {
                "project_id": export_result.project_id,
                "timeline_id": export_result.timeline_id,
                "targets": targets,
                "label": (
                    response_packages[next(iter(response_packages))]["label"]
                    if response_packages
                    else payload.label
                ),
                "version": payload.version,
                "platforms": {
                    key: value["manifest"].get("platforms") or payload.platforms
                    for key, value in response_packages.items()
                },
                "diffs": {
                    key: value["diffs"] for key, value in response_packages.items()
                },
            },
        )
    else:
        for key, result in packages.items():
            modder_hooks.emit(
                "on_export_publish_complete",
                {
                    "project_id": export_result.project_id,
                    "timeline_id": export_result.timeline_id,
                    "target": key,
                    "label": result.label,
                    "version": result.version,
                    "checksum": result.checksum,
                    "archive_path": (
                        result.archive_path.as_posix() if result.archive_path else None
                    ),
                    "manifest_path": result.manifest_path.as_posix(),
                    "platforms": result.manifest.get("platforms") or payload.platforms,
                    "provenance": result.provenance_sidecars,
                },
            )

    LOGGER.info(
        "Export publish completed",
        project=export_result.project_id,
        timeline=export_result.timeline_id,
        targets=targets,
        dry_run=payload.dry_run,
    )

    return {
        "ok": True,
        "project": export_result.project_id,
        "timeline": export_result.timeline_id,
        "targets": targets,
        "publish_gate": publish_gate,
        "export_gate": export_result.gate,
        "export": {
            "output_dir": export_result.output_dir.as_posix(),
            "generated_at": export_result.generated_at,
            "manifest_path": export_result.manifest_path.as_posix(),
            "script_path": export_result.script_path.as_posix(),
            "dry_run": export_result.dry_run,
            "diffs": [_diff_to_dict(entry) for entry in export_result.diffs],
            "worlds": export_result.world_selection,
            "pov": export_result.manifest_payload.get("pov"),
        },
        "packages": response_packages,
        "logs_path": log_path.as_posix(),
    }


@router.get(
    "/bundle/status",
    summary="Describe feature flag and policy gate status for Studio bundle export.",
)
def bundle_status(
    action: str = Query(
        "export.bundle",
        description="Action identifier evaluated against the policy gate.",
    ),
) -> Dict[str, Any]:
    return {
        "ok": True,
        "enabled": feature_flags.is_enabled("enable_export_bundle", default=False),
        "gate": evaluate_action(action),
        "status": gate_status().to_dict(),
    }
