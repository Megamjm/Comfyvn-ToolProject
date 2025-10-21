import hashlib
import json
import os
import time
import zipfile
from pathlib import Path

from PySide6.QtGui import QAction

from comfyvn.core.provenance import stamp_path


def trace_metadata(asset_path: Path):
    data = Path(asset_path).read_bytes()
    h = hashlib.sha256(data).hexdigest()[:16]
    return {"file": asset_path.name, "hash": h, "timestamp": time.time()}


def bundle_scene(scene_json: dict, assets: list[str], outdir="exports"):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    bundle = {"scene": scene_json, "assets": []}
    zipname = outdir / f"bundle_{int(time.time())}.zip"
    with zipfile.ZipFile(zipname, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("scene.json", json.dumps(scene_json, indent=2))
        for a in assets:
            p = Path(a)
            if p.exists():
                z.write(p, p.name)
                bundle["assets"].append(trace_metadata(p))
    provenance = stamp_path(
        zipname,
        source="core.bundler.bundle_scene",
        inputs={
            "scene_title": scene_json.get("title"),
            "asset_count": len(bundle["assets"]),
        },
        findings=bundle.get("issues") or [],
    )
    bundle["provenance"] = provenance
    meta = zipname.with_suffix(".meta.json")
    meta.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(zipname), "meta": str(meta)}
