from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

from comfyvn.core.music_remix import remix_track

LOGGER = logging.getLogger(__name__)


def build_translation_bundle(
    scene_paths: List[Path], import_root: Path, *, target_lang: str = "en"
) -> Dict[str, object]:
    translations_dir = import_root / "translations"
    translations_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = translations_dir / "segments.json"

    segments: List[Dict[str, object]] = []
    tm_index: Dict[str, str] = {}
    tm_hits: List[Dict[str, str]] = []

    for scene_path in scene_paths:
        if not scene_path.exists():
            LOGGER.debug(
                "Skipping missing scene for translation bundle: %s", scene_path
            )
            continue
        try:
            data = json.loads(scene_path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning(
                "Failed to parse scene %s for translation bundle: %s", scene_path, exc
            )
            continue
        scene_id = data.get("scene_id") or scene_path.stem
        lines = data.get("lines") or []
        for idx, line in enumerate(lines):
            if not isinstance(line, dict):
                continue
            text = str(line.get("text") or "").strip()
            if not text:
                continue
            segment_id = f"{scene_id}-{idx + 1}"
            segment = {
                "id": segment_id,
                "scene": scene_id,
                "speaker": line.get("speaker"),
                "text": text,
                "metadata": line.get("meta") or {},
            }
            segments.append(segment)
            if text in tm_index:
                tm_hits.append({"segment": segment_id, "match": tm_index[text]})
            else:
                tm_index[text] = segment_id

    payload = {
        "target_lang": target_lang,
        "segment_count": len(segments),
        "segments": segments,
        "tm_hits": tm_hits,
    }
    bundle_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "bundle_path": bundle_path.as_posix(),
        "segments": len(segments),
        "scenes": sorted({seg["scene"] for seg in segments}),
        "target_lang": target_lang,
        "tm_hits": len(tm_hits),
    }


def plan_remix_tasks(
    manifest: Dict[str, object], scenes: List[str], import_root: Path
) -> Dict[str, object]:
    remix_dir = import_root / "remix"
    remix_dir.mkdir(parents=True, exist_ok=True)
    plan_path = remix_dir / "remix_plan.json"

    assets = manifest.get("assets") or {}
    bg_assets = assets.get("bg") or []
    cg_assets = assets.get("cg") or []
    sprite_assets = assets.get("sprites") or []

    tasks: List[Dict[str, object]] = []
    for entry in bg_assets[:8]:
        tasks.append(
            {
                "type": "background_upscale",
                "input": entry.get("path"),
                "workflow": "comfyui:bg_upscale_v1",
            }
        )
    for entry in cg_assets[:6]:
        tasks.append(
            {
                "type": "cg_restoration",
                "input": entry.get("path"),
                "workflow": "comfyui:cg_restore_v1",
            }
        )
    for entry in sprite_assets[:10]:
        tasks.append(
            {
                "type": "sprite_recolor",
                "input": entry.get("path"),
                "workflow": "comfyui:sprite_recolor_v1",
            }
        )

    exports = [
        {
            "type": "renpy_loose",
            "notes": "Generate loose script/asset files for Ren'Py",
        },
        {"type": "renpy_rpa", "notes": "Bundle assets via user-supplied RPA hook"},
        {"type": "kirikiri_overlay", "notes": "Produce XP3 overlay patch"},
        {
            "type": "tyrano_data",
            "notes": "Rebuild Tyrano data/ structure for quick preview",
        },
    ]

    music: List[Dict[str, object]] = []
    if scenes:
        try:
            artifact, sidecar = remix_track(scene_id=scenes[0], target_style="import")
            music.append({"scene": scenes[0], "artifact": artifact, "sidecar": sidecar})
        except Exception as exc:
            LOGGER.warning("Music remix stub failed for scene %s: %s", scenes[0], exc)

    plan_payload = {"tasks": tasks, "exports": exports, "music": music}
    plan_path.write_text(
        json.dumps(plan_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "plan_path": plan_path.as_posix(),
        "task_count": len(tasks),
        "music": music,
        "exports": exports,
    }


__all__ = ["build_translation_bundle", "plan_remix_tasks"]
