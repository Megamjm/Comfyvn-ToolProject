"""
Visual novel asset extraction wrapper.

This script inspects a game directory or archive, picks an appropriate extractor
from the third-party tool manifest, runs it (when supported), and writes a
normalized log into ``imports/<game>/extract_log.json`` alongside
``raw_assets/`` output and a ``license_snapshot.json`` for provenance tracking.

Usage:
    python tools/vn_extract.py /path/to/game
    python tools/vn_extract.py /path/to/archive.rpa --game-name sample --dry-run
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
THIRD_PARTY_ROOT = ROOT / "third_party"
MANIFEST_PATH = THIRD_PARTY_ROOT / "manifest.json"
SHIM_DIR = THIRD_PARTY_ROOT / "shims"
DEFAULT_IMPORT_ROOT = ROOT / "imports"


@dataclass
class PatternSpec:
    glob: str
    role: str = "archive"  # archive | indicator
    weight: float = 1.0
    description: Optional[str] = None


@dataclass
class EngineProfile:
    key: str
    label: str
    patterns: List[PatternSpec]
    tool_priority: List[str]
    min_score: float = 1.0
    notes: Optional[str] = None


ENGINE_PROFILES: Dict[str, EngineProfile] = {
    "renpy": EngineProfile(
        key="renpy",
        label="Ren'Py",
        patterns=[
            PatternSpec(
                "**/*.rpa",
                role="archive",
                weight=2.0,
                description="Ren'Py archive (.rpa)",
            ),
            PatternSpec("**/game/*.rpyc", role="indicator", weight=0.3),
        ],
        tool_priority=["rpatool", "unrpa"],
        notes="Ren'Py archives often sit in the 'game' folder. rpatool is preferred when available.",
    ),
    "kirikiri": EngineProfile(
        key="kirikiri",
        label="KiriKiri / XP3",
        patterns=[
            PatternSpec(
                "**/*.xp3", role="archive", weight=2.0, description="XP3 archive"
            ),
            PatternSpec("**/*.xp3a", role="archive", weight=2.0),
            PatternSpec(
                "**/*.tlg",
                role="indicator",
                weight=0.4,
                description="TLG image payload",
            ),
        ],
        tool_priority=["krkrextract", "arc_unpacker", "garbro"],
        notes="XP3 archives may require engine-specific plugins; wrapper attempts best-effort extraction.",
    ),
    "wolf": EngineProfile(
        key="wolf",
        label="Wolf RPG",
        patterns=[
            PatternSpec(
                "**/*.wolf", role="archive", weight=2.0, description="Wolf archive"
            ),
            PatternSpec("**/Data.wolf", role="archive", weight=2.5),
            PatternSpec("**/*.mps", role="indicator", weight=0.2),
        ],
        tool_priority=["wolfdec"],
    ),
    "unity": EngineProfile(
        key="unity",
        label="Unity",
        patterns=[
            PatternSpec("**/*.assets", role="archive", weight=1.5),
            PatternSpec("**/*.unity3d", role="archive", weight=1.5),
            PatternSpec("**/globalgamemanagers", role="indicator", weight=0.5),
        ],
        tool_priority=["assetstudio"],
        notes="AssetStudio CLI usage varies by title; wrapper emits commands but may require manual follow-up.",
    ),
    "generic": EngineProfile(
        key="generic",
        label="Generic VN archives",
        patterns=[
            PatternSpec("**/*.arc", role="archive", weight=1.2),
            PatternSpec("**/*.pak", role="archive", weight=1.2),
            PatternSpec("**/*.int", role="archive", weight=1.0),
            PatternSpec("**/*.pac", role="archive", weight=1.0),
            PatternSpec("**/*.dat", role="archive", weight=0.6),
        ],
        tool_priority=["garbro", "arc_unpacker"],
        notes="Fallback profile when only generic archive containers are detected.",
    ),
}


@dataclass
class DetectionResult:
    profile: EngineProfile
    score: float
    matches: Dict[str, List[Path]]

    @property
    def archives(self) -> List[Path]:
        seen: Dict[Path, None] = {}
        for spec in self.profile.patterns:
            if spec.role != "archive":
                continue
            paths = self.matches.get(spec.glob, [])
            for path in paths:
                seen[path] = None
        return sorted(seen.keys())


def load_manifest() -> Dict[str, object]:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"format_version": 1, "installed": {}}


def _gather_matches(profile: EngineProfile, source: Path) -> Dict[str, List[Path]]:
    matches: Dict[str, List[Path]] = {}
    base = source if source.is_dir() else source.parent
    for spec in profile.patterns:
        found: List[Path] = []
        if source.is_dir():
            found.extend(p for p in base.glob(spec.glob) if p.is_file())
        if source.is_file():
            if source.match(spec.glob) or fnmatch.fnmatch(
                source.name, spec.glob.split("/")[-1]
            ):
                found.append(source)
        if not found:
            continue
        unique = sorted({p.resolve() for p in found})
        matches[spec.glob] = unique
    return matches


def detect_engine(source: Path, override: Optional[str] = None) -> DetectionResult:
    if override and override != "auto":
        profile = ENGINE_PROFILES.get(override)
        if not profile:
            raise ValueError(f"Unknown engine override '{override}'.")
        matches = _gather_matches(profile, source)
        score = sum(
            len(v)
            * next((spec.weight for spec in profile.patterns if spec.glob == key), 1.0)
            for key, v in matches.items()
        )
        return DetectionResult(profile=profile, score=score, matches=matches)

    best: Optional[DetectionResult] = None
    for profile in ENGINE_PROFILES.values():
        matches = _gather_matches(profile, source)
        if not matches:
            continue
        score = 0.0
        for spec in profile.patterns:
            paths = matches.get(spec.glob, [])
            if paths:
                score += spec.weight * len(paths)
        if score < profile.min_score:
            continue
        if best is None or score > best.score:
            best = DetectionResult(profile=profile, score=score, matches=matches)
    if best:
        return best
    raise RuntimeError(
        "Unable to detect engine automatically. Try --engine to override."
    )


def _normalized(path: Path) -> str:
    return path.as_posix()


def _sanitize_game_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name.strip())
    return cleaned.lower() or "vn_extractor_job"


def _ensure_dir(path: Path, clean: bool = False) -> None:
    if clean and path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _select_tool(
    result: DetectionResult, manifest: Dict[str, object], requested: Optional[str]
) -> Tuple[str, Dict[str, object]]:
    installed = manifest.get("installed") or {}
    if requested:
        info = installed.get(requested)
        if not info:
            raise RuntimeError(
                f"Requested tool '{requested}' is not installed. "
                "Run tools/install_third_party.py to fetch it."
            )
        return requested, info
    for tool_key in result.profile.tool_priority:
        info = installed.get(tool_key)
        if info:
            return tool_key, info
    raise RuntimeError(
        f"No preferred extractor installed for engine '{result.profile.label}'. "
        "Run tools/install_third_party.py to install one of: "
        + ", ".join(result.profile.tool_priority)
    )


def _build_command(
    tool_key: str, shim: Path, archive: Path, output_dir: Path
) -> Optional[List[str]]:
    if tool_key == "rpatool":
        return [str(shim), "-x", str(archive), "-o", str(output_dir)]
    if tool_key == "unrpa":
        return [str(shim), "-mp", str(output_dir), str(archive)]
    if tool_key == "arc_unpacker":
        return [str(shim), str(archive), str(output_dir)]
    if tool_key == "garbro":
        # GARbro portable build relies on GUI CLI switches; provide best-effort batch call.
        return [str(shim), "-o", str(output_dir), str(archive)]
    if tool_key == "krkrextract":
        return [str(shim), str(archive), str(output_dir)]
    if tool_key == "assetstudio":
        return [str(shim), "--cli", "--output", str(output_dir), str(archive)]
    if tool_key == "wolfdec":
        return [str(shim), str(archive)]
    return None


def _summarize_dir(path: Path) -> Dict[str, object]:
    files = []
    total_size = 0
    for item in path.rglob("*"):
        if item.is_file():
            files.append(item)
            try:
                total_size += item.stat().st_size
            except OSError:
                pass
    sample = [
        _normalized(f.relative_to(path))
        for f in sorted(files, key=lambda p: p.as_posix())[:5]
    ]
    return {
        "files": len(files),
        "bytes": total_size,
        "sample": sample,
    }


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_license_snapshot(
    tool_key: str, manifest_entry: Dict[str, object], game: str
) -> Dict[str, object]:
    license_info = manifest_entry.get("license") or {}
    download_info = manifest_entry.get("download") or {}
    return {
        "game": game,
        "tool_key": tool_key,
        "tool_name": manifest_entry.get("name"),
        "tool_version": manifest_entry.get("version"),
        "license": {
            "name": license_info.get("name"),
            "url": license_info.get("url"),
        },
        "source": download_info,
        "notes": manifest_entry.get("notes"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _build_plan(
    detection: DetectionResult,
    archives: Sequence[Path],
    tool_key: str,
    output_root: Path,
    raw_dir: Path,
) -> Dict[str, object]:
    return {
        "engine": detection.profile.key,
        "engine_label": detection.profile.label,
        "score": detection.score,
        "tool": tool_key,
        "archives": [_normalized(path) for path in archives],
        "output": {
            "root": _normalized(output_root),
            "raw_assets": _normalized(raw_dir),
        },
    }


def run_extraction(
    tool_key: str,
    manifest_entry: Dict[str, object],
    archives: Sequence[Path],
    raw_dir: Path,
    *,
    dry_run: bool = False,
) -> List[Dict[str, object]]:
    shim_path = SHIM_DIR / tool_key
    if not shim_path.exists():
        raise RuntimeError(
            f"Shim for tool '{tool_key}' not found at {shim_path}. "
            "Re-run tools/install_third_party.py."
        )

    results: List[Dict[str, object]] = []
    for archive in archives:
        target_dir = raw_dir / archive.stem
        target_dir.mkdir(parents=True, exist_ok=True)
        command = _build_command(tool_key, shim_path, archive, target_dir)
        record: Dict[str, object] = {
            "archive": _normalized(archive),
            "output_dir": _normalized(target_dir),
            "command": command,
        }
        start_ts = time.time()
        if dry_run:
            record["status"] = "dry-run"
            record["duration_sec"] = 0.0
            record["summary"] = _summarize_dir(target_dir)
            record["message"] = "Extraction skipped (dry-run)."
            results.append(record)
            continue
        if not command:
            record["status"] = "unsupported"
            record["duration_sec"] = 0.0
            record["message"] = (
                f"No automated command registered for tool '{tool_key}'. "
                "Run the shim manually and re-import the assets."
            )
            record["summary"] = _summarize_dir(target_dir)
            results.append(record)
            continue

        try:
            proc = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
            status = "ok"
            message = proc.stderr.strip() or "Extraction completed."
            stdout_tail = "\n".join(proc.stdout.splitlines()[-10:])
        except subprocess.CalledProcessError as exc:
            status = "error"
            message = exc.stderr.strip() or f"Extractor exited with {exc.returncode}."
            stdout_tail = "\n".join((exc.stdout or "").splitlines()[-10:])
        except FileNotFoundError as exc:
            status = "error"
            message = str(exc)
            stdout_tail = ""

        record.update(
            {
                "status": status,
                "duration_sec": round(time.time() - start_ts, 3),
                "message": message,
                "stdout_tail": stdout_tail,
                "summary": _summarize_dir(target_dir),
            }
        )
        results.append(record)
    return results


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Visual novel extractor wrapper.")
    parser.add_argument("source", help="Path to game directory or archive file.")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_IMPORT_ROOT),
        help="Destination base folder (default: %(default)s).",
    )
    parser.add_argument(
        "--game-name",
        help="Override the inferred game name (used for imports/<game_name>/...).",
    )
    parser.add_argument(
        "--engine",
        default="auto",
        help="Force an engine profile (default: auto detect).",
    )
    parser.add_argument(
        "--tool",
        help="Force a specific extractor key (e.g. rpatool, arc_unpacker).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip execution and emit the plan/log structure only.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Emit the extraction plan as JSON and exit.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove any existing raw_assets directory before extraction.",
    )
    args = parser.parse_args(argv)

    source_path = Path(args.source).expanduser().resolve()
    if not source_path.exists():
        parser.error(f"Source path '{source_path}' does not exist.")

    detection = detect_engine(source_path, override=args.engine)
    archives = detection.archives
    if not archives:
        raise RuntimeError("Detected engine but found no archives to extract.")

    manifest = load_manifest()
    tool_key, manifest_entry = _select_tool(detection, manifest, args.tool)

    game_name = args.game_name or _sanitize_game_name(
        source_path.stem if source_path.is_file() else source_path.name
    )
    output_root = Path(args.output_root).expanduser().resolve()
    target_dir = output_root / game_name
    raw_dir = target_dir / "raw_assets"
    _ensure_dir(target_dir, clean=False)
    _ensure_dir(raw_dir, clean=args.clean)

    plan = _build_plan(detection, archives, tool_key, target_dir, raw_dir)
    if args.plan_only:
        print(json.dumps(plan, indent=2))
        return 0

    extraction_results = run_extraction(
        tool_key,
        manifest_entry,
        archives,
        raw_dir,
        dry_run=args.dry_run,
    )

    license_snapshot = _build_license_snapshot(tool_key, manifest_entry, game_name)
    license_path = raw_dir / "license_snapshot.json"
    _write_json(license_path, license_snapshot)

    log_payload = {
        "game": game_name,
        "source": _normalized(source_path),
        "engine": {
            "key": detection.profile.key,
            "label": detection.profile.label,
            "score": detection.score,
            "notes": detection.profile.notes,
            "matches": {
                pattern: [_normalized(p) for p in paths]
                for pattern, paths in detection.matches.items()
            },
        },
        "tool": {
            "key": tool_key,
            "name": manifest_entry.get("name"),
            "version": manifest_entry.get("version"),
            "shim": _normalized(SHIM_DIR / tool_key),
        },
        "outputs": {
            "root": _normalized(target_dir),
            "raw_assets": _normalized(raw_dir),
            "license_snapshot": _normalized(license_path),
        },
        "dry_run": args.dry_run,
        "results": extraction_results,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    log_path = target_dir / "extract_log.json"
    _write_json(log_path, log_payload)

    print(
        f"[vn_extract] Engine: {detection.profile.label} — Tool: {manifest_entry.get('name')} ({tool_key})"
    )
    print(f"[vn_extract] Archives: {len(archives)} → raw assets in {raw_dir}")
    print(f"[vn_extract] Log written to {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
