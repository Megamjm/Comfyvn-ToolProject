#!/usr/bin/env python3
# Phase ALL Doctor - aggregates profiles and resolves base with rollover
import argparse
import json
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.check_current_system import _discover_base  # reuse helper

CHECKER = ROOT / "tools" / "check_current_system.py"
PROFILES = ROOT / "tools" / "check_profiles.json"
FLAGS_FILE = ROOT / "config" / "comfyvn.json"
README = ROOT / "README.md"

REQUIRED_DOCS = [
    "docs/POV_DESIGN.md",
    "docs/TIMELINE_OVERLAY.md",
    "docs/EXTRACTORS.md",
    "docs/FLAT_TO_LAYERS.md",
    "docs/PROPS_SPEC.md",
    "docs/THEME_KITS.md",
    "docs/THEME_SWAP_WIZARD.md",
    "docs/STYLE_TAGS_REGISTRY.md",
    "docs/NARRATOR_SPEC.md",
    "docs/LLM_ORCHESTRATION.md",
    "docs/BATTLE_DESIGN.md",
    "docs/PLAYGROUND.md",
    "docs/3D_ASSETS.md",
    "docs/EXPORT_RENPY.md",
    "docs/GOLDEN_TESTS.md",
    "docs/DUNGEON_API.md",
    "docs/PROVIDERS_GPU_IMAGE_VIDEO.md",
    "docs/PROVIDERS_LANG_SPEECH_LLM.md",
    "docs/REMOTE_INSTALLER.md",
    "docs/SECURITY_SECRETS.md",
    "docs/OBS_TELEMETRY.md",
    "docs/PERF_BUDGETS.md",
    "docs/MARKETPLACE.md",
    "docs/CLOUD_SYNC.md",
    "docs/BACKUPS.md",
    "docs/COLLAB_EDITING.md",
    "docs/SECURITY_SANDBOX.md",
    "docs/CODE_SIGNING.md",
    "docs/ACCESSIBILITY.md",
    "docs/INPUT_SCHEMES.md",
    "docs/IMAGE2PERSONA.md",
    "docs/ANIM_25D.md",
    "docs/EDITOR_UX_ADVANCED.md",
    "docs/PUBLISH_WEB.md",
    "docs/COMMUNITY_CONNECTORS.md",
    "docs/NSFW_GATING.md",
    "docs/PROVIDERS_CIVITAI.md",
    "docs/PROVIDERS_HF_HUB.md",
    "docs/ADVISORY_LICENSE_SNAPSHOT.md",
    "docs/ASSET_INGEST.md",
]

EXPECTED_FLAGS = [
    "enable_worldlines",
    "enable_timeline_overlay",
    "enable_depth2d",
    "enable_playground",
    "enable_stage3d",
    "enable_narrator",
    "enable_llm_role_mapping",
    "enable_battle_sim",
    "enable_props",
    "enable_weather_overlays",
    "enable_themes",
    "enable_anim_25d",
    "enable_publish_web",
    "enable_persona_importers",
    "enable_image2persona",
    "enable_asset_ingest",
    "enable_public_model_hubs",
    "enable_public_gpu",
    "enable_public_image_video",
    "enable_public_translate",
    "enable_public_llm",
    "enable_marketplace",
    "enable_cloud_sync",
    "enable_collab",
    "enable_security_sandbox",
    "enable_accessibility",
    "enable_observability",
    "enable_perf",
    "enable_mini_vn",
    "enable_export_bake",
]


