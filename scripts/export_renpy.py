#!/usr/bin/env python3
"""CLI helper for exporting ComfyVN projects into a minimal Ren'Py layout."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import HTTPException

from comfyvn.core.advisory_hooks import BundleContext
from comfyvn.core.advisory_hooks import scan as scan_bundle
from comfyvn.core.policy_gate import policy_gate
from comfyvn.server.modules import export_api


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
        default="build/game",
        help="Output directory for Ren'Py game files (default: %(default)s).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files under the output directory if present.",
    )
    return parser.parse_args()


def _ensure_output_dir(path: Path, *, force: bool) -> None:
    if path.exists():
        if not force and any(path.iterdir()):
            raise RuntimeError(
                f"output directory '{path}' is not empty (use --force to overwrite)"
            )
    else:
        path.mkdir(parents=True, exist_ok=True)


def _copy_tree(src: Path, dst: Path) -> List[str]:
    copied: List[str] = []
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied.append(target.as_posix())
    return copied


def _copy_assets(asset_pairs: List[Tuple[str, Path]], base: Path) -> List[str]:
    copied: List[str] = []
    assets_root = base / "assets"
    for rel, source in asset_pairs:
        destination = assets_root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            shutil.copy2(source, destination)
            copied.append(destination.as_posix())
    return copied


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

    try:
        renpy_info = export_api._build_renpy_project(
            timeline_id=timeline_id,
            timeline=timeline_data,
            project_id=args.project,
            project_data=project_data,
        )
    except HTTPException as exc:
        print(f"ERROR: {exc.detail}", file=sys.stderr)
        return exc.status_code or 1

    assets: List[Tuple[str, Path]] = export_api._collect_assets(
        project_data.get("assets") or []
    )

    output_dir = Path(args.out).expanduser().resolve()
    try:
        _ensure_output_dir(output_dir, force=args.force)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    game_dir = renpy_info["renpy_root"] / "game"
    copied_game_files = _copy_tree(game_dir, output_dir)
    copied_assets = _copy_assets(assets, output_dir)

    scan_bundle(
        BundleContext(
            project_id=args.project,
            timeline_id=timeline_id,
            scenes=renpy_info.get("scenes") or {},
            scene_sources=renpy_info.get("scene_sources") or {},
            licenses=project_data.get("licenses") or [],
            assets=assets,
            metadata={
                "source": "export.renpy.cli",
                "project_path": project_path.as_posix(),
                "timeline_path": timeline_path.as_posix(),
                "output_dir": output_dir.as_posix(),
            },
        )
    )

    summary: Dict[str, Any] = {
        "ok": True,
        "project": args.project,
        "timeline": timeline_id,
        "output_dir": output_dir.as_posix(),
        "copied_files": copied_game_files,
        "copied_assets": copied_assets,
        "gate": gate,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
