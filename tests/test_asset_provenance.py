from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore

from comfyvn.studio.core import asset_registry as asset_registry_module
from comfyvn.studio.core.asset_registry import AssetRegistry, PROVENANCE_TAG
from comfyvn.studio.core.provenance_registry import ProvenanceRegistry


@pytest.mark.skipif(Image is None, reason="Pillow is required for provenance stamping test")
def test_register_file_records_provenance(tmp_path):
    # Prepare a tiny PNG asset.
    source = tmp_path / "source.png"
    img = Image.new("RGB", (4, 4), color="red")  # type: ignore[attr-defined]
    img.save(source)  # type: ignore[attr-defined]

    db_path = tmp_path / "db.sqlite"
    assets_root = tmp_path / "assets"
    thumbs_root = tmp_path / "thumbs"
    meta_root = tmp_path / "assets_meta"
    registry = AssetRegistry(
        db_path=db_path,
        assets_root=assets_root,
        thumb_root=thumbs_root,
        meta_root=meta_root,
    )

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
    sidecar_path = registry.ASSETS_ROOT / asset["sidecar"]
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
    AssetRegistry.wait_for_thumbnails(timeout=5.0)


@pytest.mark.skipif(Image is None, reason="Pillow is required for thumbnail regression test")
def test_thumbnail_registration_wait(tmp_path):
    assets_root = tmp_path / "assets"
    thumbs_root = tmp_path / "thumbs"
    meta_root = assets_root / "_meta"

    db_path = tmp_path / "db.sqlite"
    registry = AssetRegistry(
        db_path=db_path,
        assets_root=assets_root,
        thumb_root=thumbs_root,
        meta_root=meta_root,
    )

    source = tmp_path / "sample.png"
    img = Image.new("RGB", (32, 32), color="blue")  # type: ignore[attr-defined]
    img.save(source)  # type: ignore[attr-defined]

    asset = registry.register_file(source, "tests")
    assert asset["thumb"] is not None

    completed = AssetRegistry.wait_for_thumbnails(timeout=5.0)
    assert completed is True

    thumb_path = thumbs_root / Path(asset["thumb"]).name
    assert thumb_path.exists()


def test_stamp_mp3_with_mutagen_stubs(monkeypatch, tmp_path):
    dest = tmp_path / "track.mp3"
    dest.write_bytes(b"fake-mp3")

    class FakeID3NoHeaderError(Exception):
        pass

    class FakeTags:
        def __init__(self):
            self.del_keys = []
            self.added = []
            self.saved = None

        def delall(self, key):
            self.del_keys.append(key)

        def add(self, frame):
            self.added.append(frame)

        def save(self, path=None):
            self.saved = path

    class FakeID3:
        def __init__(self):
            self.calls = 0
            self.instances: list[FakeTags] = []

        def __call__(self, path=None):
            self.calls += 1
            if self.calls == 1:
                raise FakeID3NoHeaderError()
            tags = FakeTags()
            self.instances.append(tags)
            return tags

    class FakeTXXX:
        def __init__(self, encoding, desc, text):
            self.encoding = encoding
            self.desc = desc
            self.text = text

    monkeypatch.setattr(asset_registry_module, "MP3", object(), raising=False)
    fake_id3 = FakeID3()
    monkeypatch.setattr(asset_registry_module, "ID3", fake_id3, raising=False)
    monkeypatch.setattr(asset_registry_module, "ID3NoHeaderError", FakeID3NoHeaderError, raising=False)
    monkeypatch.setattr(asset_registry_module, "TXXX", FakeTXXX, raising=False)

    AssetRegistry._stamp_mp3(dest, '{"marker": true}')

    assert fake_id3.calls == 2
    tags = fake_id3.instances[0]
    assert tags.del_keys == [f"TXXX:{PROVENANCE_TAG}"]
    assert tags.added[0].desc == PROVENANCE_TAG
    assert tags.added[0].text == ['{"marker": true}']
    assert tags.saved == dest


def test_stamp_ogg_with_mutagen_stubs(monkeypatch, tmp_path):
    dest = tmp_path / "track.ogg"
    dest.write_bytes(b"fake-ogg")

    created = []

    class FakeOgg:
        def __init__(self, path):
            self.path = path
            self.data = {}
            self.saved = False
            created.append(self)

        def __setitem__(self, key, value):
            self.data[key] = value

        def save(self):
            self.saved = True

    monkeypatch.setattr(asset_registry_module, "OggVorbis", FakeOgg, raising=False)

    AssetRegistry._stamp_ogg(dest, "marker-ogg")

    audio = created[0]
    assert audio.data[PROVENANCE_TAG] == ["marker-ogg"]
    assert audio.saved is True


def test_stamp_flac_with_mutagen_stubs(monkeypatch, tmp_path):
    dest = tmp_path / "track.flac"
    dest.write_bytes(b"fake-flac")

    created = []

    class FakeFlac:
        def __init__(self, path):
            self.path = path
            self.data = {}
            self.saved = False
            created.append(self)

        def __setitem__(self, key, value):
            self.data[key] = value

        def save(self):
            self.saved = True

    monkeypatch.setattr(asset_registry_module, "FLAC", FakeFlac, raising=False)

    AssetRegistry._stamp_flac(dest, "marker-flac")

    audio = created[0]
    assert audio.data[PROVENANCE_TAG] == ["marker-flac"]
    assert audio.saved is True


def test_stamp_wav_with_mutagen_stubs(monkeypatch, tmp_path):
    dest = tmp_path / "track.wav"
    dest.write_bytes(b"fake-wav")

    class FakeTags:
        def __init__(self):
            self.del_keys = []
            self.added = []

        def delall(self, key):
            self.del_keys.append(key)

        def add(self, frame):
            self.added.append(frame)

    class FakeTXXX:
        def __init__(self, encoding, desc, text):
            self.encoding = encoding
            self.desc = desc
            self.text = text

    created = []

    class FakeWav:
        def __init__(self, path):
            self.path = path
            self.tags = None
            self.saved = False
            created.append(self)

        def add_tags(self):
            self.tags = FakeTags()

        def save(self):
            self.saved = True

    monkeypatch.setattr(asset_registry_module, "WAVE", FakeWav, raising=False)
    monkeypatch.setattr(asset_registry_module, "TXXX", FakeTXXX, raising=False)

    AssetRegistry._stamp_wav(dest, "marker-wav")

    audio = created[0]
    assert isinstance(audio.tags, FakeTags)
    assert audio.tags.del_keys[-1] == f"TXXX:{PROVENANCE_TAG}"
    assert audio.tags.added[-1].desc == PROVENANCE_TAG
    assert audio.tags.added[-1].text == ["marker-wav"]
    assert audio.saved is True
