# comfyvn/modules/core/snapshot_manager.py
# ⚙️ 3. Server Core Production Chat — Snapshot Manager (v2.7b)
# Purpose: Create, list, verify, and restore project snapshots for /comfyvn/data, /exports, /logs.
# Notes: Uses bootstrap defaults and integrity checks; safe, offline, local only.
# [Server Core Production Chat]

from __future__ import annotations
import os, io, json, tarfile, time, hashlib, shutil
from typing import Dict, Any, List, Optional, Tuple

ROOT_DIR = "./"
DATA_DIR = "./comfyvn/data"
EXPORTS_DIR = "./exports"
LOGS_DIR = "./logs"
SNAP_DIR = "./comfyvn/snapshots"
MANIFEST = "manifest.json"
ARCHIVE = "payload.tar.gz"


# ---------- hashing ----------
def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk_files(base: str) -> List[str]:
    out: List[str] = []
    for root, _, files in os.walk(base):
        for fn in files:
            full = os.path.join(root, fn)
            out.append(os.path.normpath(full))
    return out


def _relpath(path: str) -> str:
    return os.path.normpath(os.path.relpath(path, ROOT_DIR))


# ---------- manifest ----------
def _build_manifest(paths: List[str]) -> Dict[str, Any]:
    files: List[str] = []
    for p in paths:
        if not os.path.exists(p):  # skip missing roots
            continue
        if os.path.isfile(p):
            files.append(os.path.normpath(p))
        else:
            files.extend(_walk_files(p))

    items: Dict[str, Dict[str, Any]] = {}
    total_size = 0
    for f in files:
        try:
            size = os.path.getsize(f)
            h = _hash_file(f)
            items[_relpath(f)] = {"sha256": h, "size": size}
            total_size += size
        except Exception:
            # skip unreadable files
            continue

    return {
        "schema_version": "1.0.0",
        "created": int(time.time()),
        "roots": [_relpath(p) for p in paths if os.path.exists(p)],
        "files": items,
        "count": len(items),
        "size": total_size,
    }


# ---------- archive ----------
def _write_archive(
    archive_path: str, roots: List[str], manifest: Dict[str, Any]
) -> None:
    os.makedirs(os.path.dirname(archive_path), exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as tar:
        # add roots (skip missing)
        for root in roots:
            if not os.path.exists(root):
                continue
            arcname = _relpath(root)
            tar.add(root, arcname=arcname)
        # add manifest json as a member
        man_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        info = tarfile.TarInfo(name=MANIFEST)
        info.size = len(man_bytes)
        info.mtime = manifest.get("created", int(time.time()))
        tar.addfile(info, io.BytesIO(man_bytes))


def _read_manifest_from_archive(archive_path: str) -> Dict[str, Any]:
    with tarfile.open(archive_path, "r:gz") as tar:
        member = tar.getmember(MANIFEST)
        f = tar.extractfile(member)
        if not f:
            return {}
        return json.loads(f.read().decode("utf-8"))


# ---------- public API ----------
def ensure_dirs() -> None:
    os.makedirs(SNAP_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)


def create_snapshot(
    name: Optional[str] = None, include_logs: bool = True
) -> Dict[str, Any]:
    """
    Create a compressed snapshot containing:
      - comfyvn/data
      - exports
      - logs (optional)
    Returns snapshot metadata.
    """
    ensure_dirs()
    ts = time.strftime("%Y%m%d_%H%M%S")
    snap_id = name or f"snap_{ts}"
    snap_dir = os.path.join(SNAP_DIR, snap_id)
    os.makedirs(snap_dir, exist_ok=True)

    roots = [DATA_DIR, EXPORTS_DIR]
    if include_logs:
        roots.append(LOGS_DIR)

    manifest = _build_manifest(roots)
    archive_path = os.path.join(snap_dir, ARCHIVE)
    _write_archive(archive_path, roots, manifest)

    meta = {
        "id": snap_id,
        "created": manifest["created"],
        "archive": os.path.relpath(archive_path, ROOT_DIR),
        "count": manifest["count"],
        "size": manifest["size"],
        "include_logs": include_logs,
    }
    with open(os.path.join(snap_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return meta  # [Server Core Production Chat]


def list_snapshots() -> List[Dict[str, Any]]:
    ensure_dirs()
    out: List[Dict[str, Any]] = []
    for entry in sorted(os.listdir(SNAP_DIR)):
        sdir = os.path.join(SNAP_DIR, entry)
        if not os.path.isdir(sdir):
            continue
        meta_path = os.path.join(sdir, "meta.json")
        archive_path = os.path.join(sdir, ARCHIVE)
        if not os.path.exists(archive_path):
            continue
        meta: Dict[str, Any] = {
            "id": entry,
            "archive": os.path.relpath(archive_path, ROOT_DIR),
        }
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta.update(json.load(f))
            except Exception:
                pass
        out.append(meta)
    # newest first
    out.sort(key=lambda m: m.get("created", 0), reverse=True)
    return out  # [Server Core Production Chat]


def verify_snapshot(snap_id: str) -> Dict[str, Any]:
    """
    Verify snapshot archive integrity: checks manifest presence and gzip/tar readability.
    """
    sdir = os.path.join(SNAP_DIR, snap_id)
    archive_path = os.path.join(sdir, ARCHIVE)
    if not os.path.exists(archive_path):
        return {"ok": False, "error": "not_found"}
    try:
        manifest = _read_manifest_from_archive(archive_path)
        ok = bool(manifest and manifest.get("files"))
        return {"ok": ok, "manifest": manifest}
    except Exception as e:
        return {"ok": False, "error": str(e)}  # [Server Core Production Chat]


def restore_snapshot(
    snap_id: str, targets: Optional[List[str]] = None, overwrite: bool = True
) -> Dict[str, Any]:
    """
    Restore selected roots from the snapshot archive back into the working tree.
    targets: list of root names to restore, e.g. ["comfyvn/data","exports","logs"]
             defaults to all recorded roots.
    """
    sdir = os.path.join(SNAP_DIR, snap_id)
    archive_path = os.path.join(sdir, ARCHIVE)
    if not os.path.exists(archive_path):
        return {"ok": False, "error": "not_found"}

    ensure_dirs()
    restored: List[str] = []
    with tarfile.open(archive_path, "r:gz") as tar:
        # read manifest to decide what to restore
        man = _read_manifest_from_archive(archive_path)
        roots = man.get("roots", [])
        if targets:
            # normalize incoming
            targets_norm = [os.path.normpath(t) for t in targets]
            roots = [r for r in roots if os.path.normpath(r) in targets_norm]

        # extract only selected roots
        for member in tar.getmembers():
            name = member.name
            top = name.split("/")[0] if "/" in name else name
            # allow manifest always
            if name == MANIFEST:
                continue
            # only extract files under chosen roots
            if not any(name == r or name.startswith(r + "/") for r in roots):
                continue
            # extraction with overwrite guard
            dest_path = os.path.join(ROOT_DIR, name)
            if member.isdir():
                os.makedirs(dest_path, exist_ok=True)
                continue
            if (not overwrite) and os.path.exists(dest_path):
                continue
            # ensure parent
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            f = tar.extractfile(member)
            if f:
                with open(dest_path, "wb") as out:
                    shutil.copyfileobj(f, out)
        restored = roots

    return {"ok": True, "restored": restored}  # [Server Core Production Chat]
