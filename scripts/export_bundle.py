#!/usr/bin/env python3
"""CLI helper to export a ComfyVN Studio bundle with provenance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import HTTPException

from comfyvn.advisory.policy import evaluate_action
from comfyvn.config import feature_flags
from comfyvn.server.modules import export_api


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a ComfyVN project bundle (scenes + assets + provenance)."
    )
    parser.add_argument(
        "--project", required=True, help="Project identifier to export."
    )
    parser.add_argument(
        "--timeline",
        help="Optional timeline identifier. Defaults to project's timeline or scene order.",
    )
    parser.add_argument(
        "--out",
        default="build/studio_bundle.zip",
        help="Output zip path (default: %(default)s).",
    )
    return parser.parse_args()


def _convert_findings(raw: list[dict]) -> list[dict]:
    if not raw:
        return []
    findings: list[dict] = []
    for entry in raw:
        severity = str(entry.get("severity") or "").lower()
        if severity in {"error", "critical", "block"}:
            level = "block"
        elif severity == "warn":
            level = "warn"
        else:
            level = "info"
        findings.append(
            {
                "level": level,
                "code": entry.get("kind") or "ADVISORY",
                "message": entry.get("message"),
                "detail": entry.get("detail"),
                "issue_id": entry.get("issue_id"),
            }
        )
    return findings


def main() -> int:
    args = _parse_args()
    if not feature_flags.is_enabled("enable_export_bundle", default=False):
        print(
            "enable_export_bundle flag disabled. Enable it in comfyvn.json before exporting.",
            file=sys.stderr,
        )
        return 3
    gate = evaluate_action("export.bundle.cli")

    try:
        project_data, _ = export_api._load_project(args.project)
    except HTTPException as exc:
        print(f"Project load failed: {exc.detail}", file=sys.stderr)
        return 1

    try:
        timeline_data, timeline_path, resolved_timeline = (
            export_api._ensure_timeline_payload(
                args.timeline, args.project, project_data
            )
        )
    except HTTPException as exc:
        print(f"Timeline resolution failed: {exc.detail}", file=sys.stderr)
        return 1

    try:
        renpy_info = export_api._build_renpy_project(
            timeline_id=resolved_timeline,
            timeline=timeline_data,
            project_id=args.project,
            project_data=project_data,
        )
    except HTTPException as exc:
        print(f"Ren'Py snapshot failed: {exc.detail}", file=sys.stderr)
        return 1

    try:
        bundle_path, provenance, enforcement = export_api._build_bundle_archive(
            project_id=args.project,
            project_data=project_data,
            timeline_id=resolved_timeline,
            timeline_data=timeline_data,
            timeline_path=timeline_path,
            renpy_info=renpy_info,
            bundle_path=Path(args.out),
        )
    except HTTPException as exc:  # pragma: no cover - defensive
        print(f"Bundle export failed: {exc.detail}", file=sys.stderr)
        return 1

    if hasattr(enforcement, "findings"):
        raw_findings = enforcement.findings  # type: ignore[attr-defined]
    else:
        raw_findings = enforcement

    findings = _convert_findings(raw_findings)
    blockers = [entry for entry in findings if entry.get("level") == "block"]
    warnings = [entry for entry in findings if entry.get("level") == "warn"]

    payload = {
        "ok": True,
        "blocked": False,
        "project": args.project,
        "timeline": resolved_timeline,
        "out": bundle_path.as_posix(),
        "gate": gate,
        "disclaimer": gate.get("disclaimer"),
        "findings": findings,
        "warning_count": len(warnings),
        "blocker_count": len(blockers),
        "provenance": {
            "generated_at": provenance.get("generated_at"),
            "project": provenance.get("project"),
            "timeline": provenance.get("timeline"),
            "renpy_project": {
                "script": provenance.get("renpy_project", {}).get("script"),
                "labels": provenance.get("renpy_project", {}).get("labels"),
            },
        },
    }
    payload["log_path"] = None
    if hasattr(enforcement, "to_dict"):
        enforcement_payload = enforcement.to_dict()  # type: ignore[attr-defined]
        payload["enforcement"] = enforcement_payload
        if enforcement_payload.get("log_path"):
            payload["log_path"] = enforcement_payload["log_path"]
    elif isinstance(enforcement, dict):
        payload["enforcement"] = enforcement

    if warnings:
        warning_messages = [
            w.get("message") or "" for w in warnings if w.get("message")
        ]
        preview = "; ".join(warning_messages[:3])
        if len(warning_messages) > 3:
            preview += f"; … (+{len(warning_messages) - 3} more)"
        print(
            f"Advisory warnings present ({len(warnings)}): {preview}",
            file=sys.stderr,
        )
    if blockers:
        blocker_messages = [
            b.get("message") or "" for b in blockers if b.get("message")
        ]
        preview = "; ".join(blocker_messages[:3]) if blocker_messages else "n/a"
        if len(blocker_messages) > 3:
            preview += f"; … (+{len(blocker_messages) - 3} more)"
        print(
            "Advisory blockers detected (workflow not halted): " f"{preview}",
            file=sys.stderr,
        )

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
