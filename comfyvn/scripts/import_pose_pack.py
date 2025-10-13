# scripts/import_pose_pack.py
# 🚀 Template to import pose packs (images + JSON/skeletons) into your asset system

import os
import json
from typing import Optional, Dict, Any

# Adjust these paths per your project structure
POSE_SOURCE_DIR = "external_pose_packs"
POSE_TARGET_DIR = "comfyvn/assets/poses"
POSE_REGISTRY = "comfyvn/assets/poses/pose_index.json"


# Example internal format for a pose entry
def make_pose_entry(
    pose_id: str, metadata: dict, skeleton: dict, preview_image_path: str
) -> dict:
    return {
        "pose_id": pose_id,
        "metadata": metadata,  # e.g. {"name": "standing", "category": "idle"}
        "skeleton": skeleton,  # e.g. list of keypoints: [{"x": ..., "y": ..., "confidence": ...}, ...]
        "preview_image": preview_image_path,
    }


def load_json_skeleton(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to load JSON skeleton {path}: {e}")
        return None


def import_pose_pack():
    os.makedirs(POSE_TARGET_DIR, exist_ok=True)
    registry = {}
    # load existing registry
    if os.path.exists(POSE_REGISTRY):
        with open(POSE_REGISTRY, "r", encoding="utf-8") as f:
            registry = json.load(f)

    for fname in os.listdir(POSE_SOURCE_DIR):
        full = os.path.join(POSE_SOURCE_DIR, fname)
        name, ext = os.path.splitext(fname)
        # If JSON skeleton file
        if ext.lower() == ".json":
            skeleton = load_json_skeleton(full)
            # find a matching image (png/jpg) with same base name
            for img_ext in (".png", ".jpg", ".jpeg"):
                img_path = os.path.join(POSE_SOURCE_DIR, name + img_ext)
                if os.path.exists(img_path):
                    preview = img_path
                    break
            else:
                preview = ""
            entry = make_pose_entry(
                pose_id=name,
                metadata={"source": "imported_pack"},
                skeleton=skeleton,
                preview_image_path=preview,
            )
            registry[name] = entry
        # If image skeleton (PNG wireframe) only
        elif ext.lower() in (".png", ".jpg", ".jpeg"):
            # Optionally implement image → keypoint conversion via OpenPose / external tool
            entry = make_pose_entry(
                pose_id=name,
                metadata={"source": "imported_pack", "wireframe_only": True},
                skeleton=None,
                preview_image_path=full,
            )
            registry[name] = entry

    # save updated registry
    with open(POSE_REGISTRY, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    print(f"Imported {len(registry)} poses into registry at {POSE_REGISTRY}")


if __name__ == "__main__":
    import_pose_pack()
