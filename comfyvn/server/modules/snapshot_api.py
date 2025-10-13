# comfyvn/server/modules/snapshot_api.py
# 💾 Snapshot API — list, create, and restore project snapshots
# [Server Core Production Chat | ComfyVN Phase 3.3 Integration Sync]

from __future__ import annotations
import os, time, shutil, zipfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, Body

router = APIRouter(prefix="/snapshot", tags=["Snapshot"])

DATA_DIR = Path("comfyvn/data")
SNAPSHOT_DIR = DATA_DIR / "snapshots"
EXPORTS_DIR = Path("exports")
LOGS_DIR = Path("logs")

for p in [SNAPSHOT_DIR, EXPORTS_DIR, LOGS_DIR]:
    p.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------
def _safe_name(name: str) -> str:
    """Make filesystem-safe snapshot names."""
    return "".join(ch for ch in name if ch.isalnum() or ch in ("_", "-", "."))[:64]


def _snapshot_path(sid: str) -> Path:
    return SNAPSHOT_DIR / f"{sid}.zip"


def _zip_dir(zipf: zipfile.ZipFile, base_path: Path, arc_prefix: str):
    """Add directory recursively to zip under arc_prefix."""
    if not base_path.exists():
        return
    for root, _, files in os.walk(base_path):
        for f in files:
            fp = Path(root) / f
            arc = f"{arc_prefix}/{fp.relative_to(base_path)}"
            zipf.write(fp, arc)


# ------------------------------------------------------------
# List snapshots
# ------------------------------------------------------------
@router.get("/list")
async def snapshot_list():
    snaps = []
    for z in sorted(SNAPSHOT_DIR.glob("*.zip")):
        try:
            stat = z.stat()
            snaps.append(
                {
                    "id": z.stem,
                    "name": z.stem,
                    "size": stat.st_size,
                    "created": int(stat.st_mtime),
                }
            )
        except Exception:
            continue
    return {"ok": True, "snapshots": snaps}


# ------------------------------------------------------------
# Create snapshot
# ------------------------------------------------------------
@router.post("/create")
async def snapshot_create(payload: dict = Body(default_factory=dict)):
    """Create a compressed backup of current project state."""
    name = payload.get("name") or time.strftime("snap_%Y%m%d_%H%M%S")
    include_logs = bool(payload.get("include_logs", True))
    sid = _safe_name(name)
    out = _snapshot_path(sid)
    if out.exists():
        sid = f"{sid}_{int(time.time())}"
        out = _snapshot_path(sid)

    try:
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            _zip_dir(zf, DATA_DIR, "data")
            _zip_dir(zf, EXPORTS_DIR, "exports")
            if include_logs:
                _zip_dir(zf, LOGS_DIR, "logs")
        return {"ok": True, "id": sid, "path": str(out.resolve())}
    except Exception as e:
        raise HTTPException(500, f"Snapshot creation failed: {e}")


# ------------------------------------------------------------
# Restore snapshot (safe mode)
# ------------------------------------------------------------
@router.post("/restore")
async def snapshot_restore(payload: dict = Body(...)):
    """
    Restore snapshot contents into data directories.
    Safe mode: extracts into a temp folder first to avoid disrupting live managers.
    """
    sid = payload.get("snap_id")
    overwrite = bool(payload.get("overwrite", True))
    if not sid:
        raise HTTPException(400, "Missing snap_id")

    src = _snapshot_path(sid)
    if not src.exists():
        raise HTTPException(404, f"Snapshot not found: {sid}")

    temp_dir = SNAPSHOT_DIR / f"tmp_restore_{int(time.time())}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(src, "r") as zf:
            zf.extractall(temp_dir)
            members = zf.namelist()

        # Copy restored data into active directories
        for sub in ["data", "exports", "logs"]:
            extracted = temp_dir / sub
            if extracted.exists():
                target = Path(sub)
                target.mkdir(parents=True, exist_ok=True)
                if overwrite:
                    for root, _, files in os.walk(extracted):
                        for f in files:
                            src_path = Path(root) / f
                            rel_path = src_path.relative_to(extracted)
                            dst_path = target / rel_path
                            dst_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(src_path, dst_path)

        # Cleanup temporary folder
        shutil.rmtree(temp_dir, ignore_errors=True)

        return {"ok": True, "restored": sid, "files": len(members)}

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(500, f"Snapshot restore failed: {e}")

    from comfyvn.server.core.diagnostics import log_diagnostic

    log_diagnostic("Snapshot API", {"snapshot_dir": str(SNAPSHOT_DIR.resolve())})
