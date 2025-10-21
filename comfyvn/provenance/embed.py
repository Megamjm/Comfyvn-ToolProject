from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

LOGGER = logging.getLogger("comfyvn.provenance")


def embed_png(
    path: str | Path, meta: Mapping[str, Any] | Iterable[tuple[str, Any]]
) -> bool:
    """
    Embed ``meta`` into the PNG located at ``path`` using tEXt chunks.

    Returns ``True`` when the embed succeeds. When Pillow is unavailable or the
    file cannot be processed, the function returns ``False`` while still writing
    the JSON sidecar next to the asset.
    """
    file_path = Path(path)
    metadata = _normalize_meta(meta)
    _write_sidecar(file_path, metadata)

    try:
        from PIL import Image, PngImagePlugin  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        LOGGER.debug("Pillow unavailable; skipping PNG embed for %s", file_path)
        return False

    if not file_path.exists():
        LOGGER.warning("PNG asset missing; cannot embed provenance: %s", file_path)
        return False

    if not metadata:
        LOGGER.debug("No metadata provided; PNG embed not required for %s", file_path)
        return False

    try:
        with Image.open(file_path) as image:
            png_info = PngImagePlugin.PngInfo()
            existing = image.info or {}
            for key, value in existing.items():
                if isinstance(value, bytes):
                    try:
                        decoded = value.decode("utf-8")
                    except UnicodeDecodeError:
                        decoded = value.decode("latin-1", errors="ignore")
                    png_info.add_text(key, decoded)
                elif isinstance(value, str):
                    png_info.add_text(key, value)

            for key, value in metadata.items():
                png_info.add_text(key, _stringify(value))

            save_kwargs: Dict[str, Any] = {}
            if "icc_profile" in existing:
                save_kwargs["icc_profile"] = existing["icc_profile"]
            if "dpi" in existing:
                save_kwargs["dpi"] = existing["dpi"]
            image.save(file_path, pnginfo=png_info, **save_kwargs)
        LOGGER.debug("Embedded PNG provenance for %s", file_path)
        return True
    except Exception:  # pragma: no cover - defensive
        LOGGER.warning(
            "Failed to embed PNG provenance for %s", file_path, exc_info=True
        )
        return False


def embed_wav(
    path: str | Path, meta: Mapping[str, Any] | Iterable[tuple[str, Any]]
) -> bool:
    """
    Embed ``meta`` into the WAV located at ``path`` using a LIST/INFO chunk.

    Returns ``True`` when the embed succeeds. When the WAV file is missing or
    cannot be updated, the function returns ``False`` while still writing the
    JSON sidecar next to the asset.
    """
    file_path = Path(path)
    metadata = _normalize_meta(meta)
    _write_sidecar(file_path, metadata)

    if not file_path.exists():
        LOGGER.warning("WAV asset missing; cannot embed provenance: %s", file_path)
        return False

    if not metadata:
        LOGGER.debug("No metadata provided; WAV embed not required for %s", file_path)
        return False

    try:
        contents = bytearray(file_path.read_bytes())
    except Exception:  # pragma: no cover - defensive
        LOGGER.warning("Unable to read WAV asset for provenance embed: %s", file_path)
        return False

    try:
        if not _rewrite_info_list(contents, metadata):
            return False
        file_path.write_bytes(contents)
        LOGGER.debug("Embedded WAV provenance for %s", file_path)
        return True
    except Exception:  # pragma: no cover - defensive
        LOGGER.warning(
            "Failed to embed WAV provenance for %s", file_path, exc_info=True
        )
        return False


def _rewrite_info_list(contents: bytearray, metadata: Dict[str, Any]) -> bool:
    if len(contents) < 12 or contents[0:4] != b"RIFF" or contents[8:12] != b"WAVE":
        LOGGER.warning("File is not a RIFF/WAVE asset; provenance embed skipped")
        return False

    info_chunk = _build_info_chunk(metadata)
    if not info_chunk:
        return False

    existing = _locate_list_info(contents)
    info_chunk_bytes = bytearray(info_chunk)
    if existing is not None:
        start, end = existing
        contents[start:end] = info_chunk_bytes
    else:
        insert_at = _locate_data_chunk_start(contents)
        contents[insert_at:insert_at] = info_chunk_bytes

    riff_size = len(contents) - 8
    contents[4:8] = riff_size.to_bytes(4, "little")
    return True


def _locate_list_info(contents: bytearray) -> tuple[int, int] | None:
    offset = 12
    total = len(contents)
    while offset + 8 <= total:
        chunk_id = bytes(contents[offset : offset + 4])
        chunk_size = int.from_bytes(contents[offset + 4 : offset + 8], "little")
        data_start = offset + 8
        data_end = data_start + chunk_size
        if data_end > total:
            return None
        padded_end = data_end + (chunk_size % 2)
        if chunk_id == b"LIST" and chunk_size >= 4:
            if contents[data_start : data_start + 4] == b"INFO":
                return offset, padded_end
        offset = padded_end
    return None


def _locate_data_chunk_start(contents: bytearray) -> int:
    offset = 12
    total = len(contents)
    while offset + 8 <= total:
        chunk_id = bytes(contents[offset : offset + 4])
        chunk_size = int.from_bytes(contents[offset + 4 : offset + 8], "little")
        data_start = offset + 8
        data_end = data_start + chunk_size
        if data_end > total:
            break
        padded_end = data_end + (chunk_size % 2)
        if chunk_id == b"data":
            return offset
        offset = padded_end
    return total


def _build_info_chunk(metadata: Dict[str, Any]) -> bytes:
    if not metadata:
        return b""

    payload = bytearray(b"INFO")
    for index, (key, value) in enumerate(metadata.items()):
        chunk_id = _chunk_id_for_key(key, index)
        text = f"{key}={_stringify(value)}"
        data = text.encode("utf-8")
        if not data or data[-1] != 0:
            data += b"\x00"
        size = len(data)

        payload.extend(chunk_id.encode("ascii"))
        payload.extend(size.to_bytes(4, "little"))
        payload.extend(data)
        if size % 2 == 1:
            payload.append(0)

    if len(payload) % 2 == 1:
        payload.append(0)

    chunk = bytearray(b"LIST")
    chunk.extend(len(payload).to_bytes(4, "little"))
    chunk.extend(payload)
    return bytes(chunk)


def _chunk_id_for_key(key: str, index: int) -> str:
    cleaned = "".join(ch for ch in key.upper() if ch.isalnum())
    if cleaned:
        body = cleaned[:3].ljust(3, "_")
    else:
        body = f"{index:03d}"
    return f"I{body[:3]}"


def _write_sidecar(path: Path, metadata: Dict[str, Any]) -> Path:
    sidecar = path.with_name(path.name + ".json")
    try:
        sidecar.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        LOGGER.debug("Wrote provenance sidecar %s", sidecar)
    except Exception:  # pragma: no cover - defensive
        LOGGER.warning("Failed to write provenance sidecar %s", sidecar, exc_info=True)
    return sidecar


def _normalize_meta(
    meta: Mapping[str, Any] | Iterable[tuple[str, Any]] | None,
) -> Dict[str, Any]:
    if meta is None:
        return {}
    if isinstance(meta, Mapping):
        items = meta.items()
    else:
        try:
            items = dict(meta).items()  # type: ignore[arg-type]
        except Exception:
            raise TypeError("meta must be mapping-like") from None
    normalized: Dict[str, Any] = {}
    for key, value in items:
        normalized[str(key)] = value
    return normalized


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        return str(value)


__all__ = ["embed_png", "embed_wav"]
