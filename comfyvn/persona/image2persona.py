from __future__ import annotations

import dataclasses
import hashlib
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from PIL import Image, ImageOps, ImageStat

from .style_suggestions import StyleSuggestionRegistry, suggest_styles

RGBTuple = Tuple[int, int, int]
Point = Tuple[float, float]

ANALYZER_VERSION = "p6.image2persona.v1"


class ImageLoadError(RuntimeError):
    """Raised when an input image cannot be processed."""


@dataclass(slots=True)
class PersonaImageOptions:
    palette_min: int = 5
    palette_max: int = 8
    quantize_edge: int = 256
    anchor_probe_size: int = 96
    debug: bool = False
    default_species: str = "unspecified"
    allow_face_anchor_bias: float = 0.22
    allow_hand_anchor_bias: float = 0.55
    allow_feet_anchor_bias: float = 0.88
    style_registry: Optional[StyleSuggestionRegistry] = None
    hooks: Dict[str, Callable[..., Any]] = field(default_factory=dict)

    def clamp_palette(self, colors: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if len(colors) <= self.palette_max:
            return list(colors)
        trimmed = sorted(colors, key=lambda item: (-item["ratio"], item["hex"]))
        return trimmed[: self.palette_max]


@dataclass(slots=True)
class PersonaImageReport:
    source: str
    digest: str
    width: int
    height: int
    palette: List[Dict[str, Any]]
    appearance: Dict[str, Any]
    anchors: Dict[str, Any]
    expressions: Dict[str, Any]
    debug: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class PersonaSuggestion:
    persona_id: Optional[str]
    summary: Dict[str, Any]
    per_image: List[PersonaImageReport]
    provenance: Dict[str, Any]

    def as_json(self, *, indent: Optional[int] = 2) -> str:
        payload = {
            "persona_id": self.persona_id,
            "summary": self.summary,
            "per_image": [dataclasses.asdict(entry) for entry in self.per_image],
            "provenance": self.provenance,
            "version": ANALYZER_VERSION,
        }
        return json.dumps(payload, indent=indent, ensure_ascii=False)


class ImagePersonaAnalyzer:
    """Extracts appearance hints, palette, anchors, and expressions from persona images."""

    def __init__(self, options: Optional[PersonaImageOptions] = None) -> None:
        self.options = options or PersonaImageOptions()
        if not 1 <= self.options.palette_min <= self.options.palette_max:
            raise ValueError("palette_min must be >=1 and <= palette_max")
        self.style_registry = (
            self.options.style_registry
            if self.options.style_registry
            else StyleSuggestionRegistry.default()
        )

    # Public API ------------------------------------------------------
    def analyze_images(
        self,
        sources: Sequence[Union[str, Path, Image.Image]],
        *,
        persona_id: Optional[str] = None,
    ) -> PersonaSuggestion:
        if not sources:
            raise ValueError("at least one image is required")

        reports: List[PersonaImageReport] = []
        for idx, source in enumerate(sources):
            report = self._analyze_single(source, index=idx)
            reports.append(report)

        summary, provenance = self._merge_reports(reports, persona_id=persona_id)
        return PersonaSuggestion(
            persona_id=persona_id,
            summary=summary,
            per_image=reports,
            provenance=provenance,
        )

    def merge_into_persona_profile(
        self,
        persona_profile: MutableMapping[str, Any],
        suggestion: PersonaSuggestion,
        *,
        prefer_existing: bool = True,
    ) -> MutableMapping[str, Any]:
        """Merge the generated suggestion into a persona profile dict."""
        target = dict(persona_profile or {})
        metadata = target.setdefault("metadata", {})
        existing = metadata.get("image2persona") if prefer_existing else None
        if existing:
            merged_summary = self._combine_summaries(existing, suggestion.summary)
        else:
            merged_summary = suggestion.summary
        metadata["image2persona"] = merged_summary
        metadata["image2persona_provenance"] = suggestion.provenance
        if suggestion.persona_id and not target.get("id"):
            target["id"] = suggestion.persona_id
        return target

    # Internal helpers ------------------------------------------------
    def _analyze_single(
        self,
        source: Union[str, Path, Image.Image],
        *,
        index: int = 0,
    ) -> PersonaImageReport:
        image, label = self._load_image(source, index=index)
        digest = self._digest(image)
        palette = self._extract_palette(image)
        appearance = self._extract_appearance(image, palette)
        anchors = self._estimate_anchors(image)
        expressions = self._estimate_expressions(image, appearance, anchors)
        debug_payload = None
        if self.options.debug:
            debug_payload = {
                "metrics": self._calc_metrics(image),
                "palette_names": [entry["name"] for entry in palette],
                "anchors": anchors,
                "appearance": appearance,
            }
        return PersonaImageReport(
            source=label,
            digest=digest,
            width=image.width,
            height=image.height,
            palette=palette,
            appearance=appearance,
            anchors=anchors,
            expressions=expressions,
            debug=debug_payload,
        )

    def _load_image(
        self, source: Union[str, Path, Image.Image], *, index: int
    ) -> Tuple[Image.Image, str]:
        label = f"in-memory://{index}"
        if isinstance(source, Image.Image):
            image = source.copy()
            label = getattr(source, "filename", label)
        else:
            path = Path(source)
            if not path.exists():
                raise ImageLoadError(f"input image not found: {source}")
            label = str(path)
            image = Image.open(path)
        try:
            image = ImageOps.exif_transpose(image).convert("RGB")
        except Exception as exc:  # pragma: no cover - defensive
            raise ImageLoadError(f"unable to normalize image: {label}") from exc
        return image, label

    def _digest(self, image: Image.Image) -> str:
        payload = f"{ANALYZER_VERSION}:{image.width}x{image.height}".encode("utf-8")
        payload += image.tobytes()
        return hashlib.sha1(payload).hexdigest()

    def _extract_palette(self, image: Image.Image) -> List[Dict[str, Any]]:
        edge = self.options.quantize_edge
        target_w, target_h = image.size
        scale = max(target_w, target_h) / float(edge)
        if scale > 1.0:
            resized = image.resize(
                (
                    max(32, int(target_w / scale)),
                    max(32, int(target_h / scale)),
                ),
                Image.Resampling.LANCZOS,
            )
        else:
            resized = image

        quantized = resized.quantize(
            colors=max(self.options.palette_max, 2),
            method=Image.Mediancut,
            dither=Image.Dither.NONE,
        )
        palette_raw = quantized.getpalette() or []
        color_counts = quantized.getcolors() or []
        total = sum(count for count, _ in color_counts) or 1
        swatches: List[Dict[str, Any]] = []
        for count, idx in color_counts:
            base = idx * 3
            if base + 3 > len(palette_raw):
                continue
            rgb = tuple(palette_raw[base : base + 3])  # type: ignore[assignment]
            ratio = count / total
            swatches.append(
                {
                    "hex": "#%02x%02x%02x" % rgb,
                    "rgb": list(rgb),
                    "ratio": round(ratio, 4),
                    "luma": round(_luma(rgb), 4),
                    "name": _color_token(rgb),
                }
            )
        if not swatches:
            # fallback to average color
            avg = tuple(int(round(x)) for x in ImageStat.Stat(image).mean[:3])
            swatches.append(
                {
                    "hex": "#%02x%02x%02x" % avg,
                    "rgb": list(avg),
                    "ratio": 1.0,
                    "luma": round(_luma(avg), 4),
                    "name": _color_token(avg),
                }
            )
        swatches = sorted(swatches, key=lambda entry: (-entry["ratio"], entry["hex"]))
        swatches = self.options.clamp_palette(swatches)

        palette_hook = self.options.hooks.get("palette")
        if callable(palette_hook):
            custom = palette_hook(image=image, palette=list(swatches))
            if isinstance(custom, Sequence) and not isinstance(custom, (str, bytes)):
                swatches = list(custom)

        return swatches

    def _extract_appearance(
        self,
        image: Image.Image,
        palette: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        stats = ImageStat.Stat(image)
        avg_rgb = tuple(int(round(value)) for value in stats.mean[:3])
        avg_luma = _luma(avg_rgb)
        saturation = _approx_saturation(avg_rgb)
        palette_tokens = [entry["name"] for entry in palette]
        primary = palette[0] if palette else None

        colorways = _rank_colorways(palette)
        accents = [entry["name"] for entry in palette if entry["ratio"] <= 0.18]

        clothing = []
        if len(palette) >= 5:
            clothing.append("complex_pattern")
        if saturation < 0.18:
            clothing.append("muted")
        elif saturation > 0.42:
            clothing.append("vibrant")
        if primary and primary["ratio"] > 0.45:
            clothing.append("monotone")
        if not clothing:
            clothing.append("minimalist")

        fur_skin = _infer_skin_token(avg_rgb, palette_tokens)

        hooks = self.options.hooks.get("appearance")
        manual = hooks(image=image, palette=palette) if callable(hooks) else {}

        appearance = {
            "species": manual.get("species") or self.options.default_species,
            "fur_skin": manual.get("fur_skin") or fur_skin,
            "colorways": manual.get("colorways") or colorways,
            "clothing_motifs": manual.get("clothing_motifs") or clothing,
            "accent_colors": manual.get("accent_colors") or accents,
            "primary_color": primary["name"] if primary else None,
            "average_luma": round(avg_luma, 4),
            "average_saturation": round(saturation, 4),
            "palette_tokens": palette_tokens,
        }
        return appearance

    def _estimate_anchors(self, image: Image.Image) -> Dict[str, Any]:
        mask_data, bbox = _estimate_subject_bbox(image, self.options.anchor_probe_size)
        if bbox is None:
            width, height = image.size
            bbox = (0.25, 0.15, 0.75, 0.95)
        left, top, right, bottom = bbox
        cx = (left + right) / 2.0
        cy = (top + bottom) / 2.0
        height = bottom - top

        def anchor_point(bias_y: float, bias_x: float = 0.5) -> Dict[str, Any]:
            x = left + (right - left) * bias_x
            y = top + height * bias_y
            return {
                "xy": [round(x, 4), round(y, 4)],
                "confidence": mask_data.get("confidence", 0.4),
            }

        anchors: Dict[str, Any] = {
            "bounding_box": {
                "normalized": [
                    round(left, 4),
                    round(top, 4),
                    round(right, 4),
                    round(bottom, 4),
                ],
                "confidence": mask_data.get("confidence", 0.4),
            },
            "face": anchor_point(self.options.allow_face_anchor_bias),
            "hands": {
                "left": anchor_point(self.options.allow_hand_anchor_bias, 0.3),
                "right": anchor_point(self.options.allow_hand_anchor_bias, 0.7),
            },
            "feet": {
                "left": anchor_point(self.options.allow_feet_anchor_bias, 0.35),
                "right": anchor_point(self.options.allow_feet_anchor_bias, 0.65),
            },
        }
        anchor_hook = self.options.hooks.get("anchors")
        if callable(anchor_hook):
            override = anchor_hook(image=image, anchors=dict(anchors))
            if isinstance(override, dict):
                anchors.update(override)
        return anchors

    def _estimate_expressions(
        self,
        image: Image.Image,
        appearance: Dict[str, Any],
        anchors: Dict[str, Any],
    ) -> Dict[str, Any]:
        stats = ImageStat.Stat(image)
        mean_rgb = stats.mean[:3]
        std_rgb = stats.stddev[:3]
        contrast = sum(std_rgb) / (sum(mean_rgb) + 1e-6)
        warmth = mean_rgb[0] - mean_rgb[2]
        brightness = sum(mean_rgb) / 3.0
        accent_warm = any(
            token.startswith("warm") for token in appearance.get("palette_tokens", [])
        )
        accent_cool = any(
            token.startswith("cool") for token in appearance.get("palette_tokens", [])
        )

        expressions = {
            "neutral": {
                "mood": "neutral",
                "confidence": round(max(0.35, min(0.75, 1.0 - contrast)), 3),
                "anchor": anchors.get("face"),
            },
            "blink": {
                "mood": "calm",
                "trigger": "idle_cycle",
                "confidence": 0.35,
            },
        }

        if brightness > 150 and warmth > 5:
            expressions["smile"] = {
                "mood": "positive",
                "trigger": "greeting",
                "confidence": round(min(0.8, 0.45 + warmth / 255.0), 3),
            }
        if contrast > 0.45 or accent_cool:
            expressions["anger"] = {
                "mood": "intense",
                "trigger": "conflict",
                "confidence": round(min(0.7, 0.35 + contrast * 0.8), 3),
            }
        if accent_warm and contrast < 0.4:
            expressions.setdefault(
                "soft_smile",
                {
                    "mood": "gentle",
                    "trigger": "affection",
                    "confidence": round(min(0.6, 0.3 + brightness / 400.0), 3),
                },
            )
        expression_hook = self.options.hooks.get("expressions")
        if callable(expression_hook):
            override = expression_hook(
                image=image,
                expressions=dict(expressions),
                appearance=appearance,
                anchors=anchors,
            )
            if isinstance(override, dict):
                expressions.update(override)
        return expressions

    def _merge_reports(
        self,
        reports: Sequence[PersonaImageReport],
        *,
        persona_id: Optional[str],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        appearance = _merge_appearance([r.appearance for r in reports])
        palette = _merge_palette(
            [r.palette for r in reports], max_size=self.options.palette_max
        )
        anchors = _merge_anchors([r.anchors for r in reports])
        expressions = _merge_expressions([r.expressions for r in reports])
        conflicts = _detect_conflicts([r.appearance for r in reports])

        style = suggest_styles(
            appearance,
            palette,
            registry=self.style_registry,
        )

        summary = {
            "persona_id": persona_id,
            "appearance": appearance,
            "palette": palette,
            "pose_anchors": anchors,
            "expression_set": expressions,
            "style": style,
            "conflicts": conflicts,
        }

        summary_hook = self.options.hooks.get("summary")
        if callable(summary_hook):
            summary = summary_hook(summary=summary, reports=reports) or summary

        provenance = {
            "algorithm": ANALYZER_VERSION,
            "images": [
                {
                    "source": report.source,
                    "digest": report.digest,
                    "dimensions": [report.width, report.height],
                }
                for report in reports
            ],
            "summary_digest": hashlib.sha1(
                json.dumps(summary, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest(),
        }

        return summary, provenance

    def _combine_summaries(
        self, existing: Dict[str, Any], new_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        combined = dict(existing or {})
        combined.update(new_summary or {})
        return combined

    def _calc_metrics(self, image: Image.Image) -> Dict[str, Any]:
        stat = ImageStat.Stat(image)
        mean_rgb = stat.mean[:3]
        std_rgb = stat.stddev[:3]
        return {
            "mean_rgb": [round(x, 3) for x in mean_rgb],
            "std_rgb": [round(x, 3) for x in std_rgb],
            "contrast": round(
                sum(std_rgb) / (sum(mean_rgb) + 1e-6),
                4,
            ),
            "dimensions": [image.width, image.height],
        }


# Palette helpers ------------------------------------------------------
def _luma(rgb: RGBTuple) -> float:
    r, g, b = rgb
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def _approx_saturation(rgb: RGBTuple) -> float:
    r, g, b = rgb
    max_v = max(rgb)
    min_v = min(rgb)
    if max_v == 0:
        return 0.0
    return (max_v - min_v) / max_v


def _color_token(rgb: RGBTuple) -> str:
    r, g, b = rgb
    luma = _luma(rgb)
    saturation = _approx_saturation(rgb)
    hue = _hue(rgb)

    if luma < 0.08:
        return "neutral:black"
    if luma > 0.92:
        return "neutral:white"
    if saturation < 0.15:
        if luma < 0.4:
            return "neutral:charcoal"
        if luma < 0.68:
            return "neutral:stone"
        return "neutral:ivory"

    if hue < 30 or hue >= 330:
        return "warm:red"
    if 30 <= hue < 75:
        return "warm:orange"
    if 75 <= hue < 150:
        return "warm:yellow" if luma > 0.5 else "warm:olive"
    if 150 <= hue < 210:
        return "cool:green"
    if 210 <= hue < 255:
        return "cool:teal"
    if 255 <= hue < 285:
        return "cool:blue"
    if 285 <= hue < 330:
        return "warm:magenta"
    return "neutral:stone"


def _hue(rgb: RGBTuple) -> float:
    r, g, b = (value / 255.0 for value in rgb)
    max_v = max(r, g, b)
    min_v = min(r, g, b)
    delta = max_v - min_v
    if delta == 0:
        return 0.0
    if max_v == r:
        hue = (g - b) / delta % 6
    elif max_v == g:
        hue = (b - r) / delta + 2
    else:
        hue = (r - g) / delta + 4
    return (hue * 60.0) % 360.0


def _rank_colorways(palette: Sequence[Dict[str, Any]]) -> List[str]:
    ranked: List[Tuple[float, str]] = []
    for entry in palette:
        ratio = entry["ratio"]
        group = entry["name"]
        if ratio > 0.4:
            bucket = "primary"
        elif ratio > 0.2:
            bucket = "secondary"
        else:
            bucket = "accent"
        ranked.append((ratio, f"{bucket}:{group}"))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[1] for item in ranked]


def _infer_skin_token(avg_rgb: RGBTuple, palette_tokens: Sequence[str]) -> str:
    luma = _luma(avg_rgb)
    saturation = _approx_saturation(avg_rgb)
    warm = any(token.startswith("warm") for token in palette_tokens)
    cool = any(token.startswith("cool") for token in palette_tokens)

    if saturation < 0.12:
        if luma > 0.7:
            return "skin:fair"
        if luma > 0.5:
            return "skin:medium"
        return "skin:deep"
    if warm and not cool:
        return "fur:warm_tone"
    if cool and not warm:
        return "fur:cool_tone"
    return "skin:balanced"


# Anchor helpers -------------------------------------------------------
def _estimate_subject_bbox(
    image: Image.Image, probe_size: int
) -> Tuple[Dict[str, Any], Optional[Tuple[float, float, float, float]]]:
    grayscale = ImageOps.grayscale(image)
    resized = grayscale.resize(
        (
            probe_size,
            max(16, int(probe_size * (grayscale.height / grayscale.width or 1))),
        ),
        Image.Resampling.BILINEAR,
    )
    histogram = resized.histogram()
    total = sum(histogram) or 1
    cutoff = total * 0.88
    cumulative = 0
    threshold = 255
    for value, count in enumerate(histogram):
        cumulative += count
        if cumulative >= cutoff:
            threshold = value
            break

    pixels = list(resized.getdata())
    width, height = resized.size
    subject_pixels: List[Tuple[int, int]] = []
    for idx, intensity in enumerate(pixels):
        if intensity <= threshold:
            x = idx % width
            y = idx // width
            subject_pixels.append((x, y))
    if not subject_pixels:
        return {"confidence": 0.1, "threshold": threshold}, None

    xs = [p[0] for p in subject_pixels]
    ys = [p[1] for p in subject_pixels]
    left = min(xs) / width
    right = (max(xs) + 1) / width
    top = min(ys) / height
    bottom = (max(ys) + 1) / height
    coverage = len(subject_pixels) / (width * height)
    confidence = round(min(0.9, max(0.25, coverage * 1.2)), 4)
    return {
        "confidence": confidence,
        "threshold": threshold,
        "coverage": round(coverage, 4),
    }, (left, top, right, bottom)


# Merge helpers --------------------------------------------------------
def _merge_appearance(items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    species = _most_common(
        [item.get("species") for item in items if item.get("species")]
    )
    fur_skin = _most_common(
        [item.get("fur_skin") for item in items if item.get("fur_skin")]
    )
    colorways = _merge_ordered_lists([item.get("colorways") for item in items])
    clothing = _merge_ordered_lists([item.get("clothing_motifs") for item in items])
    accents = _merge_ordered_lists([item.get("accent_colors") for item in items])
    tokens = _merge_ordered_lists([item.get("palette_tokens") for item in items])

    avg_luma = (
        statistics.mean([item.get("average_luma", 0.0) for item in items])
        if items
        else 0.0
    )
    avg_sat = (
        statistics.mean([item.get("average_saturation", 0.0) for item in items])
        if items
        else 0.0
    )
    primary_color = _most_common(
        [item.get("primary_color") for item in items if item.get("primary_color")]
    )

    result.update(
        {
            "species": species,
            "fur_skin": fur_skin,
            "colorways": colorways,
            "clothing_motifs": clothing,
            "accent_colors": accents,
            "palette_tokens": tokens,
            "primary_color": primary_color,
            "average_luma": round(avg_luma, 4),
            "average_saturation": round(avg_sat, 4),
        }
    )
    return result


def _merge_palette(
    palettes: Sequence[Sequence[Dict[str, Any]]], *, max_size: int
) -> List[Dict[str, Any]]:
    accumulator: Dict[str, Dict[str, Any]] = {}
    for palette in palettes:
        for swatch in palette:
            key = swatch["hex"]
            entry = accumulator.setdefault(
                key,
                {
                    "hex": swatch["hex"],
                    "rgb": swatch["rgb"],
                    "luma": swatch["luma"],
                    "ratio": 0.0,
                    "name": swatch.get("name"),
                    "sources": 0,
                },
            )
            entry["ratio"] += swatch["ratio"]
            entry["sources"] += 1

    total = sum(entry["ratio"] for entry in accumulator.values()) or 1.0
    merged = []
    for entry in accumulator.values():
        ratio = entry["ratio"] / total
        merged.append(
            {
                "hex": entry["hex"],
                "rgb": entry["rgb"],
                "luma": round(entry["luma"], 4),
                "ratio": round(ratio, 4),
                "name": entry.get("name"),
                "sources": entry["sources"],
            }
        )
    merged.sort(key=lambda entry: (-entry["ratio"], entry["hex"]))
    return merged[:max_size]


def _merge_anchors(anchor_sets: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    bbox_entries = [
        entry.get("bounding_box", {})
        for entry in anchor_sets
        if entry.get("bounding_box")
    ]
    face_entries = [entry.get("face", {}) for entry in anchor_sets if entry.get("face")]

    def avg_point(entries: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not entries:
            return None
        xs = [entry.get("xy", [0.5, 0.5])[0] for entry in entries]
        ys = [entry.get("xy", [0.5, 0.5])[1] for entry in entries]
        conf = [entry.get("confidence", 0.4) for entry in entries]
        return {
            "xy": [round(statistics.mean(xs), 4), round(statistics.mean(ys), 4)],
            "confidence": round(statistics.mean(conf), 4),
        }

    bbox = None
    if bbox_entries:
        xs = [
            entry["normalized"][0] for entry in bbox_entries if entry.get("normalized")
        ]
        ys = [
            entry["normalized"][1] for entry in bbox_entries if entry.get("normalized")
        ]
        rs = [
            entry["normalized"][2] for entry in bbox_entries if entry.get("normalized")
        ]
        bs = [
            entry["normalized"][3] for entry in bbox_entries if entry.get("normalized")
        ]
        conf = [entry.get("confidence", 0.4) for entry in bbox_entries]
        bbox = {
            "normalized": [
                round(statistics.mean(xs), 4),
                round(statistics.mean(ys), 4),
                round(statistics.mean(rs), 4),
                round(statistics.mean(bs), 4),
            ],
            "confidence": round(statistics.mean(conf), 4),
        }

    hands = {"left": [], "right": []}
    feet = {"left": [], "right": []}
    for anchors in anchor_sets:
        for side in ("left", "right"):
            hand = anchors.get("hands", {}).get(side)
            if hand:
                hands[side].append(hand)
            foot = anchors.get("feet", {}).get(side)
            if foot:
                feet[side].append(foot)

    merged = {
        "bounding_box": bbox,
        "face": avg_point(face_entries),
        "hands": {
            "left": avg_point(hands["left"]),
            "right": avg_point(hands["right"]),
        },
        "feet": {
            "left": avg_point(feet["left"]),
            "right": avg_point(feet["right"]),
        },
    }
    return merged


def _merge_expressions(expression_sets: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    combined: Dict[str, Dict[str, Any]] = {}
    for expressions in expression_sets:
        for key, data in expressions.items():
            entry = combined.setdefault(
                key,
                {
                    "mood": data.get("mood"),
                    "trigger": data.get("trigger"),
                    "confidence": 0.0,
                    "count": 0,
                },
            )
            entry["confidence"] += data.get("confidence", 0.3)
            entry["count"] += 1

    merged = {}
    for key, item in combined.items():
        merged[key] = {
            "mood": item.get("mood"),
            "trigger": item.get("trigger"),
            "confidence": round(item["confidence"] / max(1, item["count"]), 3),
        }
    return merged


def _detect_conflicts(appearances: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    conflicts: List[Dict[str, Any]] = []
    if not appearances:
        return conflicts
    species = {entry.get("species") for entry in appearances if entry.get("species")}
    if len(species) > 1:
        conflicts.append({"field": "appearance.species", "values": sorted(species)})
    fur_skin = {entry.get("fur_skin") for entry in appearances if entry.get("fur_skin")}
    if len(fur_skin) > 1:
        conflicts.append({"field": "appearance.fur_skin", "values": sorted(fur_skin)})
    primary = {
        entry.get("primary_color")
        for entry in appearances
        if entry.get("primary_color")
    }
    if len(primary) > 1:
        conflicts.append(
            {"field": "appearance.primary_color", "values": sorted(primary)}
        )
    return conflicts


# Utility --------------------------------------------------------------
def _merge_ordered_lists(items: Sequence[Optional[Sequence[str]]]) -> List[str]:
    weighted: Dict[str, float] = {}
    for seq in items:
        if not seq:
            continue
        for index, value in enumerate(seq):
            weighted[value] = weighted.get(value, 0.0) + (1.0 / (index + 1))
    ordered = sorted(weighted.items(), key=lambda item: (-item[1], item[0]))
    return [item[0] for item in ordered]


def _most_common(values: Sequence[Optional[str]]) -> Optional[str]:
    counter: Dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counter[value] = counter.get(value, 0) + 1
    if not counter:
        return None
    best = max(counter.items(), key=lambda item: (item[1], item[0]))
    return best[0]


def analyze_images(
    sources: Sequence[Union[str, Path, Image.Image]],
    *,
    persona_id: Optional[str] = None,
    options: Optional[PersonaImageOptions] = None,
) -> PersonaSuggestion:
    analyzer = ImagePersonaAnalyzer(options=options)
    return analyzer.analyze_images(sources, persona_id=persona_id)


__all__ = [
    "ANALYZER_VERSION",
    "ImageLoadError",
    "ImagePersonaAnalyzer",
    "PersonaImageOptions",
    "PersonaImageReport",
    "PersonaSuggestion",
    "analyze_images",
]
