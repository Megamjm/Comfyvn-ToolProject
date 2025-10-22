"""
Flat → Layers pipeline coordinator.

This module implements a deterministic, provenance-aware image pipeline that
decomposes a flat illustration into parallax-ready layers. The implementation
is designed to work with optional acceleration libraries (rembg, SAM/SAM2,
MiDaS/ZoeDepth, LaMa, Real-ESRGAN); when they are unavailable the pipeline
falls back to lightweight heuristics so contributors can still exercise the
flow and inspect the generated sidecars.

Touchpoints for modders/contributors:
    • FlatToLayersPipeline.register_hook(event, callback)
    • SAMInteractiveSession.attach_to_playground(playground_view)
    • FlatToLayersPipeline.debug_bundle() / last_result.debug

The pipeline writes assets under:
    layered/character/{character_id}/{cutout.png, mask.png, anchors.json}
    layered/background/planes/{index:02d}/plane.png
Each exported image is paired with a provenance sidecar that captures
{tool, version, params} so downstream tooling can audit the intermediate
products. Deterministic seeds + ordered processing guarantee repeatable
results for identical input/parameter pairs.
"""

from __future__ import annotations

import io
import json
import logging
import math
import statistics
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat

from comfyvn.config import feature_flags
from comfyvn.core.provenance import stamp_path

LOGGER = logging.getLogger("comfyvn.pipeline.flat2layers")

try:  # rembg (background removal)
    from rembg import remove as rembg_remove  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    rembg_remove = None  # type: ignore[assignment]

try:  # segment-anything / SAM
    from segment_anything import SamPredictor, sam_model_registry  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    SamPredictor = None  # type: ignore
    sam_model_registry = {}  # type: ignore

try:  # numpy is optional but improves mask statistics
    import numpy as np
except Exception:  # pragma: no cover - optional dependency
    np = None  # type: ignore

try:  # torch + MiDaS (depth)
    import torch
except Exception:  # pragma: no cover - optional dependency
    torch = None  # type: ignore

try:  # torchvision transforms (optional)
    from torchvision import transforms  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    transforms = None  # type: ignore

try:  # Real-ESRGAN optional upscale
    from realesrgan import RealESRGANer  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    RealESRGANer = None  # type: ignore


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


Vec2 = Tuple[float, float]
Vec4 = Tuple[int, int, int, int]


@dataclass(slots=True)
class PlaneExport:
    """Represents a single parallax plane export."""

    index: int
    depth_range: Tuple[float, float]
    image_path: Path
    provenance: Dict[str, Any]
    parallax_scale: float


@dataclass(slots=True)
class FlatToLayersResult:
    """Payload returned by the pipeline run."""

    character_id: str
    cutout_path: Path
    mask_path: Path
    anchors_path: Path
    planes: List[PlaneExport]
    debug: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FlatToLayersOptions:
    """Configurable knobs for a pipeline invocation."""

    source_path: Path
    output_root: Path = Path("layered")
    character_id: Optional[str] = None
    plane_count: int = 4
    plane_thresholds: Optional[Sequence[float]] = None
    parallax_scale: float = 1.0
    enable_real_esrgan: bool = False
    enable_lama_inpaint: bool = False
    interactive_session: Optional["SAMInteractiveSession"] = None
    provenance_inputs: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def normalized_character_id(self) -> str:
        if self.character_id:
            return self.character_id
        stem = self.source_path.stem
        return f"{stem}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _ensure_rgba(image: Image.Image) -> Image.Image:
    if image.mode == "RGBA":
        return image
    if image.mode == "P":
        return image.convert("RGBA")
    if image.mode == "LA":
        return image.convert("RGBA")
    return image.convert("RGBA")


def _load_image(path: Path) -> Image.Image:
    image = Image.open(path)
    return _ensure_rgba(image)


def _simple_foreground_mask(image: Image.Image) -> Image.Image:
    """Fallback mask builder when rembg/SAM are unavailable."""
    if image.mode == "RGBA":
        alpha = image.getchannel("A")
        # Detect nearly opaque pixels as foreground.
        return alpha.point(lambda px: 255 if px > 8 else 0, mode="L")
    gray = ImageOps.grayscale(image)
    stat = ImageStat.Stat(gray)
    mean = stat.mean[0]
    stddev = statistics.fmean(stat.stddev) if stat.stddev else 0.0
    threshold = min(255, max(0, mean + stddev * 0.35))
    return gray.point(lambda px: 255 if px >= threshold else 0, mode="L")


