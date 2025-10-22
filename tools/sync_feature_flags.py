#!/usr/bin/env python3
import json
import os
import pathlib
import sys

CFG = pathlib.Path("config/comfyvn.json")
DEFAULT_SERVER = {"host": "127.0.0.1", "ports": [8001, 8000], "public_base": None}
FLAGS = {
    "enable_worldlines": False,
    "enable_timeline_overlay": False,
    "enable_depth2d": False,
    "enable_playground": False,
    "enable_stage3d": False,
    "enable_narrator": False,
    "enable_llm_role_mapping": False,
    "enable_battle_sim": False,
    "enable_props": False,
    "enable_weather_overlays": False,
    "enable_themes": False,
    "enable_anim_25d": False,
    "enable_publish_web": False,
    "enable_persona_importers": False,
    "enable_image2persona": False,
    "enable_asset_ingest": False,
    "enable_public_model_hubs": False,
    "enable_public_gpu": False,
    "enable_public_image_video": False,
    "enable_public_translate": False,
    "enable_public_llm": False,
    "enable_marketplace": False,
    "enable_cloud_sync": False,
    "enable_collab": False,
    "enable_security_sandbox": False,
    "enable_accessibility": False,
    "enable_observability": False,
    "enable_perf": False,
    "enable_mini_vn": True,
    "enable_export_bake": False,
}


def main():
    if not CFG.exists():
        print("config/comfyvn.json missing")
        sys.exit(2)
    data = json.loads(CFG.read_text(encoding="utf-8") or "{}")
    server = data.get("server") or {}
    if not server:
        data["server"] = DEFAULT_SERVER
    feats = data.get("features") or {}
    changed = False
    for k, v in FLAGS.items():
        if k not in feats:
            feats[k] = v
            changed = True
    data["features"] = feats
    if changed or not server:
        CFG.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print("Updated config/comfyvn.json")
    else:
        print("No changes needed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
