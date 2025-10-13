# comfyvn/assets/pose_manager.py
# 🧍 Pose Manager — v0.4.2 Hybrid (Offline + Online + Self-Healing)
# Phase 3.4-H — Asset & Sprite System Integration
# Works with: PoseBrowser, AssetBrowser, ExportManager
# [ComfyVN_Architect]

from __future__ import annotations
import os, json, base64
from datetime import datetime
from typing import Dict, List, Optional, Any

# Optional dependency
try:
    import requests
except Exception:
    requests = None


class PoseManager:
    """Unified offline+online Pose Manager with self-healing preview generation."""

    def __init__(self, data_path: str = "./data/poses"):
        self.data_path = os.path.abspath(data_path)
        os.makedirs(self.data_path, exist_ok=True)
        self.index_path = os.path.join(self.data_path, "pose_index.json")
        self.registry: Dict[str, Dict[str, Any]] = {}
        self.index: Dict[str, Dict[str, Any]] = self._load_index()
        self._load_all_local_poses()
        self._save_index()

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------
    def _pose_file(self, pose_id: str) -> str:
        return os.path.join(self.data_path, f"{pose_id}.json")

    def _load_index(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[PoseManager] ⚠️ Failed to load index: {e}")
        return {}

    def _save_index(self):
        try:
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(self.index, f, indent=2)
        except Exception as e:
            print(f"[PoseManager] ⚠️ Failed to save index: {e}")

    def _normalize_skeleton(self, skel: Any) -> Dict[str, Dict[str, float]]:
        """Normalize skeletons to {id:{x,y}} regardless of source format."""
        norm = {}
        if isinstance(skel, dict):
            for k, v in skel.items():
                if isinstance(v, dict) and "x" in v and "y" in v:
                    norm[str(k)] = {"x": float(v["x"]), "y": float(v["y"])}
                elif isinstance(v, (list, tuple)) and len(v) >= 2:
                    norm[str(k)] = {"x": float(v[0]), "y": float(v[1])}
        elif isinstance(skel, (list, tuple)):
            for i, v in enumerate(skel):
                if isinstance(v, (list, tuple)) and len(v) >= 2:
                    norm[str(i)] = {"x": float(v[0]), "y": float(v[1])}
        return norm

    def _validate_pose(self, pose: Dict[str, Any]):
        return ("pose_id" in pose) and ("skeleton" in pose)

    def _load_all_local_poses(self):
        count = 0
        for root, _, files in os.walk(self.data_path):
            for f in files:
                if not f.endswith(".json") or f == "pose_index.json":
                    continue
                try:
                    with open(os.path.join(root, f), "r", encoding="utf-8") as fh:
                        pose = json.load(fh)
                    if not self._validate_pose(pose):
                        continue
                    pose["skeleton"] = self._normalize_skeleton(
                        pose.get("skeleton", {})
                    )
                    pose.setdefault("metadata", {})
                    pose.setdefault("preview_image", "")
                    pose["metadata"].setdefault(
                        "imported_at", datetime.now().isoformat()
                    )
                    pose["metadata"].setdefault("source", "local")

                    self.registry[pose["pose_id"]] = pose
                    self.index[pose["pose_id"]] = {
                        "file": f,
                        "source": pose["metadata"]["source"],
                        "preview_image": pose["preview_image"],
                        "imported_at": pose["metadata"]["imported_at"],
                    }
                    count += 1
                except Exception as e:
                    print(f"[PoseManager] ⚠️ Skipped {f}: {e}")
        print(f"[PoseManager] Loaded {count} poses from {self.data_path}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_pose(self, pose_id: str) -> Optional[Dict[str, Any]]:
        return self.registry.get(pose_id)

    def list_poses(self) -> List[str]:
        return sorted(self.registry.keys())

    def add_pose(self, pose_id: str, data: Dict[str, Any]) -> bool:
        data["pose_id"] = pose_id
        data["skeleton"] = self._normalize_skeleton(data.get("skeleton", {}))
        data.setdefault(
            "metadata", {"source": "local", "imported_at": datetime.now().isoformat()}
        )
        data.setdefault("preview_image", "")
        path = self._pose_file(pose_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.registry[pose_id] = data
            self.index[pose_id] = {
                "file": os.path.relpath(path, start=self.data_path),
                "source": data["metadata"]["source"],
                "preview_image": data["preview_image"],
                "imported_at": data["metadata"]["imported_at"],
            }
            self._save_index()
            print(f"[PoseManager] ✅ Saved pose '{pose_id}'")
            return True
        except Exception as e:
            print(f"[PoseManager] ❌ Failed to save {pose_id}: {e}")
            return False

    def delete_pose(self, pose_id: str):
        if pose_id in self.registry:
            del self.registry[pose_id]
        if pose_id in self.index:
            del self.index[pose_id]
        try:
            os.remove(self._pose_file(pose_id))
        except Exception:
            pass
        self._save_index()
        print(f"[PoseManager] 🗑 Deleted pose '{pose_id}'")

    # ------------------------------------------------------------------
    # Online Fetch + Built-in Pose
    # ------------------------------------------------------------------
    def auto_fetch_all(self) -> int:
        if requests is None:
            print("[PoseManager] 🌐 Requests not installed — using demo pose.")
            return self._add_builtin_demo_pose()
        urls = {
            "PoseDepot": "https://raw.githubusercontent.com/a-lgil/pose-depot/main/poses.json",
            "DynamicPosePackage": "https://raw.githubusercontent.com/NextDiffusionAI/dynamic-pose-package/main/poses.json",
        }
        imported = 0
        for name, url in urls.items():
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict) and "poses" in data:
                    for pid, pose in data["poses"].items():
                        pose["pose_id"] = pid
                        pose["metadata"] = {
                            "source": name,
                            "imported_at": datetime.now().isoformat(),
                        }
                        if self.add_pose(pid, pose):
                            imported += 1
            except Exception as e:
                print(f"[PoseManager] ⚠️ Failed to fetch {name}: {e}")
        if imported == 0:
            imported = self._add_builtin_demo_pose()
        return imported

    def _add_builtin_demo_pose(self) -> int:
        """Generate built-in stick-figure pose with PNG fallback."""
        preview_path = os.path.join(self.data_path, "standing_default.png")

        # create PNG safely (no Pillow required)
        try:
            from PIL import Image, ImageDraw

            img = Image.new("RGBA", (256, 512), (32, 32, 32, 255))
            d = ImageDraw.Draw(img)
            d.line((128, 400, 128, 120), fill=(220, 220, 220), width=3)
            d.ellipse((118, 90, 138, 110), fill=(255, 255, 255))
            d.line((128, 220, 90, 280), fill=(220, 220, 220), width=3)
            d.line((128, 220, 166, 280), fill=(220, 220, 220), width=3)
            img.save(preview_path)
        except Exception:
            # embedded base64 PNG (1×1 transparent)
            png_data = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAQAAAAAYLlVAAAAFklEQVR4nGNgGAWjYBSMglEwCjAAAKzCAfjxBP2yAAAAAElFTkSuQmCC"
            )
            with open(preview_path, "wb") as f:
                f.write(png_data)

        demo_pose = {
            "pose_id": "standing_default",
            "preview_image": preview_path,
            "metadata": {
                "source": "builtin",
                "imported_at": datetime.now().isoformat(),
                "description": "Default upright stick figure pose.",
            },
            "skeleton": {
                "0": {"x": 128, "y": 400},
                "1": {"x": 128, "y": 300},
                "2": {"x": 128, "y": 200},
                "3": {"x": 128, "y": 120},
                "4": {"x": 90, "y": 280},
                "5": {"x": 166, "y": 280},
            },
        }
        return 1 if self.add_pose("standing_default", demo_pose) else 0

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def summary(self) -> str:
        return (
            f"PoseManager: {len(self.registry)} poses loaded | data: {self.data_path}"
        )


# ----------------------------------------------------------------------
# Dynamic GUI fallback: runtime stickman renderer (Qt)
# ----------------------------------------------------------------------
try:
    from PySide6.QtGui import QPixmap, QPainter, QColor, QPen
    from PySide6.QtCore import Qt

    class PosePreviewGenerator:
        """Used by GUI when preview_image missing."""

        @staticmethod
        def generate(width: int = 256, height: int = 512) -> QPixmap:
            pix = QPixmap(width, height)
            pix.fill(QColor(30, 30, 30))
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor(220, 220, 220))
            pen.setWidth(3)
            p.setPen(pen)
            # draw simple stick
            p.drawLine(width / 2, height * 0.8, width / 2, height * 0.25)
            p.drawEllipse(width / 2 - 10, height * 0.15, 20, 20)
            p.drawLine(width / 2, height * 0.5, width / 2 - 40, height * 0.6)
            p.drawLine(width / 2, height * 0.5, width / 2 + 40, height * 0.6)
            p.end()
            return pix

except Exception:
    PosePreviewGenerator = None

# ----------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    pm = PoseManager()
    print(pm.summary())
    if not pm.list_poses():
        pm.auto_fetch_all()
        print("[PoseManager] Added demo pose")
    print("Available poses:", pm.list_poses())
