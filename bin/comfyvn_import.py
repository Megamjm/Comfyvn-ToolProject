#!/usr/bin/env python3
"""Command-line importer helper for ComfyVN."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from comfyvn.importers import ALL_IMPORTERS, get_importer


def _load_hooks(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - CLI helper
        print(f"[warn] failed to read hooks file ({exc})", file=sys.stderr)
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect and import VN directories into comfyvn-pack")
    parser.add_argument("root", help="Path to the VN directory or archive staging folder")
    parser.add_argument("--out", default="comfyvn_pack", help="Destination directory for the comfyvn-pack (default: ./comfyvn_pack)")
    parser.add_argument("--hooks", default=None, help="Optional JSON file describing external tool hooks (paths to unrpa, arc_unpacker, etc.)")
    parser.add_argument("--engine", default=None, help="Force a specific importer id (e.g., renpy, kirikiri)")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        print(f"[error] root path does not exist: {root}", file=sys.stderr)
        return 2

    hooks = _load_hooks(Path(args.hooks).expanduser()) if args.hooks else {}

    detections = []
    for importer in ALL_IMPORTERS:
        detections.append(importer.detect(root))

    detections.sort(key=lambda d: d.confidence, reverse=True)

    def _importer_from_detection(name: str):
        name_l = name.lower()
        for importer in ALL_IMPORTERS:
            if importer.label.lower() == name_l or importer.id.lower() == name_l:
                return importer
        return None

    chosen = None
    if args.engine:
        try:
            chosen = get_importer(args.engine)
        except KeyError:
            print(f"[error] unknown importer id: {args.engine}", file=sys.stderr)
            return 3
    else:
        chosen = _importer_from_detection(detections[0].engine) if detections else None
        if not chosen and detections:
            chosen = _importer_from_detection(detections[0].engine.split("/")[0])
        if not chosen:
            # fall back to renpy as a default if nothing detected
            chosen = get_importer("renpy")

    print("[detect]")
    for det in detections:
        print(f" - {det.engine:<20} confidence={det.confidence:.2f} reasons={det.reasons}")
    print(f"[chosen] importer={chosen.id} ({chosen.label})")

    plan = chosen.plan(root)
    print("[plan]")
    for step in plan.steps:
        print(f" - {step}")
    if plan.warnings:
        print("[warnings]")
        for warn in plan.warnings:
            print(f" ! {warn}")

    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    pack_path = chosen.import_pack(root, out, hooks=hooks)
    print(f"[done] comfyvn-pack created at {pack_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