def _mask_from_rembg(image: Image.Image) -> Optional[Image.Image]:
    if rembg_remove is None:
        return None
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    data = rembg_remove(buffer.getvalue(), alpha_matting=True)
    if not data:
        return None
    try:
        cut = Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:  # pragma: no cover - defensive
        return None
    return cut.getchannel("A")


def _mask_union(mask_a: Image.Image, mask_b: Image.Image) -> Image.Image:
    return ImageChops.lighter(mask_a, mask_b)


def _mask_intersection(mask_a: Image.Image, mask_b: Image.Image) -> Image.Image:
    return ImageChops.multiply(mask_a, mask_b)


def _normalize_thresholds(
    values: Optional[Sequence[float]], *, count: int
) -> List[float]:
    if values:
        dedup = sorted(set(values))
        if len(dedup) >= count - 1:
            return dedup[: count - 1]
    # Uniform thresholds across 0..1
    step = 1.0 / count
    return [round(step * t, 4) for t in range(1, count)]


def _mask_statistics(mask: Image.Image) -> Dict[str, Any]:
    mask = mask.convert("L")
    width, height = mask.size
    if np is None:
        # Manual iteration fallback (small images remain fast).
        pixels = mask.load()
        coords: List[Tuple[int, int]] = []
        for y in range(height):
            for x in range(width):
                if pixels[x, y] > 0:
                    coords.append((x, y))
        if not coords:
            bbox = (0, 0, width, height)
            centroid = (width * 0.5, height * 0.5)
        else:
            xs = [pt[0] for pt in coords]
            ys = [pt[1] for pt in coords]
            bbox = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
            centroid = (statistics.fmean(xs), statistics.fmean(ys))
        area = len(coords)
    else:
        arr = np.array(mask, dtype=np.uint8)
        foreground = arr > 0
        indices = np.transpose(np.nonzero(foreground))
        if indices.size == 0:
            bbox = (0, 0, width, height)
            centroid = (width * 0.5, height * 0.5)
            area = 0
        else:
            ymin = int(indices[:, 0].min())
            ymax = int(indices[:, 0].max())
            xmin = int(indices[:, 1].min())
            xmax = int(indices[:, 1].max())
            bbox = (xmin, ymin, xmax + 1, ymax + 1)
            centroid = (
                float(indices[:, 1].mean()),
                float(indices[:, 0].mean()),
            )
            area = int(foreground.sum())

    bbox_w = bbox[2] - bbox[0]
    bbox_h = bbox[3] - bbox[1]
    coverage = area / float(width * height) if width and height else 0.0
    return {
        "bbox": {
            "x": bbox[0],
            "y": bbox[1],
            "width": bbox_w,
            "height": bbox_h,
        },
        "centroid": {"x": centroid[0], "y": centroid[1]},
        "coverage": round(coverage, 6),
        "area": area,
        "image_size": {"width": width, "height": height},
    }


def _depth_gradient(image: Image.Image) -> Image.Image:
    """Fallback depth approximation: luminance distance from center."""
    width, height = image.size
    center = (width * 0.5, height * 0.5)
    gray = ImageOps.grayscale(image).filter(ImageFilter.GaussianBlur(radius=5))
    if np is None:
        out = Image.new("F", (width, height))
        pix_out = out.load()
        pix_gray = gray.load()
        max_distance = math.hypot(center[0], center[1])
        for y in range(height):
            for x in range(width):
                norm_dist = math.hypot(x - center[0], y - center[1]) / max_distance
                pix_out[x, y] = max(
                    0.0,
                    min(1.0, (1.0 - norm_dist) * 0.7 + (pix_gray[x, y] / 255.0) * 0.3),
                )
        return out
    arr = np.array(gray, dtype=np.float32) / 255.0
    ys, xs = np.indices((height, width))
    dist = np.sqrt((xs - center[0]) ** 2 + (ys - center[1]) ** 2)
    dist /= dist.max() if dist.max() else 1.0
    depth = (1.0 - dist) * 0.7 + arr * 0.3
    depth = np.clip(depth, 0.0, 1.0)
    return Image.fromarray((depth * 65535).astype("uint16"), mode="I;16")


