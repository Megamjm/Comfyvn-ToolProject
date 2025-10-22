from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from comfyvn.bridge.comfy_hardening import (
    HardenedBridgeError,
    HardenedBridgeUnavailable,
    HardenedComfyBridge,
    LoRAEntry,
)
from comfyvn.config.runtime_paths import cache_dir, data_dir
from comfyvn.studio.core.asset_registry import AssetRegistry

LOGGER = logging.getLogger("comfyvn.pov.render")

DEFAULT_RENDER_ROOT = data_dir("renders", "pov")
DEFAULT_CACHE_PATH = cache_dir("pov", "render_cache.json")


class POVRenderError(RuntimeError):
    """Raised when POV render orchestration cannot complete."""


@dataclass
class POVRenderCacheEntry:
    key: str
    character_id: str
    style: str
    pose: str
    artifact: str
    sidecar: Optional[str]
    bridge_sidecar: Optional[str]
    asset_uid: Optional[str]
    created_at: float
    last_access: float

    def touch(self) -> None:
        self.last_access = time.time()

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["last_access"] = self.last_access
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "POVRenderCacheEntry":
        return cls(
            key=str(payload.get("key") or ""),
            character_id=str(payload.get("character_id") or ""),
            style=str(payload.get("style") or "default"),
            pose=str(payload.get("pose") or "default"),
            artifact=str(payload.get("artifact") or ""),
            sidecar=payload.get("sidecar"),
            bridge_sidecar=payload.get("bridge_sidecar"),
            asset_uid=payload.get("asset_uid"),
            created_at=float(payload.get("created_at") or time.time()),
            last_access=float(payload.get("last_access") or time.time()),
        )


