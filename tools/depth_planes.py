"""
Depth plane helper.

Usage:
    python tools/depth_planes.py --depth path/to/depth.png --planes 4 --output planes.json

The utility loads a depth map (16-bit PNG, float PNG, or .npy array), displays
histogram statistics, and launches a minimal REPL so artists can tune the
thresholds that will be fed into the Flat→Layers pipeline. The script does not
touch the main pipeline code; it simply writes a JSON blob containing
`thresholds`, `parallax_scale`, and basic telemetry. The resulting file can be
fed back into the pipeline via `FlatToLayersOptions.plane_thresholds`.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageOps

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency
    np = None  # type: ignore


DEFAULT_NOTES = [
    "Enter `set <index> <value>` to update a threshold (0 < value < 1).",
    "`auto` redistributes thresholds evenly.",
    "`percentile <index> <pct>` sets threshold to a percentile from depth histogram.",
    "`scale <value>` updates the parallax scale multiplier.",
    "`preview` exports plane masks alongside the input depth map for a quick check.",
    "`save` writes thresholds + scale to the output file and exits.",
    "`help` prints this list. `quit` exits without writing.",
]


@dataclass
class DepthProfile:
    min_value: float
    max_value: float
    mean: float
    median: float
    stddev: float
    histogram: List[Tuple[float, float]]


@dataclass
class PlaneState:
    thresholds: List[float]
    parallax_scale: float = 1.0
    notes: List[str] = field(default_factory=lambda: list(DEFAULT_NOTES))
    depth_profile: Optional[DepthProfile] = None
    preview_dir: Optional[Path] = None


def _load_depth(path: Path) -> Image.Image:
    suffix = path.suffix.lower()
    if suffix == ".npy":
        if np is None:
            raise RuntimeError("NumPy required to load .npy depth maps.")
        arr = np.load(path)
        arr = arr.astype("float32")
        arr -= arr.min()
        span = arr.max() - arr.min()
        if span > 0:
            arr /= span
        return Image.fromarray((arr * 65535).astype("uint16"), mode="I;16")
    return Image.open(path)


def _normalize_depth(image: Image.Image) -> Image.Image:
    if image.mode in {"I;16", "F"}:
        normalized = image
    else:
        normalized = ImageOps.grayscale(image).convert("I;16")
    return ImageOps.autocontrast(normalized)


def _build_profile(image: Image.Image, *, bins: int = 32) -> DepthProfile:
    normalized = _normalize_depth(image)
    if np is None:
        pixels = list(normalized.getdata())
        values = [px / 65535.0 for px in pixels]
        histogram = []
        step = 1.0 / bins
        for index in range(bins):
            lo = index * step
            hi = (index + 1) * step
            bucket = [value for value in values if lo <= value < hi]
            histogram.append(
                (round((lo + hi) * 0.5, 4), len(bucket) / max(1, len(values)))
            )
        return DepthProfile(
            min_value=min(values) if values else 0.0,
            max_value=max(values) if values else 1.0,
            mean=statistics.fmean(values) if values else 0.0,
            median=statistics.median(values) if values else 0.0,
            stddev=statistics.pstdev(values) if values else 0.0,
            histogram=histogram,
        )

    arr = np.array(normalized, dtype=np.uint16) / 65535.0
    hist, edges = np.histogram(arr, bins=bins, range=(0.0, 1.0), density=False)
    total = hist.sum() or 1
    histogram = []
    for idx, count in enumerate(hist):
        center = (edges[idx] + edges[idx + 1]) * 0.5
        histogram.append((round(float(center), 4), float(count) / total))
    return DepthProfile(
        min_value=float(arr.min()) if arr.size else 0.0,
        max_value=float(arr.max()) if arr.size else 1.0,
        mean=float(arr.mean()) if arr.size else 0.0,
        median=float(np.median(arr)) if arr.size else 0.0,
        stddev=float(np.std(arr)) if arr.size else 0.0,
        histogram=histogram,
    )


def _auto_thresholds(count: int) -> List[float]:
    step = 1.0 / count
    return [round(step * idx, 4) for idx in range(1, count)]


def _clamp_threshold(value: float) -> float:
    return max(0.0, min(1.0, value))


def _apply_percentile(profile: DepthProfile, pct: float) -> float:
    pct = max(0.0, min(100.0, pct))
    acc = 0.0
    for center, fraction in sorted(profile.histogram, key=lambda item: item[0]):
        acc += fraction
        if acc * 100.0 >= pct:
            return _clamp_threshold(center)
    return 1.0


def _preview_planes(depth: Image.Image, state: PlaneState) -> Path:
    target_dir = state.preview_dir or Path("layered/previews/depth_planes")
    target_dir = target_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_depth(depth)
    thresholds = sorted(state.thresholds)
    planes: List[Image.Image] = []
    prev = 0.0
    for value in thresholds + [1.0]:
        value = _clamp_threshold(value)
        plane = Image.new("L", normalized.size, 0)
        mask = normalized.point(
            lambda px: 255 if prev * 65535 <= px <= value * 65535 else 0
        )
        planes.append(mask)
        prev = value
    for index, mask in enumerate(planes):
        out_path = target_dir / f"plane_{index:02d}.png"
        mask.save(out_path)
    return target_dir


def _print_profile(profile: DepthProfile) -> None:
    print("Depth statistics:")
    print(
        f"  min={profile.min_value:.4f} max={profile.max_value:.4f} mean={profile.mean:.4f}"
        f" median={profile.median:.4f} stddev={profile.stddev:.4f}"
    )
    print("  histogram (center -> fraction):")
    for center, fraction in profile.histogram:
        bar = "#" * int(fraction * 40)
        print(f"    {center:>6.3f} • {fraction:>6.3f} {bar}")


def _save_state(state: PlaneState, output: Path) -> None:
    payload = {
        "thresholds": [round(value, 6) for value in sorted(state.thresholds)],
        "parallax_scale": round(state.parallax_scale, 4),
        "notes": state.notes,
    }
    if state.depth_profile:
        payload["depth_profile"] = {
            "min": round(state.depth_profile.min_value, 6),
            "max": round(state.depth_profile.max_value, 6),
            "mean": round(state.depth_profile.mean, 6),
            "median": round(state.depth_profile.median, 6),
            "stddev": round(state.depth_profile.stddev, 6),
        }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote plane configuration → {output}")


def _interactive_loop(depth: Image.Image, state: PlaneState, output: Path) -> None:
    print("Interactive depth-plane editor. Type 'help' for commands.")
    while True:
        command = input("> ").strip()
        if not command:
            continue
        parts = command.split()
        cmd = parts[0].lower()
        if cmd in {"quit", "exit"}:
            print("Bye.")
            return
        if cmd == "help":
            print("\n".join(state.notes))
            continue
        if cmd == "list":
            for idx, value in enumerate(sorted(state.thresholds)):
                print(f"plane[{idx}] threshold={value:.4f}")
            print(f"parallax_scale={state.parallax_scale:.3f}")
            continue
        if cmd == "auto":
            count = len(state.thresholds) + 1
            state.thresholds = _auto_thresholds(count)
            print("Auto thresholds:", ", ".join(f"{v:.4f}" for v in state.thresholds))
            continue
        if cmd == "set" and len(parts) == 3:
            try:
                index = int(parts[1])
                value = float(parts[2])
            except ValueError:
                print("Usage: set <index> <value>")
                continue
            if not 0 <= index < len(state.thresholds):
                print("Index out of range.")
                continue
            state.thresholds[index] = _clamp_threshold(value)
            print(f"threshold[{index}]={state.thresholds[index]:.4f}")
            continue
        if cmd == "percentile" and len(parts) == 3:
            if not state.depth_profile:
                print(
                    "Depth profile unavailable; run with --depth <path> supporting histogram."
                )
                continue
            try:
                index = int(parts[1])
                pct = float(parts[2])
            except ValueError:
                print("Usage: percentile <index> <pct>")
                continue
            if not 0 <= index < len(state.thresholds):
                print("Index out of range.")
                continue
            state.thresholds[index] = _apply_percentile(state.depth_profile, pct)
            print(
                f"threshold[{index}] set via percentile {pct} → {state.thresholds[index]:.4f}"
            )
            continue
        if cmd == "scale" and len(parts) == 2:
            try:
                state.parallax_scale = max(0.1, float(parts[1]))
            except ValueError:
                print("Usage: scale <value>")
                continue
            print(f"parallax_scale={state.parallax_scale:.3f}")
            continue
        if cmd == "preview":
            out_dir = _preview_planes(depth, state)
            print(f"Preview planes exported → {out_dir}")
            continue
        if cmd == "save":
            _save_state(state, output)
            return
        print("Unknown command. Type 'help' for options.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive depth plane tuner")
    parser.add_argument(
        "--depth", required=True, help="Path to depth map (PNG or .npy)."
    )
    parser.add_argument(
        "--planes", type=int, default=4, help="Number of background planes."
    )
    parser.add_argument(
        "--thresholds", nargs="*", type=float, help="Initial threshold guesses."
    )
    parser.add_argument(
        "--parallax-scale", type=float, default=1.0, help="Initial parallax scale."
    )
    parser.add_argument(
        "--output", default="depth_planes.json", help="Destination JSON path."
    )
    parser.add_argument("--preview-dir", help="Directory for preview plane masks.")
    args = parser.parse_args(argv)

    depth_path = Path(args.depth).expanduser().resolve()
    if not depth_path.exists():
        print(f"Depth map not found: {depth_path}", file=sys.stderr)
        return 2

    try:
        depth_image = _load_depth(depth_path)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Failed to load depth map: {exc}", file=sys.stderr)
        return 3

    thresholds = (
        list(args.thresholds)
        if args.thresholds
        else _auto_thresholds(max(2, args.planes))
    )
    if len(thresholds) != max(0, args.planes - 1):
        thresholds = _auto_thresholds(max(2, args.planes))

    state = PlaneState(
        thresholds=[_clamp_threshold(value) for value in thresholds],
        parallax_scale=max(0.1, args.parallax_scale),
        preview_dir=Path(args.preview_dir).expanduser() if args.preview_dir else None,
    )
    state.depth_profile = _build_profile(depth_image)

    output_path = Path(args.output).expanduser().resolve()
    print(f"Depth map loaded from {depth_path}")
    _print_profile(state.depth_profile)
    _interactive_loop(depth_image, state, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
