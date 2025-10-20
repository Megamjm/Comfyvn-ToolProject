from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore

from comfyvn.studio.core.asset_registry import AssetRegistry
from comfyvn.studio.core.provenance_registry import ProvenanceRegistry


@pytest.mark.skipif(Image is None, reason="Pillow is required for provenance stamping test")
def test_register_file_records_provenance(tmp_path):
    # Prepare a tiny PNG asset.
    source = tmp_path / "source.png"
    img = Image.new("RGB", (4, 4), color="red")  # type: ignore[attr-defined]
    img.save(source)  # type: ignore[attr-defined]

    db_path = tmp_path / "db.sqlite"
    registry = AssetRegistry(db_path=db_path)
    # Redirect storage roots into the temporary directory.
    registry.ASSETS_ROOT = tmp_path / "assets"
    registry.META_ROOT = registry.ASSETS_ROOT / "_meta"
    registry.THUMB_ROOT = tmp_path / "thumbs"
    registry.ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
    registry.META_ROOT.mkdir(parents=True, exist_ok=True)
    registry.THUMB_ROOT.mkdir(parents=True, exist_ok=True)

    provenance_payload = {
        "source": "test-suite",
        "inputs": {"case": "provenance", "step": 1},
        "user_id": "pytest",
    }
    asset = registry.register_file(
        source,
        "tests",
        metadata={"origin": "unit"},
        provenance=provenance_payload,
        license_tag="CC-BY-4.0",
    )

    assert asset["provenance"] is not None
    prov_record = asset["provenance"]
    assert prov_record["source"] == "test-suite"
    assert prov_record["inputs"]["case"] == "provenance"
    assert asset["meta"]["license"] == "CC-BY-4.0"

    # Sidecar should include provenance payload.
    sidecar_path = (registry.META_ROOT / Path(asset["path"])).with_suffix(".json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["provenance"]["id"] == prov_record["id"]

    # Registry query returns the same provenance entry.
    prov_registry = ProvenanceRegistry(db_path=db_path)
    rows = prov_registry.list_for_asset_uid(asset["uid"])
    assert len(rows) == 1
    assert rows[0]["id"] == prov_record["id"]

    # PNG metadata should carry the provenance marker.
    saved_path = registry.ASSETS_ROOT / asset["path"]
    with Image.open(saved_path) as stamped:  # type: ignore[attr-defined]
        text_items = getattr(stamped, "text", {}) or {}
        marker = text_items.get("comfyvn_provenance")
    assert marker is not None
