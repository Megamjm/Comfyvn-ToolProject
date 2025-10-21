"""
Asset manifest builder for ComfyVN.

Scans the assets directory, records metadata, optional sidecar info,
and writes a manifest JSON for downstream tools.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
from typing import Any, Dict, Iterable, Optional, Tuple

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover - Pillow optional
    Image = None  # type: ignore

ASSETS_ROOT_DEFAULT = "assets"
META_ROOT_NAME = "_meta"
MANIFEST_NAME = "assets.manifest.json"


def _sha256(path: pathlib.Path, bufsize: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(bufsize)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _probe_image(path: pathlib.Path) -> Tuple[Optional[int], Optional[int]]:
    if Image is None:
        return None, None
    try:
        with Image.open(path) as img:  # type: ignore[attr-defined]
            width, height = img.size
            return width, height
    except Exception:
        return None, None


def _load_sidecar(relpath: str, assets_root: pathlib.Path) -> Dict[str, Any]:
    base = assets_root / relpath
    candidates = [
        base.with_suffix(base.suffix + ".asset.json"),
        base.with_suffix(base.suffix + ".json"),
        assets_root / META_ROOT_NAME / f"{relpath}.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                return {}
    return {}


def _categorize(relpath: str) -> Dict[str, Any]:
    parts = pathlib.Path(relpath).parts
    data: Dict[str, Any] = {"category": "other"}
    try:
        idx = parts.index("characters")
        if len(parts) >= idx + 3:
            data["category"] = "character"
            data["character"] = parts[idx + 1]
            data["expression"] = pathlib.Path(parts[idx + 2]).stem
            return data
    except ValueError:
        pass
    try:
        idx = parts.index("bg")
        if len(parts) >= idx + 2:
            data["category"] = "background"
            data["bg_name"] = pathlib.Path(parts[idx + 1]).stem
            return data
    except ValueError:
        pass
    return data


def _iter_asset_files(root: pathlib.Path) -> Iterable[pathlib.Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".png", ".webp"}:
            yield path


def build_manifest(
    assets_root: str = ASSETS_ROOT_DEFAULT,
    manifest_path: Optional[str] = None,
) -> Dict[str, Any]:
    root = pathlib.Path(assets_root)
    root.mkdir(parents=True, exist_ok=True)
    files = []
    for file_path in _iter_asset_files(root):
        rel = file_path.relative_to(root).as_posix()
        stat = file_path.stat()
        width, height = _probe_image(file_path)
        sidecar = _load_sidecar(rel, root)
        record: Dict[str, Any] = {
            "relpath": rel,
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
            "hash": _sha256(file_path),
            "width": width,
            "height": height,
        }
        record.update(_categorize(rel))
        if sidecar:
            record["seed"] = sidecar.get("seed")
            record["workflow_hash"] = sidecar.get("workflow_hash")
            record["workflow_id"] = sidecar.get("workflow_id")
            if "extras" in sidecar:
                record["extras"] = sidecar["extras"]
        files.append(record)

    manifest: Dict[str, Any] = {
        "version": "1.0",
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "assets_root": root.as_posix(),
        "count": len(files),
        "files": files,
        "by_character": {},
        "by_background": {},
    }

    for record in files:
        if record.get("category") == "character":
            character = record.get("character")
            expression = record.get("expression")
            if character and expression:
                manifest["by_character"].setdefault(character, {})[expression] = record["relpath"]
        if record.get("category") == "background":
            background = record.get("bg_name")
            if background:
                manifest["by_background"][background] = record["relpath"]

    output_path = (
        root / MANIFEST_NAME if manifest_path is None else pathlib.Path(manifest_path)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="ComfyVN asset manifest builder.")
    parser.add_argument("--assets", default=ASSETS_ROOT_DEFAULT, help="Assets root folder.")
    parser.add_argument(
        "--out",
        default=None,
        help="Manifest output path (default: assets/assets.manifest.json).",
    )
    args = parser.parse_args()
    manifest = build_manifest(args.assets, args.out)
    target = args.out or (pathlib.Path(args.assets) / MANIFEST_NAME)
    print(f"[A3] wrote manifest with {manifest['count']} files -> {target}")


if __name__ == "__main__":
    main()
