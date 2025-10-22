#!/usr/bin/env python3
"""Asset registry enforcement utility.

Ensures every asset row has a corresponding sidecar file and basic metadata.
The tool can run in report-only (dry-run) mode or perform fixes directly.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfyvn.core.db_manager import DEFAULT_DB_PATH
from comfyvn.registry.rebuild import audit_sidecars
from comfyvn.studio.core.asset_registry import AssetRegistry

LOGGER = logging.getLogger("assets_enforcer")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify and optionally fix asset sidecars and metadata."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=None,
        help="Override assets root directory (default: auto-detect).",
    )
    parser.add_argument(
        "--thumbs-dir",
        type=Path,
        default=None,
        help="Override thumbnail cache directory (default: auto-detect).",
    )
    parser.add_argument(
        "--project-id",
        default="default",
        help="Project identifier to operate on (default: default).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report problems; do not write sidecars or metadata fixes.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Rewrite sidecars even if they already exist when fixing.",
    )
    parser.add_argument(
        "--fill-metadata",
        action="store_true",
        help="Populate missing tags/licenses from file paths when fixing.",
    )
    parser.add_argument(
        "--json",
        dest="json_out",
        action="store_true",
        help="Emit the final report as JSON to stdout.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging output for troubleshooting.",
    )
    return parser.parse_args()


def build_registry(args: argparse.Namespace) -> AssetRegistry:
    assets_root = args.assets_dir.expanduser().resolve() if args.assets_dir else None
    thumbs_root = args.thumbs_dir.expanduser().resolve() if args.thumbs_dir else None
    db_path = args.db_path.expanduser().resolve()
    return AssetRegistry(
        db_path=db_path,
        project_id=args.project_id,
        assets_root=assets_root,
        thumb_root=thumbs_root,
    )


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    registry = build_registry(args)
    LOGGER.info(
        "Enforcing asset sidecars (project=%s assets=%s)",
        registry.project_id,
        registry.ASSETS_ROOT,
    )

    report = audit_sidecars(
        registry,
        fix_missing=not args.dry_run,
        overwrite=args.overwrite,
        fill_metadata=not args.dry_run and args.fill_metadata,
    )

    if args.json_out:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        if report.missing_sidecars:
            LOGGER.error(
                "Assets still missing sidecars: %s", ", ".join(report.missing_sidecars)
            )
        else:
            LOGGER.info("All assets have sidecars.")
        if report.repaired_sidecars:
            LOGGER.info(
                "Repaired sidecars for: %s", ", ".join(report.repaired_sidecars)
            )
        if report.metadata_missing:
            for entry in report.metadata_missing:
                LOGGER.warning(
                    "Metadata missing for %s (%s)",
                    entry.get("uid"),
                    ",".join(entry.get("fields", [])),
                )
        else:
            LOGGER.info("All assets contain tags and license metadata.")
        if report.metadata_fixed:
            LOGGER.info("Repaired metadata for: %s", ", ".join(report.metadata_fixed))

    return 0 if not report.missing_sidecars else 1


if __name__ == "__main__":
    sys.exit(main())
