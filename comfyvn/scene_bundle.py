# comfyvn/scene_bundle.py
# [S2 Scene Bundle Export — ComfyVN Architect | 2025-10-20 | chat: S2]
from __future__ import annotations

import json
import logging
import pathlib
import re
from typing import Dict, List, Optional, Tuple

# Optional jsonschema validation (present if requirements were applied)
try:
    import jsonschema
except Exception:
    jsonschema = None

SCHEMA_PATH_DEFAULT = "docs/scene_bundle.schema.json"
ASSETS_MANIFEST_DEFAULT = "assets/assets.manifest.json"

_TAG_RE = re.compile(
    r"\[\[\s*(?P<key>bg|label|goto|expr)\s*:\s*(?P<val>[^\]]+)\]\]", re.I
)


def _load_json(path: str) -> Optional[dict]:
    p = pathlib.Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _canon_name(name: str) -> str:
    return (name or "").strip().lower()


def _strip_stage_tags(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Remove [[bg:X]], [[label:X]], [[goto:X]], [[expr:X]] and return clean text + tags."""
    tags: List[Tuple[str, str]] = []
    if not text:
        return text, tags

    def _collect(m: re.Match) -> str:
        tags.append((m.group("key").lower(), m.group("val").strip()))
        return ""

    cleaned = _TAG_RE.sub(_collect, text).strip()
    return cleaned, tags


def _infer_emotion_from_text(text: str) -> Optional[str]:
    """Very light heuristic as a fallback if no emotion provided."""
    if not text:
        return None
    t = text.strip()
    if t.endswith("!?") or t.endswith("?!"):
        return "surprised"
    if t.endswith("!"):
        return "excited"
    if t.endswith("?"):
        return "confused"
    if t.endswith("...") or "…" in t:
        return "pensive"
    return "neutral"


def _gather_characters_and_expressions(raw: dict) -> Dict[str, set]:
    """
    Returns {character_name: {expressions}}.
    Uses raw['dialogue'] entries with keys: speaker, text, emotion.
    """
    mapping: Dict[str, set] = {}
    for it in raw.get("dialogue", []):
        if it.get("type") != "line":
            continue
        name = (it.get("speaker") or "Narrator").strip()
        emo = (
            it.get("emotion")
            or _infer_emotion_from_text(it.get("text", ""))
            or "neutral"
        )
        mapping.setdefault(name, set()).add(emo)
    # Normalize: ensure each has at least 'neutral'
    for k in list(mapping.keys()):
        if not mapping[k]:
            mapping[k].add("neutral")
    return mapping


def _link_assets_for_characters(
    char_exprs: Dict[str, set], manifest: Optional[dict]
) -> Dict[str, Dict[str, str]]:
    """
    From manifest['by_character'] choose best matching assets by expression.
    Case-insensitive character matching. If expression missing, leave unresolved.
    """
    result: Dict[str, Dict[str, str]] = {}
    if not manifest:
        return result
    idx = manifest.get("by_character", {})
    # Build lowercase index for name-insensitive lookup
    lower_idx = {_canon_name(k): v for k, v in idx.items()}
    for char, exprs in char_exprs.items():
        found = lower_idx.get(_canon_name(char))
        if not found:
            continue
        result.setdefault(char, {})
        for e in sorted(exprs):
            # Exact expression key if present
            # Common file naming uses "<expr>.png" as key in manifest group
            # Our A3 builder sets mapping to relpath keyed by expression stem
            path = found.get(e)
            if path:
                result[char][e] = path
            else:
                # fallback: try 'neutral' if exists
                if "neutral" in found:
                    result[char][e] = found["neutral"]
    return result


def _link_backgrounds(bg_names: List[str], manifest: Optional[dict]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not manifest or not bg_names:
        return result
    idx = manifest.get("by_background", {})
    # try case-insensitive resolves
    lower_idx = {_canon_name(k): v for k, v in idx.items()}
    for b in set(bg_names):
        rp = lower_idx.get(_canon_name(b))
        if rp:
            result[b] = rp
    return result


def _build_dialogue(raw: dict) -> Tuple[List[dict], List[str]]:
    """
    Convert raw dialogue to bundle dialogue, respecting tags.
    Returns (dialogue_list, bg_names_used)
    """
    out: List[dict] = [{"type": "label", "name": "start"}]
    bgs_used: List[str] = []
    for it in raw.get("dialogue", []):
        if it.get("type") != "line":
            continue
        text = it.get("text", "")
        clean, tags = _strip_stage_tags(text)
        # inject stage tags as separate events
        for k, v in tags:
            if k == "bg":
                out.append({"type": "scene", "target_bg": v})
                bgs_used.append(v)
            elif k == "label":
                out.append({"type": "label", "name": v})
            elif k == "goto":
                out.append({"type": "jump", "goto": v})
            elif k == "expr":
                # expr hint as a show event on current speaker
                out.append({"type": "show", "speaker": it.get("speaker"), "emotion": v})
        # push the line
        out.append(
            {
                "type": "line",
                "speaker": it.get("speaker"),
                "text": clean,
                "emotion": it.get("emotion")
                or _infer_emotion_from_text(clean)
                or "neutral",
            }
        )
    return out, bgs_used


def build_bundle(
    raw: dict,
    assets_manifest: Optional[dict] = None,
    schema_path: str = SCHEMA_PATH_DEFAULT,
) -> dict:
    # 1) Characters & expressions
    char_exprs = _gather_characters_and_expressions(raw)
    # 2) Dialogue + bg usage
    dialogue, bg_names = _build_dialogue(raw)
    # 3) Link assets where possible
    char_assets = _link_assets_for_characters(char_exprs, assets_manifest)
    bg_assets = _link_backgrounds(bg_names, assets_manifest)
    # 4) Assemble bundle
    bundle = {
        "id": raw.get("id") or "scene-untitled",
        "meta": {"style": raw.get("title") or "", "seed": None},
        "characters": [
            {
                "name": c,
                "expressions": sorted(list(exprs)),
                "assets": char_assets.get(c, {}),
            }
            for c, exprs in sorted(char_exprs.items(), key=lambda kv: kv[0].lower())
        ],
        "backgrounds": [
            {"name": b, "asset": bg_assets.get(b)} for b in sorted(set(bg_names))
        ],
        "dialogue": dialogue,
        "assets": {"characters": char_assets, "backgrounds": bg_assets},
    }
    # 5) Validate if schema available
    _validate_bundle(bundle, schema_path)
    return bundle


def _validate_bundle(bundle: dict, schema_path: str = SCHEMA_PATH_DEFAULT) -> None:
    if not jsonschema:
        return
    schema = _load_json(schema_path)
    if not schema:
        return
    jsonschema.validate(instance=bundle, schema=schema)


def convert_file(
    raw_path: str,
    out_path: str,
    manifest_path: str = ASSETS_MANIFEST_DEFAULT,
    schema_path: str = SCHEMA_PATH_DEFAULT,
) -> dict:
    logger = logging.getLogger(__name__)
    logger.info("Converting raw scene -> bundle: %s", raw_path)
    raw = _load_json(raw_path)
    if not raw:
        raise RuntimeError(f"Raw scene not found or invalid: {raw_path}")
    manifest = _load_json(manifest_path)
    bundle = build_bundle(raw, manifest, schema_path=schema_path)
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out_path).write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle
