#!/usr/bin/env python3
"""CLI helper for exporting ComfyVN projects into a Ren'Py layout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import HTTPException

from comfyvn.exporters.renpy_orchestrator import (
    DiffEntry,
    ExportOptions,
    PublishOptions,
    RenPyOrchestrator,
)

DEFAULT_PUBLISH_PATH = Path("build/renpy_publish.zip")
DEFAULT_PLATFORMS = ("windows", "linux", "mac")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a ComfyVN project to a Ren'Py-ready folder."
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Project identifier to export.",
    )
    parser.add_argument(
        "--timeline",
        help="Optional timeline identifier override.",
    )
    parser.add_argument(
        "--world",
        help="Optional worldline identifier override.",
    )
    parser.add_argument(
        "--world-mode",
        choices=["auto", "single", "multi"],
        default="auto",
        help="Worldline export selection mode (default: %(default)s).",
    )
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute a dry-run diff without writing any files.",
    )
    parser.add_argument(
        "--no-per-scene",
        action="store_true",
        help="Skip emitting per-scene .rpy modules (only write script.rpy).",
    )
    parser.add_argument(
        "--pov-mode",
        choices=["auto", "disabled", "master", "forks", "both"],
        default="auto",
        help="POV export strategy (default: %(default)s).",
    )
    parser.add_argument(
        "--no-pov-switch",
        dest="pov_switch_menu",
        action="store_false",
        help="Disable the Switch POV menu for master exports.",
    )
    parser.set_defaults(pov_switch_menu=True)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Run the publish preset after export (zip + manifest).",
    )
    parser.add_argument(
        "--publish-out",
        help="Destination zip path for publish preset (default derived from --out).",
    )
    parser.add_argument(
        "--publish-label",
        help="Root folder name to use inside the publish archive.",
    )
    parser.add_argument(
        "--platform",
        dest="platforms",
        action="append",
        default=[],
        help="Platform placeholder to include in publish zip (repeatable). Default windows/linux/mac.",
    )
    parser.add_argument(
        "--invoke-sdk",
        action="store_true",
        help="Invoke Ren'Py SDK CLI distribute command after zipping.",
    )
    parser.add_argument(
        "--renpy-sdk",
        help="Path to Ren'Py SDK root when invoking the CLI.",
    )
    parser.add_argument(
        "--renpy-flag",
        dest="renpy_flags",
        action="append",
        default=[],
        help="Additional flag passed to the Ren'Py CLI (repeatable).",
    )
    parser.add_argument(
        "--rating-ack-token",
        help="Pass an acknowledgement token returned by a previous rating gate warning.",
    )
    parser.add_argument(
        "--rating-acknowledged",
        action="store_true",
        help="Confirm the operator acknowledged the rating warning (requires --rating-ack-token).",
    )
    return parser.parse_args()


def _diff_to_dict(entry: DiffEntry) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "path": entry.path,
        "status": entry.status,
    }
    if entry.detail:
        payload["detail"] = entry.detail
    return payload


def _publish_path(args: argparse.Namespace, project: str, timeline: str) -> Path:
    if args.publish_out:
        candidate = Path(args.publish_out).expanduser()
    else:
        candidate = DEFAULT_PUBLISH_PATH
    candidate = candidate.expanduser()
    if candidate.is_dir():
        basename = f"{project}_{timeline}.zip"
        return candidate / basename
    if not candidate.suffix:
        return candidate.with_suffix(".zip")
    return candidate


def _error_payload(exc: HTTPException) -> Dict[str, Any]:
    detail = exc.detail
    if isinstance(detail, dict):
        message = detail.get("message") or detail
    else:
        message = detail
    return {
        "ok": False,
        "status": exc.status_code,
        "error": message,
    }


def main() -> int:
    args = _parse_args()
    orchestrator = RenPyOrchestrator()
    options = ExportOptions(
        project_id=args.project,
        timeline_id=args.timeline,
        world_id=args.world,
        world_mode=args.world_mode,
        output_dir=Path(args.out).expanduser(),
        force=args.force,
        dry_run=args.dry_run,
        policy_action="export.renpy.cli",
        per_scene=not args.no_per_scene,
        pov_mode=args.pov_mode,
        pov_switch_menu=args.pov_switch_menu,
        rating_acknowledged=args.rating_acknowledged,
        rating_ack_token=args.rating_ack_token,
    )

    try:
        export_result = orchestrator.export(options)
    except HTTPException as exc:
        payload = _error_payload(exc)
        print(json.dumps(payload, indent=2), file=sys.stderr)
        return exc.status_code or 1

    if export_result.dry_run:
        payload = {
            "ok": True,
            "project": export_result.project_id,
            "timeline": export_result.timeline_id,
            "dry_run": True,
            "output_dir": export_result.output_dir.as_posix(),
            "diffs": [_diff_to_dict(entry) for entry in export_result.diffs],
            "missing_assets": export_result.manifest_payload["missing_assets"],
            "gate": export_result.gate,
            "rating_gate": export_result.rating_gate,
            "rating": export_result.manifest_payload.get("rating"),
            "worlds": export_result.world_selection,
        }
        print(json.dumps(payload, indent=2))
        return 0

    summary: Dict[str, Any] = {
        "ok": True,
        "project": export_result.project_id,
        "timeline": export_result.timeline_id,
        "output_dir": export_result.output_dir.as_posix(),
        "script": export_result.script_path.as_posix(),
        "scene_modules": {
            scene_id: path.as_posix()
            for scene_id, path in export_result.scene_files.items()
        },
        "manifest": export_result.manifest_path.as_posix(),
        "missing_assets": export_result.manifest_payload["missing_assets"],
        "generated_at": export_result.generated_at,
        "backgrounds_copied": len(export_result.backgrounds),
        "portraits_copied": len(export_result.portraits),
        "worlds": export_result.world_selection,
        "gate": export_result.gate,
        "rating_gate": export_result.rating_gate,
        "rating": export_result.manifest_payload.get("rating"),
    }

    if export_result.pov_routes:

        def _rel(path: Path) -> str:
            try:
                return path.relative_to(export_result.output_dir).as_posix()
            except ValueError:
                return path.as_posix()

        summary["pov"] = {
            "mode": export_result.pov_mode,
            "menu_enabled": export_result.pov_menu_enabled,
            "default": export_result.pov_default,
            "routes": [
                {
                    "id": route.pov,
                    "name": route.name,
                    "slug": route.slug,
                    "entry_label": route.entry_label,
                    "scene_labels": route.labels,
                    "scenes": route.scenes,
                }
                for route in export_result.pov_routes
            ],
            "forks": {
                pov: {
                    "name": fork.name,
                    "slug": fork.slug,
                    "game_dir": _rel(fork.game_dir),
                    "script": _rel(fork.script_path),
                    "manifest": _rel(fork.manifest_path),
                }
                for pov, fork in export_result.pov_forks.items()
            },
        }

    if args.publish:
        platforms = tuple(args.platforms) if args.platforms else DEFAULT_PLATFORMS
        destination = _publish_path(
            args, export_result.project_id, export_result.timeline_id
        )
        publish_options = PublishOptions(
            destination=destination,
            label=args.publish_label,
            platforms=platforms,
            renpy_sdk=Path(args.renpy_sdk).expanduser() if args.renpy_sdk else None,
            call_sdk=args.invoke_sdk,
            renpy_cli_flags=tuple(args.renpy_flags),
        )
        try:
            publish_result = orchestrator.publish(export_result, publish_options)
        except HTTPException as exc:
            payload = _error_payload(exc)
            payload["phase"] = "publish"
            print(json.dumps(payload, indent=2), file=sys.stderr)
            return exc.status_code or 1
        summary["publish"] = {
            "archive": publish_result.archive_path.as_posix(),
            "manifest": publish_result.manifest_path.as_posix(),
            "checksum": publish_result.checksum,
            "platforms": list(publish_result.platforms),
            "sdk_invoked": publish_result.sdk_invoked,
            "sdk_exit_code": publish_result.sdk_exit_code,
        }
        if publish_result.sdk_stdout:
            summary["publish"]["sdk_stdout"] = publish_result.sdk_stdout
        if publish_result.sdk_stderr:
            summary["publish"]["sdk_stderr"] = publish_result.sdk_stderr
        if publish_result.fork_archives:
            summary["publish"]["fork_archives"] = [
                {
                    "pov": record.pov,
                    "name": record.name,
                    "slug": record.slug,
                    "archive": record.archive_path.as_posix(),
                    "manifest": record.manifest_path.as_posix(),
                    "checksum": record.checksum,
                }
                for record in publish_result.fork_archives
            ]

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
