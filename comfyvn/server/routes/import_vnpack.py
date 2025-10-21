"""
FastAPI endpoints for handling VN pack archive uploads (dry-run & extract).
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile

from comfyvn.core.file_importer import FileImporter
from comfyvn.importers.vnpack import find_adapter

router = APIRouter(prefix="/import/vnpack", tags=["Importers"])
_MAX_PREVIEW_FILES = 50
_CHUNK_SIZE = 1 * 1024 * 1024


async def _write_upload(upload: UploadFile, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        await upload.seek(0)
    except Exception:
        pass
    loop = asyncio.get_running_loop()

    def _writer() -> None:
        with dest.open("wb") as handle:
            while True:
                chunk = upload.file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)

    await loop.run_in_executor(None, _writer)
    return dest


def _serialize_paths(paths: Iterable[Path]) -> List[str]:
    return [Path(p).as_posix() for p in paths]


@router.post("/dryrun")
async def import_vnpack_dryrun(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename missing for upload")
    with tempfile.TemporaryDirectory(prefix="vnpack_dryrun_") as tmp_dir:
        tmp_path = Path(tmp_dir) / file.filename
        await _write_upload(file, tmp_path)
        adapter = find_adapter(tmp_path)
        if adapter is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported VN pack extension: {tmp_path.suffix or '<none>'}",
            )
        listing = adapter.list_contents()
        preview = {"scenes": [], "notes": "mapping unavailable"}
        with contextlib.suppress(NotImplementedError):
            with tempfile.TemporaryDirectory(prefix="vnpack_preview_") as extract_dir:
                extract_root = Path(extract_dir)
                adapter.extract(extract_root)
                preview = adapter.map_scene_graph(extract_root)
        return {
            "ok": True,
            "adapter": adapter.__class__.__name__,
            "files": listing[:_MAX_PREVIEW_FILES],
            "preview": preview,
        }


@router.post("/extract")
async def import_vnpack_extract(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename missing for upload")
    importer = FileImporter("vnpack")
    with tempfile.TemporaryDirectory(prefix="vnpack_extract_") as tmp_dir:
        tmp_path = Path(tmp_dir) / file.filename
        await _write_upload(file, tmp_path)
        adapter = find_adapter(tmp_path)
        if adapter is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported VN pack extension: {tmp_path.suffix or '<none>'}",
            )
        session = importer.new_session(tmp_path, metadata={"filename": file.filename})
        adapter_cls = adapter.__class__
        session_adapter = adapter_cls(session.raw_path)
        extracted_paths = _serialize_paths(
            session_adapter.extract(session.extracted_dir)
        )
        preview = session_adapter.map_scene_graph(session.extracted_dir)
        return {
            "ok": True,
            "bundle": {
                "id": session.import_id,
                "raw_path": session.raw_path.as_posix(),
                "extracted_path": session.extracted_dir.as_posix(),
                "converted_path": session.converted_dir.as_posix(),
            },
            "adapter": adapter_cls.__name__,
            "extracted_count": len(extracted_paths),
            "extracted": extracted_paths[:_MAX_PREVIEW_FILES],
            "preview": preview,
        }
