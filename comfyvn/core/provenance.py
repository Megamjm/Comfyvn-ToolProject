from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

LOGGER = logging.getLogger("comfyvn.provenance")


def _safe_path(path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = candidate.resolve()
    return candidate


def hash_file(path: Path | str, *, chunk_size: int = 1 << 20) -> Optional[str]:
    """Return the SHA256 digest for ``path`` or ``None`` when the file is missing."""
    file_path = Path(path)
    if not file_path.exists():
        LOGGER.warning("Provenance hash skipped; file missing: %s", file_path)
        return None

    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ProvenanceStamp:
    target: str
    source: str
    workflow_hash: Optional[str]
    timestamp: float = field(default_factory=lambda: time.time())
    stamp_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    inputs: Dict[str, Any] = field(default_factory=dict)
    findings: Iterable[Dict[str, Any]] = field(default_factory=list)
    user_id: Optional[str] = None
    file_hash: Optional[str] = None
    embedded: bool = False
    sidecar_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.stamp_id,
            "target": self.target,
            "source": self.source,
            "workflow_hash": self.workflow_hash,
            "timestamp": self.timestamp,
            "inputs": dict(self.inputs),
            "findings": list(self.findings),
            "user_id": self.user_id,
            "file_hash": self.file_hash,
            "embedded": self.embedded,
            "sidecar_path": self.sidecar_path,
        }


def build_stamp_payload(
    path: Path | str,
    *,
    source: str,
    inputs: Optional[Dict[str, Any]] = None,
    findings: Optional[Iterable[Dict[str, Any]]] = None,
    workflow_hash: Optional[str] = None,
    user_id: Optional[str] = None,
    include_hash: bool = True,
) -> ProvenanceStamp:
    file_path = _safe_path(path)
    digest = hash_file(file_path) if include_hash else None
    payload = ProvenanceStamp(
        target=file_path.as_posix(),
        source=source,
        workflow_hash=workflow_hash,
        inputs=dict(inputs or {}),
        findings=list(findings or []),
        user_id=user_id,
        file_hash=digest,
    )
    LOGGER.debug(
        "Built provenance stamp target=%s source=%s", payload.target, payload.source
    )
    return payload


def _write_sidecar(path: Path, stamp: ProvenanceStamp) -> Path:
    sidecar = path.with_suffix(path.suffix + ".prov.json")
    data = {"provenance": stamp.to_dict()}
    sidecar.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    LOGGER.debug("Wrote provenance sidecar %s", sidecar)
    return sidecar


def _embed_png_text(path: Path, stamp: ProvenanceStamp) -> bool:
    try:
        from PIL import Image, PngImagePlugin  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        LOGGER.debug("Pillow unavailable; skipping PNG provenance embed for %s", path)
        return False

    try:
        with Image.open(path) as image:
            info = PngImagePlugin.PngInfo()
            for key, value in image.info.items():
                if isinstance(value, bytes):
                    try:
                        info.add_text(key, value.decode("utf-8", errors="ignore"))
                    except Exception:  # pragma: no cover - defensive
                        continue
                elif isinstance(value, str):
                    info.add_text(key, value)
            info.add_text(
                "comfyvn_provenance", json.dumps(stamp.to_dict(), ensure_ascii=False)
            )
            image.save(path, pnginfo=info)
        LOGGER.debug("Embedded PNG provenance marker into %s", path)
        return True
    except Exception:  # pragma: no cover - defensive
        LOGGER.warning("Failed to embed PNG provenance for %s", path, exc_info=True)
        return False


def _embed_jpeg_comment(path: Path, stamp: ProvenanceStamp) -> bool:
    try:
        from PIL import Image  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        LOGGER.debug("Pillow unavailable; skipping JPEG provenance embed for %s", path)
        return False

    try:
        with Image.open(path) as image:
            comment = json.dumps(stamp.to_dict(), ensure_ascii=False).encode("utf-8")
            image.save(path, comment=comment)
        LOGGER.debug("Embedded JPEG provenance marker into %s", path)
        return True
    except Exception:  # pragma: no cover - defensive
        LOGGER.warning("Failed to embed JPEG provenance for %s", path, exc_info=True)
        return False


def embed_provenance(path: Path | str, stamp: ProvenanceStamp) -> bool:
    """Best-effort embed of provenance metadata into image files."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".png":
        return _embed_png_text(file_path, stamp)
    if suffix in {".jpg", ".jpeg"}:
        return _embed_jpeg_comment(file_path, stamp)
    LOGGER.debug("No provenance embed strategy for %s", file_path)
    return False


def stamp_path(
    path: Path | str,
    *,
    source: str,
    inputs: Optional[Dict[str, Any]] = None,
    findings: Optional[Iterable[Dict[str, Any]]] = None,
    workflow_hash: Optional[str] = None,
    user_id: Optional[str] = None,
    embed: bool = True,
) -> Dict[str, Any]:
    file_path = _safe_path(path)
    stamp = build_stamp_payload(
        file_path,
        source=source,
        inputs=inputs,
        findings=findings,
        workflow_hash=workflow_hash,
        user_id=user_id,
    )
    try:
        sidecar = _write_sidecar(file_path, stamp)
        embedded = embed_provenance(file_path, stamp) if embed else False
    except Exception:  # pragma: no cover - defensive
        LOGGER.warning("Provenance stamping failed for %s", file_path, exc_info=True)
        sidecar = None
        embedded = False

    result = stamp.to_dict()
    result["embedded"] = embedded
    result["sidecar_path"] = sidecar.as_posix() if sidecar else None
    return result


__all__ = [
    "ProvenanceStamp",
    "build_stamp_payload",
    "embed_provenance",
    "hash_file",
    "stamp_path",
]
