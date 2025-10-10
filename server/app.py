import os
import io
import json
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, request, jsonify, send_file, session, redirect, url_for, render_template
from functools import wraps

import requests

# --- Optional thumbnail support (Pillow). If not installed, thumbnails are skipped gracefully.
try:
    from PIL import Image
    PIL_OK = True
except Exception:
    PIL_OK = False

# -------------------------------
# Paths & Defaults
# -------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CONFIG_PATH = DATA_DIR / "config.json"
DB_PATH = DATA_DIR / "vn.sqlite3"  # not required for Phases 1–2, but kept if you already use it
GALLERY_DIR = DATA_DIR / "gallery"
APPROVED_DIR = GALLERY_DIR / "approved"
REJECTED_DIR = GALLERY_DIR / "rejected"
SUMMARIES_DIR = DATA_DIR / "summaries"
EXPORT_QUEUE_DIR = DATA_DIR / "export_queue"
ASSETS_DIR = DATA_DIR / "assets"
THUMBS_DIR = GALLERY_DIR / "_thumbs"
LOGS_DIR = ROOT / "logs"

RENPI_BIN_DIR = ROOT / "renpy"        # contains renpy.exe
RENPI_EXE = RENPI_BIN_DIR / "renpy.exe"
RENPI_PROJECT = ROOT / "renpy_project"  # we generate a minimal project here
RENPI_GAME = RENPI_PROJECT / "game"
RENPI_IMAGES = RENPI_GAME / "images"

# For ComfyUI outputs. This can be overridden in config.json
DEFAULT_COMFY_OUTPUT = (ROOT / "ComfyUI" / "output")  # typical structure if ComfyUI lives alongside this repo

# Ensure directories
for p in [DATA_DIR, GALLERY_DIR, APPROVED_DIR, REJECTED_DIR, SUMMARIES_DIR, EXPORT_QUEUE_DIR, ASSETS_DIR, THUMBS_DIR, LOGS_DIR, RENPI_PROJECT, RENPI_GAME, RENPI_IMAGES]:
    p.mkdir(parents=True, exist_ok=True)

# -------------------------------
# Logging (simple file logger)
# -------------------------------
import logging
LOG_FILE = LOGS_DIR / "app.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger("comfyvn")

# -------------------------------
# Config Helpers
# -------------------------------
DEFAULT_CONFIG = {
    "comfyui_url": "http://127.0.0.1:8188",
    "comfyui_output_dir": str(DEFAULT_COMFY_OUTPUT),
    "thumbnail_max": 512,
    "poll_interval_seconds": 3,
    "ui_theme": "dark",
    "renpy_exe": str(RENPI_EXE),
    "renpy_project_dir": str(RENPI_PROJECT),
    "save_fullsize_in_approved": True
}

def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # merge defaults to keep new keys
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception as e:
            logger.exception("Failed to read config.json, using defaults.")
    return DEFAULT_CONFIG.copy()

