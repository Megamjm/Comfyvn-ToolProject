#!/usr/bin/env python3
"""
Regenerate `comfyvn/providers/nodeset.lock.json` based on the current custom node checkouts.

The script reads the canonical provider template (node packs + repos), attempts to locate a
local checkout for each pack, and pins the commit hash. When a pack is missing the script
marks the commit as `"000…"` so follow-up automation can alert the operator.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from comfyvn.providers import (NODESET_LOCK_PATH, PROVIDERS_PATH,
                               load_providers_template)


@dataclass
class NodePack:
    name: str
    repo: str
    category: Iterable[str]
    commit: Optional[str] = None


def _detect_commit(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        commit = result.stdout.strip()
        return commit or None
    except Exception:
        return None


def _find_candidate_dirs(root: Path, slug: str) -> List[Path]:
    candidates = [
        root / slug,
        root / f"ComfyUI-{slug}",
        root / slug.replace("ComfyUI-", ""),
    ]
    unique: List[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _gather_packs(search_roots: List[Path], providers_path: Path) -> List[NodePack]:
    catalog = load_providers_template(providers_path)
    packs: List[NodePack] = []

    for pack_id, info in sorted(catalog.node_packs.items()):
        repo = str(info.get("repo") or "")
        slug = repo.split("/")[-1] if repo else pack_id
        commit = info.get("commit") or None
        for root in search_roots:
            for candidate in _find_candidate_dirs(root, slug):
                detected = _detect_commit(candidate)
                if detected:
                    commit = detected
                    break
            if commit:
                break
        packs.append(
            NodePack(
                name=repo.split("/")[-1] if repo else pack_id,
                repo=repo,
                category=info.get("category") or [],
                commit=commit,
            )
        )
    return packs


def _write_lock(path: Path, packs: List[NodePack]) -> None:
    payload: Dict[str, object] = {}
    payload["generated"] = (
        __import__("datetime").datetime.utcnow().replace(microsecond=0).isoformat()
        + "Z"
    )
    payload["packs"] = [
        {
            "name": pack.name,
            "repo": pack.repo,
            "commit": pack.commit or "0000000000000000000000000000000000000000",
            "category": list(pack.category),
        }
        for pack in packs
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate nodeset.lock.json from local checkouts."
    )
    parser.add_argument(
        "--search-root",
        action="append",
        default=[
            "custom_nodes",
            "extensions",
            "ComfyUI/custom_nodes",
        ],
        help="Directory to search for node pack repositories (can be repeated).",
    )
    parser.add_argument(
        "--providers",
        type=Path,
        default=PROVIDERS_PATH,
        help="Path to providers.json template.",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=NODESET_LOCK_PATH,
        help="Destination path for nodeset.lock.json.",
    )
    args = parser.parse_args()

    search_roots = [Path(root).expanduser() for root in args.search_root]
    packs = _gather_packs(search_roots, args.providers)
    _write_lock(args.lock, packs)
    print(f"Wrote {args.lock} ({len(packs)} packs)")


if __name__ == "__main__":
    main()