class POVRenderCache:
    """JSON-backed cache for POV render artifacts."""

    def __init__(self, path: Path | str = DEFAULT_CACHE_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: Dict[str, POVRenderCacheEntry] = {}
        self._lock = threading.RLock()
        self._load()

    @staticmethod
    def make_key(character_id: str, style: Optional[str], pose: Optional[str]) -> str:
        parts = [
            (character_id or "unknown").strip().lower() or "unknown",
            (style or "default").strip().lower() or "default",
            (pose or "default").strip().lower() or "default",
        ]
        return "|".join(parts)

    def _load(self) -> None:
        if not self.path.exists():
            self._persist()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("Failed to load POV render cache: %s", exc)
            data = {}
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            record = POVRenderCacheEntry.from_dict(entry)
            if not record.key:
                record.key = key
            self._entries[record.key] = record

    def _persist(self) -> None:
        serialisable = {key: entry.to_dict() for key, entry in self._entries.items()}
        self.path.write_text(json.dumps(serialisable, indent=2), encoding="utf-8")

    def lookup(self, key: str) -> Optional[POVRenderCacheEntry]:
        with self._lock:
            entry = self._entries.get(key)
            if entry:
                entry.touch()
                self._persist()
            return entry

    def store(self, entry: POVRenderCacheEntry) -> POVRenderCacheEntry:
        with self._lock:
            entry.touch()
            self._entries[entry.key] = entry
            self._persist()
            LOGGER.debug(
                "POV render cache stored key=%s artifact=%s",
                entry.key,
                entry.artifact,
            )
            return entry

    def delete(self, key: str) -> None:
        with self._lock:
            if key in self._entries:
                self._entries.pop(key)
                self._persist()


class POVRenderPipeline:
    """Coordinates POV portrait renders with per-character LoRA support."""

    def __init__(
        self,
        *,
        bridge: Optional[HardenedComfyBridge] = None,
        registry: Optional[AssetRegistry] = None,
        render_root: Path | str | None = None,
        cache: Optional[POVRenderCache] = None,
    ) -> None:
        self.bridge = bridge or HardenedComfyBridge()
        self.registry = registry or AssetRegistry()
        self.render_root = (
            Path(render_root).expanduser().resolve()
            if render_root
            else DEFAULT_RENDER_ROOT
        )
        self.render_root.mkdir(parents=True, exist_ok=True)
        self.cache = cache or POVRenderCache()
        self._lock = threading.RLock()

    def ensure_poses(
        self,
        character_id: str,
        *,
        style: Optional[str] = None,
        poses: Optional[Iterable[str]] = None,
        workflow_path: Optional[str | Path] = None,
        force: bool = False,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not character_id or not str(character_id).strip():
            raise POVRenderError("character_id is required")
        pose_list = self._normalise_poses(poses)
        results: List[Dict[str, Any]] = []
        for pose in pose_list:
            result = self._ensure_pose(
                character_id=character_id,
                style=style,
                pose=pose,
                workflow_path=workflow_path,
                force=force,
                extra_metadata=extra_metadata,
            )
            if result:
                results.append(result)
        return results

    def _ensure_pose(
        self,
        *,
        character_id: str,
        style: Optional[str],
        pose: str,
        workflow_path: Optional[str | Path],
        force: bool,
        extra_metadata: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        key = self.cache.make_key(character_id, style, pose)
        if not force:
            cached = self.cache.lookup(key)
            cached_payload = self._materialise_cache_entry(cached)
            if cached_payload:
                LOGGER.debug(
                    "POV render cache hit char=%s style=%s pose=%s",
                    character_id,
                    style or "default",
                    pose,
                )
                return cached_payload

        LOGGER.info(
            "POV render triggering char=%s style=%s pose=%s",
            character_id,
            style or "default",
            pose,
        )
        bridge_payload = self._build_bridge_payload(
            character_id=character_id,
            style=style,
            pose=pose,
            workflow_path=workflow_path,
        )
        render_result = self._invoke_bridge(
            bridge_payload,
            character_id=character_id,
            style=style,
            pose=pose,
        )
        asset_payload = self._register_asset(
            render_result=render_result,
            character_id=character_id,
            style=style,
            pose=pose,
            extra_metadata=extra_metadata,
        )
        entry = POVRenderCacheEntry(
            key=key,
            character_id=character_id,
            style=asset_payload["style"],
            pose=asset_payload["pose"],
            artifact=asset_payload["asset_path"],
            sidecar=asset_payload.get("asset_sidecar"),
            bridge_sidecar=asset_payload.get("bridge_sidecar"),
            asset_uid=asset_payload.get("asset", {}).get("uid"),
            created_at=time.time(),
            last_access=time.time(),
        )
        self.cache.store(entry)
        asset_payload["cached"] = False
        asset_payload["cache_key"] = key
        return asset_payload

    def _materialise_cache_entry(
        self, entry: Optional[POVRenderCacheEntry]
    ) -> Optional[Dict[str, Any]]:
        if not entry:
            return None
        artifact_path = Path(entry.artifact)
        if not artifact_path.exists():
            LOGGER.info("POV render cache stale (artifact missing) key=%s", entry.key)
            self.cache.delete(entry.key)
            return None

        asset_info: Optional[Dict[str, Any]] = None
        if entry.asset_uid:
            asset_info = self.registry.get_asset(entry.asset_uid)
            if not asset_info:
                LOGGER.info(
                    "POV render cache stale (asset missing) uid=%s", entry.asset_uid
                )
                self.cache.delete(entry.key)
                return None

        asset_sidecar = Path(entry.sidecar) if entry.sidecar else None
        if asset_sidecar and not asset_sidecar.exists():
            LOGGER.info("POV render cache stale (sidecar missing) key=%s", entry.key)
            self.cache.delete(entry.key)
            return None

        payload = {
            "character_id": entry.character_id,
            "style": entry.style,
            "pose": entry.pose,
            "artifact": str(artifact_path),
            "asset_path": str(artifact_path),
            "asset_sidecar": str(asset_sidecar) if asset_sidecar else None,
            "bridge_sidecar": entry.bridge_sidecar,
            "cached": True,
            "cache_key": entry.key,
        }
        if asset_info:
            payload["asset"] = asset_info
        if entry.bridge_sidecar and Path(entry.bridge_sidecar).exists():
            payload["bridge_sidecar"] = entry.bridge_sidecar
        return payload

    def _build_bridge_payload(
        self,
        *,
        character_id: str,
        style: Optional[str],
        pose: str,
        workflow_path: Optional[str | Path],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "workflow_id": self._workflow_id(character_id, style, pose),
            "metadata": {
                "character_id": character_id,
                "pose": pose,
                "style": style or "default",
                "channel": "portrait",
            },
            "inputs": {
                "character": character_id,
                "pose": pose,
                "style": style or "default",
            },
            "characters": [character_id],
            "character": character_id,
        }
        if workflow_path:
            payload["workflow_path"] = str(Path(workflow_path).expanduser())
        return payload

    def _invoke_bridge(
        self,
        payload: Dict[str, Any],
        *,
        character_id: str,
        style: Optional[str],
        pose: str,
    ) -> Dict[str, Any]:
        try:
            self.bridge.reload()
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("POV bridge reload failed; continuing with cached config")
        if not getattr(self.bridge, "enabled", True):
            raise POVRenderError(
                "Hardened ComfyUI bridge is disabled; enable enable_comfy_bridge_hardening"
            )
        try:
            result = self.bridge.submit(payload)
        except HardenedBridgeUnavailable as exc:
            raise POVRenderError(f"ComfyUI backend unavailable: {exc}") from exc
        except HardenedBridgeError as exc:
            raise POVRenderError(str(exc)) from exc

        primary = result.get("primary_artifact") or {}
        artifact_path = Path(str(primary.get("path") or "")).expanduser()
        if not artifact_path.exists():
            raise POVRenderError(
                f"ComfyUI render did not produce an artifact for {character_id}/{pose}"
            )
        result["artifact_path"] = str(artifact_path)

        sidecar_payload = result.get("sidecar") or {}
        sidecar_path = sidecar_payload.get("path")
        if sidecar_path:
            result["sidecar_path"] = str(Path(sidecar_path).expanduser())
        else:
            result["sidecar_path"] = None

        overrides = result.get("overrides") or {}
        if not overrides.get("loras"):
            overrides["loras"] = [
                entry.to_dict() for entry in self._character_loras([character_id])
            ]
            result["overrides"] = overrides
        LOGGER.debug(
            "POV bridge completed char=%s style=%s pose=%s artifact=%s",
            character_id,
            style or "default",
            pose,
            artifact_path,
        )
        return result

    def _register_asset(
        self,
        *,
        render_result: Dict[str, Any],
        character_id: str,
        style: Optional[str],
        pose: str,
        extra_metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        artifact_path = Path(render_result["artifact_path"])
        suffix = artifact_path.suffix or ".png"
        style_slug = self._slug(style or "default")
        pose_slug = self._slug(pose or "default")
        character_slug = self._slug(character_id)
        dest_relative = (
            Path("characters") / character_slug / style_slug / f"{pose_slug}{suffix}"
        )
        overrides = render_result.get("overrides") or {}
        loras = overrides.get("loras") or []
        metadata: Dict[str, Any] = {
            "character_id": character_id,
            "style": style or "default",
            "pose": pose,
            "origin": "pov_render_pipeline",
            "workflow_id": render_result.get("workflow_id"),
            "prompt_id": render_result.get("prompt_id"),
            "rendered_at": time.time(),
            "loras": loras,
        }
        if extra_metadata:
            metadata.update(extra_metadata)
        sidecar_content = render_result.get("sidecar_content")
        if sidecar_content:
            metadata["comfy_sidecar"] = sidecar_content
        payload = self.registry.register_file(
            artifact_path,
            asset_type="portrait",
            dest_relative=dest_relative,
            metadata=metadata,
            copy=True,
        )
        asset_path = (self.registry.ASSETS_ROOT / payload["path"]).resolve()
        asset_sidecar = payload.get("sidecar")
        asset_sidecar_path = (
            (self.registry.ASSETS_ROOT / asset_sidecar).resolve()
            if asset_sidecar
            else None
        )
        bridge_sidecar = render_result.get("sidecar_path")
        self._copy_bridge_sidecar(
            bridge_sidecar,
            asset_path.with_suffix(f"{asset_path.suffix}.bridge.json"),
        )
        result = {
            "character_id": character_id,
            "style": style or "default",
            "pose": pose,
            "asset": payload,
            "asset_path": str(asset_path),
            "asset_sidecar": str(asset_sidecar_path) if asset_sidecar_path else None,
            "bridge_sidecar": bridge_sidecar,
            "loras": loras,
        }
        return result

    def _copy_bridge_sidecar(self, source: Optional[str], destination: Path) -> None:
        if not source:
            return
        src_path = Path(source)
        if not src_path.exists():
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src_path, destination)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug(
                "Failed to copy bridge sidecar %s -> %s (%s)",
                src_path,
                destination,
                exc,
            )

    @staticmethod
    def _normalise_poses(poses: Optional[Iterable[str]]) -> List[str]:
        if poses is None:
            return ["default"]
        result: List[str] = []
        for pose in poses:
            if pose is None:
                continue
            text = str(pose).strip()
            if not text:
                continue
            result.append(text)
        return result or ["default"]

    def _character_loras(self, characters: Sequence[str]) -> List[LoRAEntry]:
        try:
            return self.bridge.character_loras(characters)
        except AttributeError:
            entries: List[LoRAEntry] = []
            for character_id in characters:
                entries.extend(self.bridge._registry.load(character_id))  # type: ignore[attr-defined]
            return entries

    @staticmethod
    def _workflow_id(character_id: str, style: Optional[str], pose: str) -> str:
        return f"pov.{character_id}.{style or 'default'}.{pose}"

    @staticmethod
    def _slug(value: str) -> str:
        lowered = value.lower()
        return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_") or "default"


__all__ = [
    "POVRenderPipeline",
    "POVRenderCache",
    "POVRenderCacheEntry",
    "POVRenderError",
]