def _load_json(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_checker(profile: str, base: str):
    cmd = [sys.executable, str(CHECKER), "--profile", profile, "--base", base]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    try:
        data = json.loads(p.stdout or "{}")
    except Exception:
        data = {"pass": False, "notes": ["no json from checker"]}
    data["_rc"] = p.returncode
    data["_stderr"] = p.stderr.strip()
    data["_profile"] = profile
    return data


def junit_write(cases, path: pathlib.Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<testsuite name="doctor_all" tests="%d">' % len(cases),
    ]
    for c in cases:
        if c["ok"]:
            xml.append(f'<testcase classname="doctor" name="{c["name"]}"/>')
        else:
            xml.append(
                f'<testcase classname="doctor" name="{c["name"]}"><failure message="{c["message"]}"/></testcase>'
            )
    xml.append("</testsuite>")
    path.write_text("\n".join(xml), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="")
    ap.add_argument("--profiles-file", default=str(PROFILES))
    ap.add_argument("--flags-file", default=str(FLAGS_FILE))
    ap.add_argument("--include", default="p[1-7]_.*")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--out", default=".doctor_all.json")
    ap.add_argument("--junit", default="")
    args = ap.parse_args()

    profs = _load_json(pathlib.Path(args.profiles_file))
    if not profs:
        print(
            json.dumps(
                {"pass": False, "notes": ["missing tools/check_profiles.json"]},
                indent=2,
            )
        )
        sys.exit(2)

    inc = re.compile(args.include) if args.include else None
    exc = re.compile(args.exclude) if args.exclude else None
    selected = [
        k
        for k in profs.keys()
        if (not inc or inc.match(k)) and (not exc or not exc.match(k))
    ]

    base, tried, warns = _discover_base(args.base, args.flags_file)
    if base:
        print(f"[doctor_phase_all] base={base} tried={tried}", file=sys.stderr)
    else:
        print(f"[doctor_phase_all] no reachable base; tried={tried}", file=sys.stderr)

    summary = {
        "ts": time.time(),
        "base_requested": args.base,
        "base": base,
        "tried": tried,
        "warnings": warns,
        "profiles": selected,
        "pass": True,
        "profiles_detail": [],
        "flags_check": {"pass": True, "missing": [], "values": {}},
        "docs_check": {"pass": True, "missing": []},
        "readme_check": {"pass": True, "warnings": []},
    }

    junit_cases = []
    if not base:
        summary["pass"] = False
        junit_cases.append(
            {
                "name": "base::discovery",
                "ok": False,
                "message": "No reachable base discovered",
            }
        )
    else:
        junit_cases.append({"name": "base::discovery", "ok": True, "message": ""})
        for prof in selected:
            res = run_checker(prof, base)
            summary["profiles_detail"].append(res)
            ok = bool(res.get("pass"))
            if not ok:
                summary["pass"] = False
            junit_cases.append(
                {
                    "name": f"profile::{prof}",
                    "ok": ok,
                    "message": "checker failed" if not ok else "",
                }
            )

    # Flags presence
    flags = _load_json(pathlib.Path(args.flags_file))
    feats = (flags.get("features") or {}) if flags else {}
    missing = [k for k in EXPECTED_FLAGS if k not in feats]
    summary["flags_check"]["missing"] = missing
    summary["flags_check"]["values"] = {k: feats.get(k, None) for k in EXPECTED_FLAGS}
    if missing:
        summary["flags_check"]["pass"] = False
        summary["pass"] = False
        junit_cases.append(
            {
                "name": "flags::presence",
                "ok": False,
                "message": f"missing flags: {missing}",
            }
        )
    else:
        junit_cases.append({"name": "flags::presence", "ok": True, "message": ""})

    # Docs presence
    docs_missing = [p for p in REQUIRED_DOCS if not (ROOT / p).exists()]
    summary["docs_check"]["missing"] = docs_missing
    if docs_missing:
        summary["docs_check"]["pass"] = False
        summary["pass"] = False
        junit_cases.append(
            {
                "name": "docs::presence",
                "ok": False,
                "message": f"missing docs: {docs_missing}",
            }
        )
    else:
        junit_cases.append({"name": "docs::presence", "ok": True, "message": ""})

    # README port drift
    try:
        txt = (ROOT / "README.md").read_text(encoding="utf-8")
        if (":8000" in txt) and (":8001" in txt):
            summary["readme_check"]["warnings"].append(
                "README references both :8000 and :8001; standardize or explain dual-port rollover."
            )
    except Exception:
        pass

    pathlib.Path(args.out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.junit:
        junit_write(junit_cases, pathlib.Path(args.junit))
    print(json.dumps(summary, indent=2))
    sys.exit(0 if summary["pass"] else 2)


if __name__ == "__main__":
    main()
