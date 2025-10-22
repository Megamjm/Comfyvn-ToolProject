from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from comfyvn.config.runtime_paths import cache_dir
from comfyvn.core import modder_hooks
from comfyvn.core.modder_hooks import HookSpec

LOGGER = logging.getLogger(__name__)

_THUMB_WIDTH = 512
_THUMB_HEIGHT = 288
_FALLBACK_PNG = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000A49444154789C63000100000500010D0A2DB40000000049454E44AE426082"
)


def _slugify(value: str) -> str:
    sanitized = "".join(ch if ch.isalnum() else "_" for ch in str(value))
    sanitized = sanitized.strip("_") or "scene"
    return sanitized.lower()


def _ensure_thumbnail_hook() -> None:
    if "on_thumbnail_captured" in modder_hooks.HOOK_SPECS:
        return
    spec = HookSpec(
        name="on_thumbnail_captured",
        description="Emitted when the Mini-VN thumbnailer writes a deterministic scene thumbnail.",
        payload_fields={
            "scene_id": "Scene identifier that was captured.",
            "timeline_id": "Timeline identifier associated with the capture.",
            "pov": "POV identifier used for the capture when available.",
            "seed": "Deterministic seed used by the Mini-VN player.",
            "path": "Absolute path to the thumbnail image on disk.",
            "filename": "Filename of the generated thumbnail.",
            "digest": "Content digest used to detect cache changes.",
            "width": "Thumbnail width in pixels.",
            "height": "Thumbnail height in pixels.",
            "timestamp": "Capture completion timestamp (UTC seconds).",
        },
        ws_topic="viewer.thumbnail_captured",
        rest_event="on_thumbnail_captured",
    )
    modder_hooks.HOOK_SPECS["on_thumbnail_captured"] = spec
    bus = getattr(modder_hooks, "_BUS", None)
    if bus and getattr(bus, "_listeners", None) is not None:
        with bus._lock:  # type: ignore[attr-defined]
            bus._listeners.setdefault(spec.name, [])  # type: ignore[attr-defined]


@dataclass(frozen=True)
class MiniVNThumbnail:
    scene_id: str
    key: str
    filename: str
    path: Path
    digest: str
    width: int
    height: int
    updated_at: float
    timeline_id: str
    pov: Optional[str]
    seed: int

    def to_dict(self) -> dict[str, object]:
        return {
            "scene_id": self.scene_id,
            "key": self.key,
            "filename": self.filename,
            "digest": self.digest,
            "width": self.width,
            "height": self.height,
            "updated_at": self.updated_at,
            "timeline_id": self.timeline_id,
            "pov": self.pov,
            "seed": self.seed,
        }


class MiniVNThumbnailer:
    """Deterministic thumbnail helper for Mini-VN fallback previews."""

    def __init__(self, *, root: Optional[Path] = None) -> None:
        self._root = Path(root) if root else cache_dir("viewer", "thumbnails")
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def capture(
        self,
        *,
        scene_id: str,
        digest: str,
        title: str,
        subtitle: Optional[str],
        pov: Optional[str],
        seed: int,
        timeline_id: str,
    ) -> MiniVNThumbnail:
        key = _slugify(scene_id or "scene")
        image_path = self._root / f"{key}.png"
        meta_path = self._root / f"{key}.json"
        previous = self._read_meta(meta_path)
        if previous and previous.get("digest") == digest and image_path.exists():
            return MiniVNThumbnail(
                scene_id=scene_id,
                key=key,
                filename=image_path.name,
                path=image_path,
                digest=digest,
                width=int(previous.get("width", _THUMB_WIDTH)),
                height=int(previous.get("height", _THUMB_HEIGHT)),
                updated_at=float(previous.get("updated_at", time.time())),
                timeline_id=timeline_id,
                pov=previous.get("pov"),
                seed=int(previous.get("seed", seed)),
            )

        image_path.parent.mkdir(parents=True, exist_ok=True)
        width, height = self._render_thumbnail(
            image_path, title=title, subtitle=subtitle, digest=digest
        )
        meta = {
            "scene_id": scene_id,
            "digest": digest,
            "width": width,
            "height": height,
            "updated_at": time.time(),
            "timeline_id": timeline_id,
            "pov": pov,
            "seed": seed,
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        record = MiniVNThumbnail(
            scene_id=scene_id,
            key=key,
            filename=image_path.name,
            path=image_path,
            digest=digest,
            width=width,
            height=height,
            updated_at=meta["updated_at"],
            timeline_id=timeline_id,
            pov=pov,
            seed=seed,
        )
        _ensure_thumbnail_hook()
        try:
            modder_hooks.emit(
                "on_thumbnail_captured",
                {
                    "scene_id": scene_id,
                    "timeline_id": timeline_id,
                    "pov": pov,
                    "seed": seed,
                    "path": record.path.as_posix(),
                    "filename": record.filename,
                    "digest": digest,
                    "width": width,
                    "height": height,
                    "timestamp": record.updated_at,
                },
            )
        except Exception:
            LOGGER.debug("Thumbnail hook emission failed", exc_info=True)
        return record

    def purge(self, active_keys: Iterable[str]) -> None:
        keys = {k for k in active_keys}
        for meta_path in self._root.glob("*.json"):
            key = meta_path.stem
            if key in keys:
                continue
            image_path = self._root / f"{key}.png"
            try:
                meta_path.unlink(missing_ok=True)
            except Exception:
                LOGGER.debug(
                    "Failed to remove stale thumbnail metadata %s",
                    meta_path,
                    exc_info=True,
                )
            if image_path.exists():
                try:
                    image_path.unlink()
                except Exception:
                    LOGGER.debug(
                        "Failed to remove stale thumbnail %s", image_path, exc_info=True
                    )

    def _read_meta(self, path: Path) -> Optional[dict[str, object]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            LOGGER.debug("Thumbnail meta read failed for %s", path, exc_info=True)
            return None

    def _render_thumbnail(
        self,
        path: Path,
        *,
        title: str,
        subtitle: Optional[str],
        digest: str,
    ) -> tuple[int, int]:
        width, height = _THUMB_WIDTH, _THUMB_HEIGHT
        try:
            from PIL import Image, ImageDraw, ImageFont  # type: ignore
        except Exception as exc:  # pragma: no cover - pillow optional
            LOGGER.debug("Pillow unavailable, writing fallback thumbnail: %s", exc)
            path.write_bytes(_FALLBACK_PNG)
            return 1, 1

        background = self._digest_color(digest)
        image = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        draw.text((24, 28), title[:48], fill=(255, 255, 255), font=font)
        if subtitle:
            draw.rectangle([(0, height - 92), (width, height)], fill=(16, 16, 16))
            draw.text(
                (24, height - 72),
                subtitle[:64],
                fill=(220, 220, 220),
                font=font,
            )
        draw.text(
            (24, height - 32),
            digest[:12],
            fill=(200, 200, 200),
            font=font,
        )
        image.save(path, format="PNG")
        return width, height

    def _digest_color(self, digest: str) -> tuple[int, int, int]:
        if len(digest) < 6:
            digest = f"{digest:0<6}"
        r = int(digest[0:2], 16)
        g = int(digest[2:4], 16)
        b = int(digest[4:6], 16)
        return tuple((component + 160) // 2 for component in (r, g, b))


__all__ = ["MiniVNThumbnail", "MiniVNThumbnailer"]