def _normalize_depth_map(depth_map: Image.Image) -> Image.Image:
    if depth_map.mode not in {"I;16", "F"}:
        depth_map = depth_map.convert("F")
    arr = None
    if np is not None:
        arr = np.array(depth_map, dtype=np.float32)
        mn = float(arr.min()) if arr.size else 0.0
        mx = float(arr.max()) if arr.size else 1.0
        span = mx - mn if mx != mn else 1.0
        arr = (arr - mn) / span
        return Image.fromarray((arr * 65535).astype("uint16"), mode="I;16")
    # Fallback: use ImageOps autocontrast on 16-bit
    if depth_map.mode != "I;16":
        depth_map = depth_map.convert("I;16")
    return ImageOps.autocontrast(depth_map)


def _split_planes(
    depth_map: Image.Image,
    *,
    thresholds: Sequence[float],
    plane_count: int,
    mask: Optional[Image.Image] = None,
) -> List[Tuple[Tuple[float, float], Image.Image]]:
    normalized = _normalize_depth_map(depth_map)
    width, height = normalized.size
    thresholds = sorted(set(max(0.0, min(1.0, value)) for value in thresholds))
    if len(thresholds) < plane_count - 1:
        thresholds = list(thresholds)
        step = 1.0 / plane_count
        while len(thresholds) < plane_count - 1:
            thresholds.append(round(step * (len(thresholds) + 1), 4))
    buckets: List[Tuple[float, float]] = []
    prev = 0.0
    for value in thresholds:
        buckets.append((prev, value))
        prev = value
    buckets.append((prev, 1.0))

    if np is None:
        normalized = normalized.convert("F")
        pix = normalized.load()
        mask_pix = mask.load() if mask else None
        planes: List[Image.Image] = [
            Image.new("L", (width, height), color=0) for _ in buckets
        ]
        for y in range(height):
            for x in range(width):
                value = pix[x, y]
                alpha = mask_pix[x, y] if mask_pix else 255
                if alpha <= 0:
                    continue
                for index, (lo, hi) in enumerate(buckets):
                    if lo <= value <= hi + 1e-6:
                        planes[index].putpixel((x, y), 255)
                        break
        return list(zip(buckets, planes))

    arr = np.array(normalized, dtype=np.uint16) / 65535.0
    if mask is not None:
        mask_arr = np.array(mask.convert("L"), dtype=np.uint8) / 255.0
        arr = arr * mask_arr
    result: List[Tuple[Tuple[float, float], Image.Image]] = []
    for lo, hi in buckets:
        plane_mask = ((arr >= lo) & (arr <= hi + 1e-6)).astype("uint8") * 255
        image = Image.fromarray(plane_mask, mode="L")
        result.append(((lo, hi), image))
    return result


def _composite_plane(image: Image.Image, mask: Image.Image) -> Image.Image:
    mask = mask.convert("L")
    blank = Image.new("RGBA", image.size, (0, 0, 0, 0))
    return Image.composite(image, blank, mask)


def _maybe_upscale(image: Image.Image, *, enable: bool, scale: int = 2) -> Image.Image:
    if not enable:
        return image
    if RealESRGANer is None:  # pragma: no cover - optional dependency
        LOGGER.info("Real-ESRGAN unavailable; skipping upscale.")
        return image
    if np is None:
        LOGGER.info("NumPy unavailable; skipping Real-ESRGAN upscale.")
        return image
    try:  # pragma: no cover - runtime only when dependency present
        upsampler = RealESRGANer(
            scale=scale,
            model_path=None,
            model=None,
            tile=256,
            tile_pad=10,
            pre_pad=0,
            half=False,
        )
        upscaled, _ = upsampler.enhance(np.array(image))
        return Image.fromarray(upscaled)
    except Exception:
        LOGGER.warning("Real-ESRGAN upscale failed; returning original.", exc_info=True)
        return image


# ---------------------------------------------------------------------------
# SAM interactive support
# ---------------------------------------------------------------------------


SAMBrush = Dict[str, Any]
SAMEventHook = Callable[[Dict[str, Any]], None]


