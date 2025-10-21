#!/usr/bin/env python3
"""
Rebuild the hash-based deduplication cache from an assets directory.

Example:
    python scripts/rebuild_dedup_cache.py --assets ./assets
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfyvn.cache.cache_manager import CacheManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild the deduplication cache index from on-disk assets."
    )
    parser.add_argument(
        "--assets",
        default="assets",
        help="Assets root to scan (default: ./assets).",
    )
    parser.add_argument(
        "--index",
        default=None,
        help="Override cache index path (default: runtime cache/dedup/dedup_cache.json).",
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=None,
        help="Optional limit on the number of cached blobs.",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=None,
        help="Optional limit on the aggregate bytes tracked in the cache.",
    )
    parser.add_argument(
        "--no-preserve-pins",
        action="store_true",
        help="Do not keep existing pinned paths.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s"
    )

    assets_root = Path(args.assets).expanduser().resolve()
    if not assets_root.exists():
        raise SystemExit(f"Assets path {assets_root} does not exist.")

    index_path = Path(args.index).expanduser().resolve() if args.index else None

    manager = CacheManager(
        index_path=index_path,
        max_entries=args.max_entries,
        max_bytes=args.max_bytes,
    )

    files = CacheManager.iter_asset_files(assets_root)
    summary = manager.rebuild_from_files(
        files,
        preserve_pins=not args.no_preserve_pins,
    )

    unique_entries = sum(1 for _ in manager.iter_entries())
    pinned_count = len(manager.pinned_paths())

    logging.info("Dedup cache index rebuilt at %s", manager.index_path)
    logging.info(
        "Processed %s files (%s duplicates, %s skipped).",
        summary["processed"],
        summary["duplicates"],
        summary["skipped"],
    )
    logging.info(
        "Unique blobs tracked: %s (pinned paths: %s)",
        unique_entries,
        pinned_count,
    )


if __name__ == "__main__":
    main()