def save_config(cfg: Dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

CONFIG = load_config()
save_config(CONFIG)  # ensure any missing defaults get written

# -------------------------------
# Secret & Helper App
# -------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("VN_SECRET_KEY", os.urandom(24))
AUTH_ENABLED = os.environ.get("VN_AUTH", "0") == "1"

def require_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not AUTH_ENABLED:
            return func(*args, **kwargs)
        if session.get("user"):
            return func(*args, **kwargs)
        return redirect(url_for("login_page"))
    return wrapper

# -------------------------------
# Login Route
# -------------------------------
@app.route("/login", methods=["GET", "POST"])
def login_page():
    if not AUTH_ENABLED:
        return redirect(url_for("ui_index"))
    if request.method == "POST":
        user = request.form.get("username","").strip()
        pwd = request.form.get("password","").strip()
        if user and pwd == CONFIG.get("admin_password", "admin"):
            session["user"] = user
            return redirect(url_for("ui_index"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html", error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

# -------------------------------
# Gallery Functions
# -------------------------------
def user_dir(subfolder="gallery"):
    user = session.get("user", "default")
    base = DATA_DIR / "users" / user
    (base / subfolder).mkdir(parents=True, exist_ok=True)
    return base / subfolder

# -------------------------------
# Utilities
# -------------------------------
def is_image_file(p: Path) -> bool:
    return p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}

def new_id() -> str:
    return uuid.uuid4().hex[:16]

def ts() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def make_thumb(src: Path, dst: Path, max_size: int) -> None:
    if not PIL_OK:
        return
    try:
        with Image.open(src) as im:
            im.thumbnail((max_size, max_size))
            dst.parent.mkdir(parents=True, exist_ok=True)
            # Preserve format where possible; default to PNG
            fmt = "PNG"
            if im.format in {"PNG", "JPEG", "WEBP"}:
                fmt = im.format
            im.save(dst, format=fmt, optimize=True)
    except Exception:
        logger.exception(f"Thumbnail generation failed for {src}")

def list_gallery_folder(folder: Path, status: str) -> List[Dict[str, Any]]:
    items = []
    for p in sorted(folder.glob("*")):
        if p.is_file() and is_image_file(p):
            stem = p.stem
            thumb = THUMBS_DIR / f"{stem}.png"
            if not thumb.exists():
                make_thumb(p, thumb, int(CONFIG.get("thumbnail_max", 512)))
            meta = {
                "id": stem,
                "filename": p.name,
                "status": status,
                "path": str(p),
                "thumb": str(thumb) if thumb.exists() else None,
                "mtime": os.path.getmtime(p),
            }
            # attach sidecar metadata json if present
            meta_json = p.with_suffix(".json")
            if meta_json.exists():
                try:
                    meta["metadata"] = json.loads(meta_json.read_text(encoding="utf-8"))
                except Exception:
                    meta["metadata_error"] = True
            items.append(meta)
    return items

def ensure_renpy_project():
    """
    Make sure minimal Ren'Py project exists with a safe script.rpy and gui files.
    """
    RENPI_PROJECT.mkdir(parents=True, exist_ok=True)
    RENPI_GAME.mkdir(parents=True, exist_ok=True)
    RENPI_IMAGES.mkdir(parents=True, exist_ok=True)

    script_file = RENPI_GAME / "script.rpy"
    if not script_file.exists():
        script_file.write_text(
            "# Auto-generated by ComfyVN Toolchain\n"
            f"label start_{session.get('user','default')}:\n"
            "    scene black\n"
            "    \"Project initialized. Use the exporter to add scenes.\"\n"
            "    return\n",
            encoding="utf-8"
        )

def build_renpy_script_from_approved(approved_images: List[Path]) -> None:
    """
    Create a simple linear VN that shows each approved image in order,
    with a click-to-continue flow. Ensures `label start` exists.
    """
    ensure_renpy_project()

    # Copy images
    copied = []
    for img in approved_images:
        dst = RENPI_IMAGES / img.name
        try:
            shutil.copy2(img, dst)
            copied.append(dst)
        except Exception:
            logger.exception(f"Failed to copy {img} to Ren'Py images.")

    # Build script
    lines = [
        "# Auto-generated by ComfyVN Toolchain",
        "define config.developer = True",
        "",
        f"label start_{session.get('user','default')}:",
    ]
    if not copied:
        lines += [
            "    scene black",
            "    \"No approved images yet. Please approve items in the gallery and export again.\"",
            "    return",
        ]
    else:
        lines += ["    scene black"]
        for i, img in enumerate(copied, start=1):
            # simple scene for each image
            lines += [
                f"    # Scene {i}",
                f"    scene expression \"images/{img.name}\"",
                "    with fade",
                "    \"(Click to continue)\"",
                "",
            ]
        lines += ["    return"]

    script_file = RENPI_GAME / "script.rpy"
    script_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(f"Ren'Py script generated with {len(copied)} scenes at {script_file}")

# -------------------------------
# API: Health & Config
# -------------------------------
@app.get("/health")
def health():
    comfy_url = CONFIG.get("comfyui_url")
    ok = True
    comfy_ok = False
    try:
        # light-weight check
        r = requests.get(comfy_url, timeout=2)
        comfy_ok = r.status_code < 500
    except Exception:
        comfy_ok = False
        ok = False
    return jsonify({
        "ok": ok,
        "service": "ComfyVN",
        "time": ts(),
        "comfyui_url": comfy_url,
        "comfyui_ok": comfy_ok
    })

@app.get("/api/config")
def get_config():
    return jsonify(load_config())

@app.post("/api/config")
def post_config():
    try:
        incoming = request.get_json(force=True, silent=False) or {}
        cfg = load_config()
        cfg.update(incoming)
        save_config(cfg)
        return jsonify({"ok": True, "config": cfg})
    except Exception:
        logger.exception("Failed to update config.")
        return jsonify({"ok": False, "error": "config_write_failed"}), 400

# -------------------------------
# API: ComfyUI Queue (simple)
# -------------------------------
@app.post("/queue")
def queue_workflow():
    """
    For now, forwards a JSON payload to ComfyUI /prompt endpoint (standard API).
    Body should contain the workflow JSON expected by ComfyUI.
    """
    cfg = load_config()
    comfy_url = cfg.get("comfyui_url", DEFAULT_CONFIG["comfyui_url"]).rstrip("/")
    url = comfy_url + "/prompt"
    try:
        payload = request.get_json(force=True, silent=False)
        r = requests.post(url, json=payload, timeout=10)
        return jsonify({
            "ok": r.status_code < 300,
            "status_code": r.status_code,
            "response": r.json() if "application/json" in r.headers.get("content-type","") else r.text
        }), r.status_code
    except Exception:
        logger.exception("Queue to ComfyUI failed.")
        return jsonify({"ok": False, "error": "queue_failed"}), 400

# -------------------------------
# API: Gallery
# -------------------------------
@app.get("/api/gallery")
@require_auth
def api_gallery():
    """
    Returns approved and rejected lists plus any loose items in /data/users/<user>/gallery
    (You should mostly see items only in subfolders.)
    """
    gallery_path = user_dir("gallery")
    approved_path = user_dir("gallery/approved")
    rejected_path = user_dir("gallery/rejected")
    items = []
    items += list_gallery_folder(approved_path, "approved")
    items += list_gallery_folder(rejected_path, "rejected")
    # Any loose images (treat as 'pending')
    for p in sorted(gallery_path.glob("*")):
        if p.is_file() and is_image_file(p):
            stem = p.stem
            thumb = THUMBS_DIR / f"{stem}.png"
            if not thumb.exists():
                make_thumb(p, thumb, int(CONFIG.get("thumbnail_max", 512)))
            items.append({
                "id": stem,
                "filename": p.name,
                "status": "pending",
                "path": str(p),
                "thumb": str(thumb) if thumb.exists() else None,
                "mtime": os.path.getmtime(p),
            })
    return jsonify({"ok": True, "items": items})

@app.post("/api/gallery/decision")
@require_auth
def api_gallery_decision():
    """
    Body: { "id": "<stem>", "action": "approve" | "reject" }
    Moves the image (and its .json sidecar if present) to the appropriate folder.
    """
    try:
        data = request.get_json(force=True, silent=False)
        img_id = data.get("id")
        action = data.get("action")
        if action not in {"approve", "reject"}:
            return jsonify({"ok": False, "error": "invalid_action"}), 400

        gallery_path = user_dir("gallery")
        approved_path = user_dir("gallery/approved")
        rejected_path = user_dir("gallery/rejected")

        # find candidate by checking places
        candidates = [
            gallery_path / f"{img_id}.png",
            gallery_path / f"{img_id}.jpg",
            gallery_path / f"{img_id}.jpeg",
            approved_path / f"{img_id}.png",
            approved_path / f"{img_id}.jpg",
            rejected_path / f"{img_id}.png",
            rejected_path / f"{img_id}.jpg",
        ]
        src = None
        for c in candidates:
            if c.exists():
                src = c
                break
        if not src:
            return jsonify({"ok": False, "error": "not_found"}), 404

        if action == "approve":
            dst_dir = approved_path
        else:
            dst_dir = rejected_path
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        shutil.move(str(src), str(dst))

        # move sidecar json and thumb if present
        for side_ext in (".json",):
            sc = src.with_suffix(side_ext)
            if sc.exists():
                shutil.move(str(sc), str(dst.with_suffix(side_ext)))
        # thumbs: just recreate to be safe
        thumb = THUMBS_DIR / f"{dst.stem}.png"
        if thumb.exists():
            try:
                thumb.unlink()
            except Exception:
                pass
        make_thumb(dst, thumb, int(CONFIG.get("thumbnail_max", 512)))

        return jsonify({"ok": True, "moved_to": str(dst)})
    except Exception:
        logger.exception("Gallery decision failed.")
        return jsonify({"ok": False, "error": "decision_failed"}), 400

# -------------------------------
# API: Sync from ComfyUI outputs
# -------------------------------
@app.post("/api/sync/comfyui")
@require_auth
def api_sync_comfyui():
    """
    Scan the ComfyUI output folder for new images and import them into /data/users/<user>/gallery
    with an ID and sidecar metadata (basic).
    Body (optional): { "output_dir": "..." }
    """
    try:
        body = request.get_json(silent=True) or {}
        cfg = load_config()
        out_dir = Path(body.get("output_dir") or cfg.get("comfyui_output_dir") or DEFAULT_COMFY_OUTPUT)
        if not out_dir.exists():
            return jsonify({"ok": False, "error": f"output_dir_not_found: {out_dir}"}), 400

        gallery_path = user_dir("gallery")
        approved_path = user_dir("gallery/approved")
        rejected_path = user_dir("gallery/rejected")

        imported = []
        for p in sorted(out_dir.glob("*")):
            if p.is_file() and is_image_file(p):
                # Avoid re-importing if already present (by content name match)
                target = gallery_path / p.name
                if target.exists() or (approved_path / p.name).exists() or (rejected_path / p.name).exists():
                    continue
                new_name = p.name  # keep original name for traceability
                dst = gallery_path / new_name
                shutil.copy2(p, dst)

                # Attempt to capture a basic sidecar metadata
                sidecar = dst.with_suffix(".json")
                if not sidecar.exists():
                    meta = {
                        "id": dst.stem,
                        "source": "comfyui",
                        "origin_path": str(p),
                        "imported_at": ts()
                    }
                    sidecar.write_text(json.dumps(meta, indent=2), encoding="utf-8")

                # Make thumb
                thumb = THUMBS_DIR / f"{dst.stem}.png"
                make_thumb(dst, thumb, int(cfg.get("thumbnail_max", 512)))
                imported.append(dst.name)

        return jsonify({"ok": True, "imported": imported})
    except Exception:
        logger.exception("Sync from ComfyUI failed.")
        return jsonify({"ok": False, "error": "sync_failed"}), 400

@app.route("/")
@require_auth
def ui_index():
    return send_file("templates/index.html")

@app.get("/api/status")
@require_auth
def ui_status():
    """Live status poller for UI."""
    gallery_path = user_dir("gallery")
    approved_path = user_dir("gallery/approved")
    return jsonify({
        "time": ts(),
        "comfyui_ok": requests.get(CONFIG["comfyui_url"]).ok if CONFIG["comfyui_url"] else False,
        "approved": len(list(approved_path.glob("*.png"))),
        "pending": len(list(gallery_path.glob("*.png"))),
    })

# -------------------------------
# API: Export to Ren'Py
# -------------------------------
@app.post("/api/export_renpy")
@require_auth
def api_export_renpy():
    """
    Build a multi-route Ren'Py project.
    Each user gets a separate label and scenes folder.
    """
    try:
        user = session.get("user", "default")
        user_gallery = user_dir("gallery/approved")

        scenes = [p for p in sorted(user_gallery.glob("*"))
                  if p.is_file() and is_image_file(p)]
        if not scenes:
            return jsonify({"ok": False, "error": "no_scenes"}), 400

        # --- build per-user script folder ---
        route_dir = RENPI_GAME / "scripts" / user
        route_dir.mkdir(parents=True, exist_ok=True)

        # remove old scenes
        for old in route_dir.glob("scene_*.rpy"):
            old.unlink()

        # copy images
        for img in scenes:
            shutil.copy2(img, RENPI_IMAGES / img.name)

        # --- create route script ---
        lines = [
            f"# Auto-generated route for {user}",
            f"label start_{user}:",
            "    scene black",
            f"    \"{user}'s route begins!\"",
            ""
        ]
        for i, img in enumerate(scenes, 1):
            lines += [
                f"    # Scene {i}",
                f"    scene expression \"images/{img.name}\"",
                "    with fade",
                "    \"(Click to continue)\"",
                ""
            ]
        lines.append("    return\n")

        out_path = route_dir / f"route_{user}.rpy"
        out_path.write_text("\n".join(lines), encoding="utf-8")

        logger.info(f"Built route for {user} with {len(scenes)} scenes.")

        # --- rebuild master start.rpy menu ---
        start_file = RENPI_GAME / "start.rpy"
        route_labels = [f"start_{d.name}" for d in (RENPI_GAME / "scripts").iterdir() if d.is_dir()]
        menu_lines = [
            "# Master start menu – generated by ComfyVN",
            "label start:",
            "    scene black",
            "    menu:",
        ]
        for label in route_labels:
            username = label.replace("start_","")
            menu_lines.append(f"        \"Play route for {username}\":")
            menu_lines.append(f"            jump {label}")
        menu_lines.append("    return\n")
        start_file.write_text("\n".join(menu_lines), encoding="utf-8")

        return jsonify({"ok": True, "routes": route_labels})
    except Exception:
        logger.exception("Multi-route export failed.")
        return jsonify({"ok": False, "error": "export_failed"}), 400


# -------------------------------
# API: Launch Ren'Py
# -------------------------------
@app.post("/api/launch_renpy")
@require_auth
def api_launch_renpy():
    """
    Launch the Ren'Py project using renpy.exe (Windows).
    """
    try:
        cfg = load_config()
        renpy_exe = Path(cfg.get("renpy_exe") or RENPI_EXE)
        project_dir = Path(cfg.get("renpy_project_dir") or RENPI_PROJECT)
        if not renpy_exe.exists():
            return jsonify({"ok": False, "error": f"renpy_exe_not_found: {renpy_exe}"}), 400
        if not project_dir.exists():
            ensure_renpy_project()

        # Prefer to (re)export before launch so 'start' exists:
        approved_path = user_dir("gallery/approved")
        approved_imgs = [p for p in sorted(approved_path.glob("*")) if p.is_file() and is_image_file(p)]
        build_renpy_script_from_approved(approved_imgs)

        # Launch Ren’Py
        # If you want the launcher UI: pass only the Ren'Py dir.
        # To run the project directly, pass the project directory.
        try:
            subprocess.Popen([str(renpy_exe), str(project_dir)], cwd=str(RENPI_BIN_DIR))
        except Exception:
            # Fallback: try running EXE without forcing cwd
            subprocess.Popen([str(renpy_exe), str(project_dir)])
        return jsonify({"ok": True, "launched": True})
    except Exception:
        logger.exception("Launch Ren'Py failed.")
        return jsonify({"ok": False, "error": "launch_failed"}), 400

# -------------------------------
# Static helpers for thumbs / files
# -------------------------------
@app.get("/api/thumb/<stem>")
@require_auth
def get_thumb(stem: str):
    gallery_path = user_dir("gallery")
    for ext in (".png", ".jpg", ".jpeg"):
        img = gallery_path / f"{stem}{ext}"
        if img.exists():
            thumb = THUMBS_DIR / f"{stem}.png"
            if not thumb.exists():
                make_thumb(img, thumb, int(CONFIG.get("thumbnail_max", 512)))
            if thumb.exists():
                return send_file(str(thumb))
    return jsonify({"ok": False, "error": "not_found"}), 404

# -------------------------------
# Login Template Route
# -------------------------------
@app.route("/login.html")
def login_html():
    return render_template("login.html")

# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":
    # Make sure config and project skeleton exist
    ensure_renpy_project()

    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    debug = bool(int(os.environ.get("FLASK_DEBUG", "0")))
    logger.info(f"Starting ComfyVN server on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)