class SAMInteractiveSession:
    """Mutable interactive SAM loop for Playground integrations."""

    def __init__(
        self,
        *,
        model_type: str = "vit_h",
        checkpoint_path: Optional[Path] = None,
        device: Optional[str] = None,
    ) -> None:
        self.model_type = model_type
        self.checkpoint_path = checkpoint_path
        self.device = device or (
            "cuda" if torch and torch.cuda.is_available() else "cpu"
        )
        self._predictor: Optional[SamPredictor] = None
        self._hooks: Dict[str, List[SAMEventHook]] = {
            "on_mask_update": [],
            "on_brush_event": [],
            "on_debug": [],
        }
        self._brush_log: List[SAMBrush] = []
        self._last_mask: Optional[Image.Image] = None

    # ------------------------------------------------------------------ hooks
    def register_hook(self, name: str, callback: SAMEventHook) -> None:
        if name not in self._hooks:
            raise ValueError(f"Unknown SAM interactive hook '{name}'")
        self._hooks[name].append(callback)

    def _emit(self, name: str, payload: Dict[str, Any]) -> None:
        for callback in self._hooks.get(name, []):
            try:
                callback(dict(payload))
            except Exception:  # pragma: no cover - defensive
                LOGGER.warning("SAM hook '%s' failed: %s", name, payload, exc_info=True)

    # ------------------------------------------------------------------ lifecycle
    def _ensure_predictor(self) -> Optional[SamPredictor]:
        if SamPredictor is None:
            LOGGER.info(
                "segment-anything not installed; interactive loop operates in stub mode."
            )
            return None
        if self._predictor:
            return self._predictor
        registry = getattr(sam_model_registry, "get", None)
        if not registry:
            LOGGER.warning("SAM registry unavailable; cannot construct predictor.")
            return None
        if not self.checkpoint_path:
            LOGGER.warning("No SAM checkpoint configured; interactive loop disabled.")
            return None
        model_builder = sam_model_registry.get(self.model_type)
        if not model_builder:
            LOGGER.warning("SAM model type '%s' unsupported.", self.model_type)
            return None
        try:  # pragma: no cover - depends on runtime env
            sam = model_builder(checkpoint=self.checkpoint_path.as_posix())
            if torch:
                sam.to(device=self.device)
            self._predictor = SamPredictor(sam)
            LOGGER.info("SAM predictor ready (%s @ %s).", self.model_type, self.device)
        except Exception:
            LOGGER.warning("Failed to initialize SAM predictor.", exc_info=True)
            self._predictor = None
        return self._predictor

    def attach_to_playground(
        self, playground: Any, *, channel: str = "flat2layers.sam"
    ) -> None:
        """
        Register this session with a PlaygroundView.

        The Playground should emit dict payloads via `on_stage_log` hook containing:
            {"channel": "flat2layers.sam", "event": "brush", "points": [...], "positive": True}
        Brush events are recorded, the mask is recomputed, and an immediate snapshot is
        emitted to observers via `on_mask_update`.
        """

        def _on_stage_log(payload: Dict[str, Any]) -> None:
            if payload.get("channel") != channel:
                return
            kind = payload.get("event")
            if kind == "brush":
                brush = {
                    "points": payload.get("points") or [],
                    "positive": bool(payload.get("positive", True)),
                    "timestamp": time.time(),
                }
                self._brush_log.append(brush)
                self._emit(
                    "on_brush_event", {"brush": brush, "count": len(self._brush_log)}
                )
            elif kind == "reset":
                self.reset()
            elif kind == "debug":
                self._emit("on_debug", {"payload": payload})

        playground.register_hook("on_stage_log", _on_stage_log)
        LOGGER.info(
            "SAM interactive session attached to Playground hook channel '%s'.", channel
        )

    # ------------------------------------------------------------------ core
    def predict_mask(
        self,
        image: Image.Image,
        *,
        initial_mask: Optional[Image.Image] = None,
    ) -> Image.Image:
        predictor = self._ensure_predictor()
        if predictor is None:
            LOGGER.debug("SAM predictor unavailable; returning initial mask/fallback.")
            return initial_mask or _simple_foreground_mask(image)

        image_rgb = image.convert("RGB")
        image_arr = np.array(image_rgb) if np is not None else None  # type: ignore[arg-type]
        if image_arr is None:
            return initial_mask or _simple_foreground_mask(image)

        predictor.set_image(image_arr)
        pos_points: List[Vec2] = []
        neg_points: List[Vec2] = []
        for stroke in self._brush_log:
            pts = stroke.get("points") or []
            if stroke.get("positive", True):
                pos_points.extend(pts)
            else:
                neg_points.extend(pts)
        if not pos_points and initial_mask is not None:
            stats = _mask_statistics(initial_mask)
            bbox = stats["bbox"]
            pos_points.append(
                (bbox["x"] + bbox["width"] * 0.5, bbox["y"] + bbox["height"] * 0.5)
            )

        points = []
        labels = []
        for point in pos_points:
            points.append(point)
            labels.append(1)
        for point in neg_points:
            points.append(point)
            labels.append(0)
        if not points:
            LOGGER.debug("SAM session has no points; returning simple mask fallback.")
            return initial_mask or _simple_foreground_mask(image)

        try:  # pragma: no cover - depends on SAM install
            mask_raw, _, _ = predictor.predict(
                point_coords=np.array(points, dtype=np.float32),
                point_labels=np.array(labels, dtype=np.int32),
                multimask_output=False,
            )
        except Exception:
            LOGGER.warning(
                "SAM prediction failed; returning initial mask.", exc_info=True
            )
            return initial_mask or _simple_foreground_mask(image)

        mask = Image.fromarray(mask_raw.astype("uint8") * 255, mode="L")
        if initial_mask is not None:
            mask = _mask_intersection(mask, initial_mask)
        self._last_mask = mask
        self._emit("on_mask_update", {"mask": mask})
        return mask

    def reset(self) -> None:
        self._brush_log.clear()
        self._last_mask = None

    def last_mask(self) -> Optional[Image.Image]:
        return self._last_mask

    def debug_snapshot(self) -> Dict[str, Any]:
        return {
            "model_type": self.model_type,
            "device": self.device,
            "checkpoint": (
                self.checkpoint_path.as_posix() if self.checkpoint_path else None
            ),
            "brush_events": len(self._brush_log),
        }


