"""
Asset registry facade for the Studio shell.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import threading
import hashlib
import wave
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Dict, List, Optional
from array import array
from comfyvn.config.runtime_paths import thumb_cache_dir

try:  # thumbnail generation optional
    from PIL import Image  # type: ignore
    from PIL import PngImagePlugin  # type: ignore
except Exception:  # pragma: no cover - pillow optional
    Image = None  # type: ignore
    PngImagePlugin = None  # type: ignore

try:  # audio tagging optional
    from mutagen.id3 import ID3, TXXX, ID3NoHeaderError  # type: ignore
    from mutagen.mp3 import MP3  # type: ignore
    from mutagen.oggvorbis import OggVorbis  # type: ignore
    from mutagen.flac import FLAC  # type: ignore
    from mutagen.wave import WAVE  # type: ignore
except Exception:  # pragma: no cover - mutagen optional
    ID3 = None  # type: ignore
    TXXX = None  # type: ignore
    ID3NoHeaderError = Exception  # type: ignore
    MP3 = None  # type: ignore
    OggVorbis = None  # type: ignore
    FLAC = None  # type: ignore
    WAVE = None  # type: ignore

from .base_registry import BaseRegistry
from .provenance_registry import ProvenanceRegistry

LOGGER = logging.getLogger(__name__)
PROVENANCE_TAG = "comfyvn_provenance"


class AssetRegistry(BaseRegistry):
    TABLE = "assets_registry"
    ASSETS_ROOT = Path("data/assets")
    META_ROOT = ASSETS_ROOT / "_meta"
    THUMB_ROOT = thumb_cache_dir()
    SIDECAR_SUFFIX = ".asset.json"
    _IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
    _AUDIO_WAVEFORM_SUFFIXES = {".wav", ".wave"}
    _thumb_executor: ThreadPoolExecutor | None = None
    _thumb_executor_lock = threading.Lock()
    _pending_futures: set[Future] = set()
    _pending_lock = threading.Lock()

    def __init__(
        self,
        *args,
        assets_root: Path | str | None = None,
        thumb_root: Path | str | None = None,
        meta_root: Path | str | None = None,
        sidecar_suffix: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.ASSETS_ROOT = self._resolve_assets_root(assets_root)
        self.META_ROOT = self._resolve_meta_root(meta_root)
        self.THUMB_ROOT = self._resolve_thumb_root(thumb_root)
        self.sidecar_suffix = sidecar_suffix or self.SIDECAR_SUFFIX
        rel_hint = os.getenv("COMFYVN_THUMBS_REL")
        self._thumb_rel_base = Path(rel_hint).expanduser() if rel_hint else Path("cache/thumbs")
        self.ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
        if self.META_ROOT:
            self.META_ROOT.mkdir(parents=True, exist_ok=True)
        self.THUMB_ROOT.mkdir(parents=True, exist_ok=True)
        self._provenance = ProvenanceRegistry(db_path=self.db_path, project_id=self.project_id)

    @classmethod
    def _resolve_assets_root(cls, override: Path | str | None) -> Path:
        if override:
            return Path(override).expanduser().resolve()
        env = os.getenv("COMFYVN_ASSETS_ROOT")
        if env:
            return Path(env).expanduser().resolve()
        candidates = [
            Path("assets"),
            Path("data/assets"),
            Path("comfyvn/data/assets"),
            cls.ASSETS_ROOT,
        ]
        for candidate in candidates:
            candidate = Path(candidate).expanduser()
            if candidate.exists():
                return candidate.resolve()
        return Path("assets").expanduser().resolve()

    def _resolve_meta_root(self, override: Path | str | None) -> Path | None:
        if override is False:  # type: ignore[truthy-function]
            return None
        if override:
            meta = Path(override).expanduser().resolve()
            meta.mkdir(parents=True, exist_ok=True)
            return meta
        # keep legacy _meta directory for callers that still rely on it
        legacy = self.ASSETS_ROOT / "_meta"
        return legacy

    @staticmethod
    def _resolve_thumb_root(override: Path | str | None) -> Path:
        if override:
            return Path(override).expanduser().resolve()
        env = os.getenv("COMFYVN_THUMBS_ROOT")
        if env:
            return Path(env).expanduser().resolve()
        repo_cache = Path("cache/thumbs")
        if repo_cache.exists() or repo_cache.parent.exists():
            return repo_cache.expanduser().resolve()
        return thumb_cache_dir()

    def _ensure_schema(self) -> None:
        super()._ensure_schema()
        with self.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assets_registry (
                    id INTEGER PRIMARY KEY,
                    project_id TEXT DEFAULT 'default',
                    uid TEXT UNIQUE,
                    type TEXT,
                    path_full TEXT,
                    path_thumb TEXT,
                    hash TEXT,
                    bytes INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    meta JSON
                )
                """
            )

    # ---------------------
    # Public query helpers
    # ---------------------
    def list_assets(self, asset_type: Optional[str] = None) -> List[Dict[str, Any]]:
        if asset_type:
            rows = self.fetchall(
                f"SELECT id, uid, type, path_full, path_thumb, hash, bytes, meta "
                f"FROM {self.TABLE} WHERE project_id = ? AND type = ? ORDER BY id DESC",
                [self.project_id, asset_type],
            )
        else:
            rows = self.fetchall(
                f"SELECT id, uid, type, path_full, path_thumb, hash, bytes, meta "
                f"FROM {self.TABLE} WHERE project_id = ? ORDER BY id DESC",
                [self.project_id],
            )
        return [self._format_asset_row(row) for row in rows]

    def get_asset(self, uid: str) -> Optional[Dict[str, Any]]:
        row = self.fetchone(
            f"SELECT id, uid, type, path_full, path_thumb, hash, bytes, meta "
            f"FROM {self.TABLE} WHERE project_id = ? AND uid = ?",
            [self.project_id, uid],
        )
        return self._format_asset_row(row) if row else None

    # ---------------------
    # Registration helpers
    # ---------------------
    def register_file(
        self,
        source_path: Path | str,
        asset_type: str,
        *,
        dest_relative: Optional[Path | str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        copy: bool = True,
        provenance: Optional[Dict[str, Any]] = None,
        license_tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Copy (or reference) a file into the assets directory and index it."""
        source = Path(source_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"Asset source does not exist: {source}")

        if dest_relative:
            rel_path = Path(dest_relative)
            if rel_path.is_absolute():
                raise ValueError("dest_relative must be relative to the assets root.")
        else:
            rel_path = Path(asset_type) / source.name

        dest = (self.ASSETS_ROOT / rel_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        if copy:
            if source != dest:
                shutil.copy2(source, dest)
                LOGGER.debug("Copied asset %s -> %s", source, dest)
            else:
                LOGGER.debug("Source and destination are identical for %s; skipping copy.", source)
                copy = False
        else:
            try:
                rel_path = source.relative_to(self.ASSETS_ROOT)
            except ValueError as exc:
                raise ValueError(
                    f"Non-copied assets must reside inside the assets root ({self.ASSETS_ROOT}); got {source}"
                ) from exc
            dest = source

        file_hash = self._sha256(dest)
        uid = file_hash[:16]
        meta_payload = metadata.copy() if metadata else {}
        if license_tag:
            meta_payload.setdefault("license", license_tag)
        size_bytes = dest.stat().st_size
        preview_rel, preview_kind = self._schedule_preview(dest, uid)
        if preview_rel:
            meta_payload.setdefault("preview", {"path": preview_rel, "kind": preview_kind or "thumbnail"})

        meta_json = self.dumps(meta_payload)
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO assets_registry (project_id, uid, type, path_full, path_thumb, hash, bytes, meta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET
                    type=excluded.type,
                    path_full=excluded.path_full,
                    path_thumb=excluded.path_thumb,
                    hash=excluded.hash,
                    bytes=excluded.bytes,
                    meta=excluded.meta
                """,
                (
                    self.project_id,
                    uid,
                    asset_type,
                    str(rel_path.as_posix()),
                    preview_rel,
                    file_hash,
                    size_bytes,
                    meta_json,
                ),
            )

        asset_row = self.fetchone(
            f"SELECT id FROM {self.TABLE} WHERE project_id = ? AND uid = ?",
            [self.project_id, uid],
        )
        asset_db_id = int(asset_row["id"]) if asset_row else None

        provenance_record = None
        if provenance and asset_db_id is not None:
            provenance_record = self._record_provenance(
                asset_db_id,
                uid,
                file_hash,
                provenance,
                meta_payload,
            )
            if copy:
                self._embed_provenance_marker(dest, provenance_record)
        elif provenance:
            LOGGER.warning("Provenance payload supplied but asset id unavailable for uid=%s", uid)

        preview_entry = None
        if preview_rel:
            preview_entry = {"path": preview_rel, "kind": preview_kind or "thumbnail"}

        sidecar_path = self._sidecar_path(rel_path)
        sidecar = {
            "id": uid,
            "uid": uid,
            "type": asset_type,
            "path": str(rel_path.as_posix()),
            "hash": file_hash,
            "bytes": size_bytes,
            "meta": meta_payload,
        }
        if license_tag:
            sidecar["license"] = license_tag
        if preview_entry:
            sidecar["preview"] = preview_entry
        if provenance_record:
            sidecar["provenance"] = provenance_record
        self._write_sidecar(rel_path, sidecar)
        LOGGER.info("Registered asset %s (%s)", uid, rel_path)
        try:
            sidecar_rel = str(sidecar_path.relative_to(self.ASSETS_ROOT).as_posix())
        except ValueError:
            sidecar_rel = sidecar_path.as_posix()
        return {
            "uid": uid,
            "type": asset_type,
            "path": str(rel_path.as_posix()),
            "thumb": preview_rel,
            "hash": file_hash,
            "bytes": size_bytes,
            "meta": meta_payload,
            "provenance": provenance_record,
            "preview": preview_entry,
            "sidecar": sidecar_rel,
        }

    def resolve_path(self, uid: str) -> Optional[Path]:
        asset = self.get_asset(uid)
        if not asset:
            return None
        return (self.ASSETS_ROOT / asset["path"]).resolve()

    def remove_asset(self, uid: str, *, delete_files: bool = False) -> bool:
        """Delete an asset registry entry and optionally remove files on disk."""
        asset = self.get_asset(uid)
        if not asset:
            return False

        with self.connection() as conn:
            conn.execute(
                f"DELETE FROM {self.TABLE} WHERE project_id = ? AND uid = ?",
                (self.project_id, uid),
            )

        thumb_rel = asset.get("thumb")
        if thumb_rel:
            try:
                full_thumb = (self.THUMB_ROOT / Path(thumb_rel).name).resolve()
                if full_thumb.exists():
                    full_thumb.unlink()
            except Exception:
                LOGGER.debug("Failed to remove thumbnail for %s", uid)

        if delete_files:
            try:
                path = (self.ASSETS_ROOT / asset["path"]).resolve()
                if path.exists():
                    path.unlink()
            except Exception:
                LOGGER.debug("Failed to remove asset file for %s", uid)

        rel_path = Path(asset["path"])
        primary_sidecar = self._sidecar_path(rel_path)
        if primary_sidecar.exists():
            try:
                primary_sidecar.unlink()
            except Exception:
                LOGGER.debug("Failed to remove sidecar for %s", uid)
        if self.META_ROOT:
            legacy_sidecar = (self.META_ROOT / rel_path).with_suffix(".json")
            if legacy_sidecar.exists():
                try:
                    legacy_sidecar.unlink()
                except Exception:
                    LOGGER.debug("Failed to remove legacy sidecar for %s", uid)

        LOGGER.info("Removed asset %s", uid)
        return True

    # ---------------------
    # Internal helpers
    # ---------------------
    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _sidecar_path(self, rel_path: Path) -> Path:
        rel = Path(rel_path)
        target = self.ASSETS_ROOT / rel
        return target.with_suffix(target.suffix + self.sidecar_suffix)

    def _write_sidecar(self, rel_path: Path, payload: Dict[str, Any]) -> None:
        canonical = dict(payload)
        canonical.setdefault("id", canonical.get("uid"))
        primary_path = self._sidecar_path(rel_path)
        primary_path.parent.mkdir(parents=True, exist_ok=True)
        primary_path.write_text(json.dumps(canonical, indent=2, ensure_ascii=False), encoding="utf-8")
        LOGGER.debug("Sidecar written: %s", primary_path)
        if self.META_ROOT:
            legacy_path = (self.META_ROOT / rel_path).with_suffix(".json")
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.write_text(json.dumps(canonical, indent=2, ensure_ascii=False), encoding="utf-8")
            LOGGER.debug("Legacy sidecar mirrored: %s", legacy_path)

    def _format_asset_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        payload = dict(row)
        payload["path"] = payload.pop("path_full")
        thumb = payload.pop("path_thumb", None)
        if thumb is not None:
            payload["thumb"] = thumb
        meta = payload.get("meta")
        if isinstance(meta, str):
            try:
                payload["meta"] = json.loads(meta)
            except json.JSONDecodeError:
                payload["meta"] = meta
        rel_path = Path(payload["path"])
        sidecar_path = self._sidecar_path(rel_path)
        try:
            sidecar_rel = sidecar_path.relative_to(self.ASSETS_ROOT)
            payload["sidecar"] = sidecar_rel.as_posix()
        except Exception:
            payload["sidecar"] = sidecar_path.as_posix()
        return payload

    @classmethod
    def _get_thumbnail_executor(cls) -> ThreadPoolExecutor:
        if cls._thumb_executor is None:
            with cls._thumb_executor_lock:
                if cls._thumb_executor is None:
                    cls._thumb_executor = ThreadPoolExecutor(
                        max_workers=2,
                        thread_name_prefix="AssetThumb",
                    )
        return cls._thumb_executor

    def _schedule_preview(self, dest: Path, uid: str) -> tuple[Optional[str], Optional[str]]:
        suffix = dest.suffix.lower()
        preview_kind: Optional[str]
        if suffix in self._IMAGE_SUFFIXES:
            if Image is None:
                LOGGER.debug("Pillow not available; skipping thumbnail for %s", dest)
                return (None, None)
            thumb_path = self.THUMB_ROOT / f"{uid}{suffix}"
            preview_kind = "thumbnail"
        elif suffix in self._AUDIO_WAVEFORM_SUFFIXES:
            thumb_path = self.THUMB_ROOT / f"{uid}.waveform.json"
            preview_kind = "waveform"
        else:
            LOGGER.debug("Skipping preview for %s (unsupported suffix)", dest)
            return (None, None)

        thumb_rel = str((self._thumb_rel_base / thumb_path.name).as_posix())
        executor = self._get_thumbnail_executor()
        future = executor.submit(self._thumbnail_job, dest, thumb_path, thumb_rel, uid, preview_kind)
        self._register_thumbnail_future(future)
        return thumb_rel, preview_kind

    @classmethod
    def _register_thumbnail_future(cls, future: Future) -> None:
        with cls._pending_lock:
            cls._pending_futures.add(future)

        def _cleanup(fut: Future) -> None:
            with cls._pending_lock:
                cls._pending_futures.discard(fut)

        future.add_done_callback(_cleanup)

    @classmethod
    def wait_for_thumbnails(cls, timeout: float | None = None) -> bool:
        with cls._pending_lock:
            pending = list(cls._pending_futures)
        if not pending:
            return True
        done, not_done = wait(pending, timeout=timeout)
        return not not_done

    def _thumbnail_job(
        self,
        source: Path,
        thumb_path: Path,
        thumb_rel: str,
        uid: str,
        preview_kind: Optional[str],
    ) -> None:
        success = self._create_preview_file(source, thumb_path)
        if not success:
            LOGGER.warning(
                "Clearing %s preview for %s due to generation failure",
                preview_kind or "thumbnail",
                uid,
            )
            thumb_path.unlink(missing_ok=True)
            with self.connection() as conn:
                conn.execute(
                    f"UPDATE {self.TABLE} SET path_thumb = NULL WHERE project_id = ? AND uid = ?",
                    (self.project_id, uid),
                )

    def _create_preview_file(self, source: Path, thumb_path: Path) -> bool:
        suffix = source.suffix.lower()
        if suffix in self._IMAGE_SUFFIXES:
            return self._create_image_thumbnail(source, thumb_path)
        if suffix in self._AUDIO_WAVEFORM_SUFFIXES:
            return self._create_waveform_preview(source, thumb_path)
        return False

    @staticmethod
    def _create_image_thumbnail(source: Path, thumb_path: Path) -> bool:
        if Image is None:
            return False
        try:
            with Image.open(source) as img:  # type: ignore[attr-defined]
                img.thumbnail((256, 256))
                thumb_path.parent.mkdir(parents=True, exist_ok=True)
                img.save(thumb_path)
            return True
        except Exception as exc:  # pragma: no cover - optional
            LOGGER.warning("Thumbnail generation failed for %s: %s", source, exc)
            return False

    @staticmethod
    def _create_waveform_preview(source: Path, thumb_path: Path) -> bool:
        try:
            with wave.open(str(source), "rb") as wav_file:
                frames = wav_file.getnframes()
                channels = wav_file.getnchannels()
                sampwidth = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                if frames <= 0 or sampwidth not in (1, 2):
                    LOGGER.debug("Unsupported waveform parameters for %s", source)
                    return False
                raw = wav_file.readframes(frames)
        except wave.Error as exc:
            LOGGER.debug("Waveform probe failed for %s: %s", source, exc)
            return False
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Waveform read failed for %s: %s", source, exc)
            return False

        if sampwidth == 1:
            samples = array("b", raw)
        else:
            samples = array("h")
            samples.frombytes(raw)

        if channels > 1:
            samples = samples[::channels]

        if not samples:
            LOGGER.debug("No samples available for waveform preview in %s", source)
            return False

        max_amplitude = max(1, max(abs(int(v)) for v in samples))
        target_points = 512
        step = max(1, len(samples) // target_points)
        points: List[float] = []
        for idx in range(0, len(samples), step):
            window = samples[idx : idx + step]
            if not window:
                break
            peak = max(window)
            trough = min(window)
            amplitude = max(abs(int(peak)), abs(int(trough))) / max_amplitude
            points.append(round(float(amplitude), 4))
            if len(points) >= target_points:
                break

        payload = {
            "kind": "waveform",
            "channels": channels,
            "sample_rate": framerate,
            "points": points,
        }
        try:
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            thumb_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to write waveform preview for %s: %s", source, exc)
            return False

    # ---------------------
    # Provenance helpers
    # ---------------------
    def _record_provenance(
        self,
        asset_db_id: int,
        uid: str,
        file_hash: str,
        provenance: Dict[str, Any],
        meta_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        source = (provenance.get("source") or meta_payload.get("source") or "unspecified").strip()
        user_id = provenance.get("user_id") or meta_payload.get("user_id") or os.getenv("COMFYVN_USER")
        workflow_hash = provenance.get("workflow_hash")
        commit_hash = provenance.get("commit_hash") or os.getenv("COMFYVN_GIT_COMMIT")
        inputs = provenance.get("inputs") or {}
        inputs.setdefault("asset_uid", uid)
        inputs.setdefault("asset_hash", file_hash)
        c2pa_like = provenance.get("c2pa_like") or {}

        record = self._provenance.record(
            asset_db_id,
            source=source,
            workflow_hash=workflow_hash,
            commit_hash=commit_hash,
            inputs=inputs,
            c2pa_like=c2pa_like,
            user_id=user_id,
        )
        record["asset_uid"] = uid
        return record

    def _embed_provenance_marker(self, dest: Path, provenance_record: Dict[str, Any]) -> None:
        if Image is None:
            LOGGER.debug("Skipping provenance stamp for %s (Pillow unavailable)", dest)
            return

        marker = json.dumps(
            {
                "provenance_id": provenance_record.get("id"),
                "source": provenance_record.get("source"),
                "workflow_hash": provenance_record.get("workflow_hash"),
                "created_at": provenance_record.get("created_at"),
            },
            ensure_ascii=False,
        )

        suffix = dest.suffix.lower()
        try:
            if suffix == ".png" and PngImagePlugin is not None:
                self._stamp_png(dest, marker)
            elif suffix in {".mp3", ".ogg", ".oga", ".flac", ".wav", ".wave"}:
                self._stamp_audio(dest, marker, suffix)
            else:
                LOGGER.debug("No provenance marker implementation for %s files", suffix)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to embed provenance marker for %s: %s", dest, exc)

    @staticmethod
    def _stamp_png(dest: Path, marker: str) -> None:
        if Image is None or PngImagePlugin is None:
            return
        with Image.open(dest) as img:  # type: ignore[attr-defined]
            png_info = PngImagePlugin.PngInfo()  # type: ignore[attr-defined]
            if hasattr(img, "text"):
                for key, value in getattr(img, "text").items():
                    png_info.add_text(key, value)
            else:
                for key, value in img.info.items():
                    if isinstance(value, str):
                        png_info.add_text(key, value)
            png_info.add_text(PROVENANCE_TAG, marker)
            img.save(dest, pnginfo=png_info)

    @staticmethod
    def _stamp_audio(dest: Path, marker: str, suffix: str) -> None:
        if suffix == ".mp3":
            AssetRegistry._stamp_mp3(dest, marker)
        elif suffix in {".ogg", ".oga"}:
            AssetRegistry._stamp_ogg(dest, marker)
        elif suffix == ".flac":
            AssetRegistry._stamp_flac(dest, marker)
        elif suffix in {".wav", ".wave"}:
            AssetRegistry._stamp_wav(dest, marker)

    @staticmethod
    def _stamp_mp3(dest: Path, marker: str) -> None:
        if MP3 is None or ID3 is None or TXXX is None:
            LOGGER.debug("Mutagen ID3 support unavailable; skipping MP3 provenance for %s", dest)
            return
        try:
            try:
                tags = ID3(dest)  # type: ignore[call-arg]
            except ID3NoHeaderError:  # type: ignore[misc]
                tags = ID3()  # type: ignore[call-arg]
            tags.delall(f"TXXX:{PROVENANCE_TAG}")
            tags.add(TXXX(encoding=3, desc=PROVENANCE_TAG, text=[marker]))
            tags.save(dest)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - optional
            LOGGER.warning("Unable to embed MP3 provenance for %s: %s", dest, exc)

    @staticmethod
    def _stamp_ogg(dest: Path, marker: str) -> None:
        if OggVorbis is None:
            LOGGER.debug("Mutagen Ogg support unavailable; skipping provenance for %s", dest)
            return
        try:
            audio = OggVorbis(dest)  # type: ignore[call-arg]
            audio[PROVENANCE_TAG] = [marker]
            audio.save()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - optional
            LOGGER.warning("Unable to embed OGG provenance for %s: %s", dest, exc)

    @staticmethod
    def _stamp_flac(dest: Path, marker: str) -> None:
        if FLAC is None:
            LOGGER.debug("Mutagen FLAC support unavailable; skipping provenance for %s", dest)
            return
        try:
            audio = FLAC(dest)  # type: ignore[call-arg]
            audio[PROVENANCE_TAG] = [marker]
            audio.save()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - optional
            LOGGER.warning("Unable to embed FLAC provenance for %s: %s", dest, exc)

    @staticmethod
    def _stamp_wav(dest: Path, marker: str) -> None:
        if WAVE is None or TXXX is None:
            LOGGER.debug("Mutagen WAV support unavailable; skipping provenance for %s", dest)
            return
        try:
            audio = WAVE(dest)  # type: ignore[call-arg]
            if getattr(audio, "tags", None) is None:
                add_tags = getattr(audio, "add_tags", None)
                if callable(add_tags):
                    add_tags()
            tags = getattr(audio, "tags", None)
            if tags is None:
                LOGGER.warning("Unable to embed WAV provenance for %s (no tag container)", dest)
                return
            tags.delall(f"TXXX:{PROVENANCE_TAG}")
            tags.add(TXXX(encoding=3, desc=PROVENANCE_TAG, text=[marker]))  # type: ignore[call-arg]
            audio.save()  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - optional
            LOGGER.warning("Unable to embed WAV provenance for %s: %s", dest, exc)
