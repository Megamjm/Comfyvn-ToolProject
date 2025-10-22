from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Mapping, Optional

from comfyvn.config import feature_flags
from comfyvn.pov import WORLDLINES
from comfyvn.pov.timeline_worlds import diff_worlds
from comfyvn.pov.worldlines import WorldlineRegistry, make_snapshot_cache_key

from .timeline_overlay import OVERLAY

LOGGER = logging.getLogger(__name__)


class SnapshotController:
    """
    Capture deterministic timeline snapshots and optionally fork new worldlines.

    Snapshots rely on the worldline feature flag; callers should ensure the feature is
    enabled (``enable_worldlines``) before invoking the helpers. When the timeline
    overlay feature is active, successful captures invalidate the cached overlay so the
    GUI refreshes automatically.
    """

    def __init__(
        self,
        *,
        registry: WorldlineRegistry = WORLDLINES,
    ) -> None:
        self._registry = registry

    # ---------------------------------------------------------------- utilities
    def _require_features(self) -> None:
        if not feature_flags.is_enabled("enable_worldlines", default=False):
            raise RuntimeError(
                "Worldline snapshots require enable_worldlines feature flag"
            )
        if not feature_flags.is_enabled("enable_timeline_overlay", default=False):
            raise RuntimeError(
                "Timeline overlay snapshots require enable_timeline_overlay feature flag"
            )

    def _build_entry(
        self,
        *,
        world_id: str,
        scene: str,
        node: str,
        pov: str,
        vars_payload: Mapping[str, Any],
        seed: Any,
        theme: Any,
        weather: Any,
        thumbnail: Optional[str],
        thumbnail_hash: Optional[str],
        badges: Optional[Mapping[str, Any]],
        metadata: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        cache_key = make_snapshot_cache_key(
            scene=scene,
            node=node,
            worldline=world_id,
            pov=pov,
            vars=vars_payload,
            seed=seed,
            theme=theme,
            weather=weather,
        )
        digest = cache_key.rsplit(":", 1)[-1]
        if thumbnail_hash is None:
            source = f"{cache_key}|{thumbnail or ''}|{pov}"
            thumbnail_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        entry: Dict[str, Any] = {
            "scene": scene,
            "node": node,
            "pov": pov,
            "cache_key": cache_key,
            "hash": thumbnail_hash,
            "thumbnail": thumbnail,
            "vars_digest": digest,
            "seed": seed,
            "theme": theme,
            "weather": weather,
            "badges": dict(badges or {}),
            "metadata": dict(metadata or {}),
        }
        entry["badges"].setdefault("pov", pov)
        return entry

    def _invalidate_overlay(self, *world_ids: str) -> None:
        try:
            for world_id in world_ids:
                OVERLAY.invalidate(world_id)
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Overlay invalidation failed", exc_info=True)

    # ---------------------------------------------------------------- captures
    def capture(
        self,
        *,
        world_id: str,
        scene: str,
        node: str,
        pov: str,
        vars_payload: Mapping[str, Any],
        seed: Any,
        theme: Any,
        weather: Any,
        thumbnail: Optional[str] = None,
        thumbnail_hash: Optional[str] = None,
        badges: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        dedupe: bool = True,
        limit: Optional[int] = 250,
    ) -> Dict[str, Any]:
        """
        Capture a snapshot for the specified worldline.

        Returns the recorded snapshot payload (metadata copied from the registry) plus
        the cache key used for deterministic lookups.
        """

        self._require_features()
        entry = self._build_entry(
            world_id=world_id,
            scene=scene,
            node=node,
            pov=pov,
            vars_payload=vars_payload,
            seed=seed,
            theme=theme,
            weather=weather,
            thumbnail=thumbnail,
            thumbnail_hash=thumbnail_hash,
            badges=badges,
            metadata=metadata,
        )
        snapshot = self._registry.record_snapshot(
            world_id,
            entry,
            dedupe=dedupe,
            limit=limit,
        )
        self._invalidate_overlay(world_id)
        LOGGER.info(
            "snapshot.capture worldline=%s node=%s cache=%s pov=%s theme=%s weather=%s",
            world_id,
            node,
            snapshot.get("cache_key"),
            pov,
            snapshot.get("theme"),
            snapshot.get("weather"),
        )
        return {
            "worldline": world_id,
            "snapshot": snapshot,
            "cache_key": snapshot.get("cache_key"),
        }

    def fork_from_state(
        self,
        *,
        source_world_id: str,
        new_world_id: str,
        lane: str,
        scene: str,
        node: str,
        pov: str,
        vars_payload: Mapping[str, Any],
        seed: Any,
        theme: Any,
        weather: Any,
        thumbnail: Optional[str] = None,
        thumbnail_hash: Optional[str] = None,
        world_label: Optional[str] = None,
        world_notes: Optional[str] = None,
        badges: Optional[Mapping[str, Any]] = None,
        snapshot_metadata: Optional[Mapping[str, Any]] = None,
        world_metadata: Optional[Mapping[str, Any]] = None,
        activate: bool = True,
        dedupe: bool = True,
        limit: Optional[int] = 250,
    ) -> Dict[str, Any]:
        """
        Fork a worldline from the given state and persist an initial snapshot.

        Returns the new world snapshot, the recorded timeline snapshot, and the diff
        payload comparing the source and fork (POV-masked).
        """

        self._require_features()
        world_obj, created, pov_snapshot = self._registry.fork(
            source_world_id,
            new_world_id,
            label=world_label,
            lane=lane,
            notes=world_notes,
            metadata=world_metadata,
            set_active=activate,
        )
        entry = self._build_entry(
            world_id=world_obj.id,
            scene=scene,
            node=node,
            pov=pov,
            vars_payload=vars_payload,
            seed=seed,
            theme=theme,
            weather=weather,
            thumbnail=thumbnail,
            thumbnail_hash=thumbnail_hash,
            badges=badges,
            metadata=snapshot_metadata,
        )
        snapshot = self._registry.record_snapshot(
            world_obj.id,
            entry,
            dedupe=dedupe,
            limit=limit,
        )
        diff_payload: Optional[Dict[str, Any]]
        try:
            diff_payload = diff_worlds(
                source_world_id,
                world_obj.id,
                registry=self._registry,
                mask_by_pov=True,
            )
        except KeyError:
            diff_payload = None
        self._invalidate_overlay(source_world_id, world_obj.id)
        LOGGER.info(
            "snapshot.fork source=%s new=%s lane=%s cache=%s pov=%s theme=%s weather=%s",
            source_world_id,
            world_obj.id,
            world_obj.lane,
            snapshot.get("cache_key"),
            pov,
            snapshot.get("theme"),
            snapshot.get("weather"),
        )
        response: Dict[str, Any] = {
            "world": world_obj.snapshot(),
            "created": created,
            "pov": pov_snapshot,
            "snapshot": snapshot,
            "diff": diff_payload,
        }
        return response


SNAPSHOT = SnapshotController()


def capture_snapshot(**kwargs: Any) -> Dict[str, Any]:
    return SNAPSHOT.capture(**kwargs)


def fork_worldline_from_state(**kwargs: Any) -> Dict[str, Any]:
    return SNAPSHOT.fork_from_state(**kwargs)


__all__ = [
    "SnapshotController",
    "SNAPSHOT",
    "capture_snapshot",
    "fork_worldline_from_state",
]