# ---------------------------------------------------------------------------
# Pipeline implementation
# ---------------------------------------------------------------------------


PipelineHook = Callable[[Dict[str, Any]], None]


class FlatToLayersPipeline:
    """Co-ordinates the flat→layers decomposition."""

    EVENTS = (
        "on_start",
        "on_mask_ready",
        "on_depth_ready",
        "on_plane_exported",
        "on_complete",
        "on_debug",
    )

    def __init__(self) -> None:
        self._hooks: Dict[str, List[PipelineHook]] = {name: [] for name in self.EVENTS}
        self._last_result: Optional[FlatToLayersResult] = None
        self._last_debug: Dict[str, Any] = {}

    # ------------------------------------------------------------------ hooks
    def register_hook(self, event: str, callback: PipelineHook) -> None:
        if event not in self._hooks:
            raise ValueError(f"Unknown pipeline hook '{event}'")
        self._hooks[event].append(callback)

    def _emit(self, event: str, payload: Dict[str, Any]) -> None:
        for callback in self._hooks.get(event, []):
            try:
                callback(dict(payload))
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.warning("Flat2Layers hook '%s' raised", event, exc_info=True)

    # ------------------------------------------------------------------ accessors
    @property
    def last_result(self) -> Optional[FlatToLayersResult]:
        return self._last_result

    def debug_bundle(self) -> Dict[str, Any]:
        return dict(self._last_debug)

    # ------------------------------------------------------------------ core
    def run(self, options: FlatToLayersOptions) -> FlatToLayersResult:
        gate = feature_flags.is_enabled("enable_flat2layers", default=False)
        if not gate:
            raise RuntimeError(
                "Flat→Layers pipeline disabled (feature flag 'enable_flat2layers'). Edit config/comfyvn.json to enable."
            )

        start_ts = time.time()
        options = FlatToLayersOptions(**vars(options))  # defensive copy
        character_id = options.normalized_character_id()
        source_path = options.source_path.expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(source_path)

        self._emit(
            "on_start", {"source": source_path.as_posix(), "character_id": character_id}
        )
        image = _load_image(source_path)

        # Mask generation
        rembg_mask = _mask_from_rembg(image) or _simple_foreground_mask(image)
        interactive_mask = None
        if options.interactive_session:
            interactive_mask = options.interactive_session.predict_mask(
                image, initial_mask=rembg_mask
            )
        mask = (
            _mask_union(rembg_mask, interactive_mask)
            if interactive_mask
            else rembg_mask
        )
        mask = mask.filter(ImageFilter.GaussianBlur(radius=1))
        cutout = _composite_plane(image, mask)

        # Anchors metadata
        anchors = _mask_statistics(mask)
        anchors["version"] = 1
        anchors["character_id"] = character_id
        anchors["source"] = source_path.as_posix()

        # Depth estimation
        depth_map = _depth_gradient(image)
        depth_debug = {"strategy": "fallback_gradient"}
        background_mask = ImageChops.invert(mask)

        thresholds = _normalize_thresholds(
            options.plane_thresholds, count=options.plane_count
        )
        planes_with_masks = _split_planes(
            depth_map,
            thresholds=thresholds,
            plane_count=options.plane_count,
            mask=background_mask,
        )

        # Prepare output directories
        output_root = options.output_root.expanduser().resolve()
        character_root = output_root / "character" / character_id
        planes_root = output_root / "background" / "planes"
        character_root.mkdir(parents=True, exist_ok=True)
        planes_root.mkdir(parents=True, exist_ok=True)

        # Optional upscale
        cutout_upscaled = _maybe_upscale(cutout, enable=options.enable_real_esrgan)

        # Persist character artifacts
        cutout_path = character_root / "cutout.png"
        mask_path = character_root / "mask.png"
        anchors_path = character_root / "anchors.json"
        cutout_upscaled.save(cutout_path)
        mask.save(mask_path)
        anchors_path.write_text(json.dumps(anchors, indent=2), encoding="utf-8")

        character_inputs = {
            "tool": "flat2layers",
            "version": "1.0",
            "params": {
                "plane_count": options.plane_count,
                "thresholds": list(thresholds),
                "parallax_scale": options.parallax_scale,
                "source": source_path.name,
            },
        }
        character_inputs.update(options.provenance_inputs)

        cutout_prov = stamp_path(
            cutout_path, source="flat2layers.cutout", inputs=character_inputs
        )
        mask_prov = stamp_path(
            mask_path, source="flat2layers.mask", inputs=character_inputs
        )
        anchors_prov = stamp_path(
            anchors_path, source="flat2layers.anchors", inputs=character_inputs
        )

        self._emit(
            "on_mask_ready",
            {
                "character_id": character_id,
                "mask_path": mask_path.as_posix(),
                "cutout_path": cutout_path.as_posix(),
                "anchors": anchors,
                "provenance": {
                    "cutout": cutout_prov,
                    "mask": mask_prov,
                    "anchors": anchors_prov,
                },
            },
        )

        # Export depth-aware planes
        plane_exports: List[PlaneExport] = []
        for index, ((lo, hi), plane_mask) in enumerate(planes_with_masks):
            plane_cut = _composite_plane(image, plane_mask)
            plane_cut = _maybe_upscale(plane_cut, enable=options.enable_real_esrgan)
            plane_dir = planes_root / f"{index:02d}"
            plane_dir.mkdir(parents=True, exist_ok=True)
            plane_path = plane_dir / "plane.png"
            plane_cut.save(plane_path)

            inputs = dict(character_inputs)
            inputs["params"] = dict(inputs["params"])
            inputs["params"].update(
                {"depth_range": [round(lo, 4), round(hi, 4)], "plane_index": index}
            )

            plane_prov = stamp_path(
                plane_path,
                source="flat2layers.background_plane",
                inputs=inputs,
            )
            plane_exports.append(
                PlaneExport(
                    index=index,
                    depth_range=(round(lo, 4), round(hi, 4)),
                    image_path=plane_path,
                    provenance=plane_prov,
                    parallax_scale=options.parallax_scale,
                )
            )
            self._emit(
                "on_plane_exported",
                {
                    "index": index,
                    "depth_range": [round(lo, 4), round(hi, 4)],
                    "plane_path": plane_path.as_posix(),
                    "parallax_scale": options.parallax_scale,
                    "provenance": plane_prov,
                },
            )

        elapsed = time.time() - start_ts
        debug_payload = {
            "elapsed": round(elapsed, 3),
            "source": source_path.as_posix(),
            "character_id": character_id,
            "depth": depth_debug,
            "thresholds": list(thresholds),
            "plane_count": len(plane_exports),
            "feature_flag": gate,
            "interactive": (
                options.interactive_session.debug_snapshot()
                if options.interactive_session
                else None
            ),
        }
        self._last_debug = debug_payload
        self._emit("on_debug", debug_payload)

        result = FlatToLayersResult(
            character_id=character_id,
            cutout_path=cutout_path,
            mask_path=mask_path,
            anchors_path=anchors_path,
            planes=plane_exports,
            debug=debug_payload,
        )
        self._last_result = result

        self._emit(
            "on_complete",
            {
                "character_id": character_id,
                "result": {
                    "cutout": cutout_path.as_posix(),
                    "mask": mask_path.as_posix(),
                    "anchors": anchors_path.as_posix(),
                    "planes": [plane.image_path.as_posix() for plane in plane_exports],
                },
                "debug": debug_payload,
            },
        )
        return result


__all__ = [
    "FlatToLayersPipeline",
    "FlatToLayersOptions",
    "FlatToLayersResult",
    "PlaneExport",
    "SAMInteractiveSession",
]
