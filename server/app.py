from __future__ import annotations

# ── stdlib ────────────────────────────────────────────────────────────────────
import os
import json
import glob
import time
import uuid
import base64
import sqlite3
import subprocess
import platform
from datetime import datetime

# ── third-party ───────────────────────────────────────────────────────────────
import requests
from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    render_template,
    session,
    redirect,
    url_for,
)

# ── configuration & paths ─────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))

COMFY_HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
DATA_DIR = os.environ.get("VN_DATA_DIR", os.path.join(ROOT_DIR, "data"))
ASSET_DIR = os.path.join(DATA_DIR, "assets")
DB_PATH = os.path.join(DATA_DIR, "vn.sqlite3")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

AUTH_ENABLED = os.environ.get("VN_AUTH", "0") == "1"
ADMIN_PASSWORD = os.environ.get("VN_PASSWORD", "admin")

# File-system gallery roots
GALLERY_DIR = os.path.join(DATA_DIR, "gallery")
APPROVED_DIR = os.path.join(GALLERY_DIR, "approved")
REJECTED_DIR = os.path.join(GALLERY_DIR, "rejected")

# Ren'Py export roots
RENPY_PROJECT_DIR = os.path.join(DATA_DIR, "renpy_project")
SCRIPT_DIR = os.path.join(RENPY_PROJECT_DIR, "game", "scripts")

# Other data dirs
SUMMARIES_DIR = os.path.join(DATA_DIR, "summaries")
EXPORT_QUEUE_DIR = os.path.join(DATA_DIR, "export_queue")

# Ensure directories exist
for p in [DATA_DIR, ASSET_DIR, GALLERY_DIR, APPROVED_DIR, REJECTED_DIR,
          SUMMARIES_DIR, EXPORT_QUEUE_DIR, SCRIPT_DIR]:
    os.makedirs(p, exist_ok=True)

# ── db helpers ────────────────────────────────────────────────────────────────
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            title TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            png_path TEXT,
            json_sidecar_path TEXT,
            meta_json TEXT,
            tags TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            body TEXT,
            created_at REAL NOT NULL
        )
        """)
        conn.commit()

def _now() -> float:
    return time.time()

init_db()

# ── app init ──────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = base64.urlsafe_b64encode(os.urandom(32))

# ── helpers ───────────────────────────────────────────────────────────────────
def require_auth():
    if not AUTH_ENABLED:
        return None
    if session.get("authed"):
        return None
    return redirect(url_for("login"))

def safe_write_json(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

# ── auth routes ───────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if not AUTH_ENABLED:
        return redirect(url_for("index"))
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == ADMIN_PASSWORD:
            session["authed"] = True
            return redirect(url_for("index"))
        return render_template("login.html", error="Invalid password")
    return render_template("login.html", error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ── core ui ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    auth = require_auth()
    if auth:
        return auth
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify({"ok": True, "comfy_host": COMFY_HOST})

# ── static passthrough (if needed) ────────────────────────────────────────────
@app.get("/static/<path:path>")
def static_proxy(path):
    return send_from_directory(app.static_folder, path)

# ── comfy queue & ingestion (DB-backed assets) ────────────────────────────────
@app.post("/queue")
def queue():
    auth = require_auth()
    if auth:
        return auth
    payload = request.get_json(force=True)
    title = payload.get("title") or "untitled"
    workflow = payload.get("workflow")
    meta = payload.get("meta", {})
    tags_val = meta.get("tags")
    tags = ",".join(tags_val) if isinstance(tags_val, list) else (tags_val or "")

    if not isinstance(workflow, dict):
        return jsonify({"error": "workflow must be an object"}), 400

    asset_id = str(uuid.uuid4())
    sidecar_path = os.path.join(ASSET_DIR, f"{asset_id}.json")
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump({"workflow": workflow, "meta": meta, "title": title}, f, ensure_ascii=False, indent=2)

    with db() as conn:
        conn.execute(
            """INSERT INTO assets (id, status, title, created_at, updated_at,
                                   png_path, json_sidecar_path, meta_json, tags)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (asset_id, "queued", title, _now(), _now(), None, sidecar_path, json.dumps(meta, ensure_ascii=False), tags)
        )
        conn.commit()

    comfy_ok = False
    comfy_resp = None
    try:
        r = requests.post(f"{COMFY_HOST}/prompt", json=workflow, timeout=5)
        comfy_ok = r.status_code in (200, 201, 202)
        if r.headers.get("content-type", "").startswith("application/json"):
            comfy_resp = r.json()
        else:
            comfy_resp = {"text": r.text}
    except Exception as e:
        comfy_resp = {"error": str(e)}

    return jsonify({
        "id": asset_id,
        "queued": True,
        "forwarded_to_comfy": comfy_ok,
        "comfy_response": comfy_resp
    })

@app.get("/gallery")
def gallery_db():
    """DB-backed gallery listing (assets table)."""
    auth = require_auth()
    if auth:
        return auth

    status = request.args.get("status")
    tag = request.args.get("tag")
    q = "SELECT * FROM assets WHERE 1=1"
    args = []
    if status:
        q += " AND status=?"; args.append(status)
    if tag:
        q += " AND (tags LIKE ? OR meta_json LIKE ?)"; args += [f"%{tag}%", f"%{tag}%"]
    q += " ORDER BY created_at DESC"

    with db() as conn:
        rows = conn.execute(q, args).fetchall()
    return jsonify([dict(r) for r in rows])

@app.post("/approve/<asset_id>")
def approve(asset_id: str):
    auth = require_auth()
    if auth:
        return auth
    with db() as conn:
        conn.execute("UPDATE assets SET status=?, updated_at=? WHERE id=?", ("approved", _now(), asset_id))
        conn.commit()
    return jsonify({"id": asset_id, "status": "approved"})

@app.post("/reject/<asset_id>")
def reject(asset_id: str):
    auth = require_auth()
    if auth:
        return auth
    with db() as conn:
        conn.execute("UPDATE assets SET status=?, updated_at=? WHERE id=?", ("rejected", _now(), asset_id))
        conn.commit()
    return jsonify({"id": asset_id, "status": "rejected"})

@app.post("/ingest/<asset_id>")
def ingest(asset_id: str):
    """Attach a PNG (and optional sidecar) to an existing DB asset."""
    auth = require_auth()
    if auth:
        return auth
    if "image" not in request.files:
        return jsonify({"error": "multipart file field 'image' required"}), 400

    img = request.files["image"]
    if not img.filename.lower().endswith(".png"):
        return jsonify({"error": "only .png accepted"}), 400

    png_dir_rel = os.path.join("static", "assets")
    os.makedirs(os.path.join(BASE_DIR, png_dir_rel), exist_ok=True)
    png_path_rel = os.path.join(png_dir_rel, f"{asset_id}.png")
    img.save(os.path.join(BASE_DIR, png_path_rel))

    if "sidecar" in request.files:
        side = request.files["sidecar"]
        side_dir_rel = os.path.join("static", "assets")
        os.makedirs(os.path.join(BASE_DIR, side_dir_rel), exist_ok=True)
        side.save(os.path.join(BASE_DIR, side_dir_rel, f"{asset_id}.json"))

    with db() as conn:
        conn.execute("UPDATE assets SET png_path=?, updated_at=? WHERE id=?", (png_path_rel, _now(), asset_id))
        conn.commit()
    return jsonify({"ok": True, "png_path": png_path_rel})

# ── ren'py export (direct scene beats) ────────────────────────────────────────
@app.post("/export/renpy")
def export_renpy():
    """Build one script from raw beats payload."""
    auth = require_auth()
    if auth:
        return auth

    data = request.get_json(force=True)
    scene_title = data.get("scene_title", "Untitled")
    beats = data.get("beats", [])
    out_dir = os.path.join(DATA_DIR, "renpy_export")
    os.makedirs(out_dir, exist_ok=True)
    script_path = os.path.join(out_dir, "script.rpy")

    def safe(s: str) -> str:
        return str(s).replace('"', '\\"')

    lines = [
        'label start:\n',
        '    scene black\n',
        f'    $ title = "{safe(scene_title)}"\n',
        f'    "Title: {safe(scene_title)}"\n'
    ]

    for b in beats:
        chars = ", ".join([c.get("name", "??") for c in b.get("characters", [])])
        lines.append(f'    # Beat {safe(b.get("id", ""))} ({safe(b.get("timecode", ""))})\n')
        if chars:
            lines.append(f'    "Characters: {safe(chars)}"\n')
        if b.get("shot"):
            lines.append(f'    "Shot: {safe(b["shot"])}"\n')
        if b.get("line"):
            lines.append(f'    "{safe(b["line"])}"\n')
        lines.append('    nvl clear\n')

    with open(script_path, "w", encoding="utf-8") as f:
        f.write("".join(lines))

    return jsonify({"ok": True, "script_path": script_path})

# ── config api ────────────────────────────────────────────────────────────────
@app.route("/api/config", methods=["GET", "POST"])
def config_api():
    if request.method == "GET":
        if not os.path.exists(CONFIG_PATH):
            return jsonify({
                "polling_interval": 5,
                "live_progress": True,
                "auto_approve": False,
                "default_vn_tier": "Simple",
                "theme_mode": "Dark"
            })
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    else:
        data = request.get_json(force=True)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return jsonify({"success": True})

@app.route("/api/status")
def status_api():
    # Placeholder ComfyUI check
    return jsonify({"status": "idle"})

# ── filesystem gallery (separate namespace) ───────────────────────────────────
@app.route("/api/gallery_fs")
def list_gallery_fs():
    images = []
    for path in glob.glob(os.path.join(GALLERY_DIR, "*.png")):
        name = os.path.basename(path)
        meta_path = os.path.splitext(path)[0] + ".json"
        meta = {}
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        images.append({"name": name, "meta": meta})
    return jsonify(images)

@app.route("/api/gallery_fs/<filename>")
def get_gallery_image_fs(filename):
    return send_from_directory(GALLERY_DIR, filename)

@app.route("/api/gallery_fs/decision", methods=["POST"])
def gallery_decision_fs():
    data = request.get_json(force=True)
    fname = data.get("filename")
    decision = data.get("decision")
    if decision not in {"approve", "reject"}:
        return jsonify({"error": "decision must be 'approve' or 'reject'"}), 400

    src = os.path.join(GALLERY_DIR, fname)
    if not os.path.exists(src):
        return jsonify({"error": "file not found"}), 404

    dst_dir = APPROVED_DIR if decision == "approve" else REJECTED_DIR
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, fname)
    os.replace(src, dst)

    meta_src = os.path.splitext(src)[0] + ".json"
    if os.path.exists(meta_src):
        os.replace(meta_src, os.path.splitext(dst)[0] + ".json")
    return jsonify({"success": True, "decision": decision})

# ── comfy sync & summarization & export queue ────────────────────────────────
@app.route("/api/sync/comfyui")
def sync_comfyui():
    """
    Pull new renders from ComfyUI output and link/copy them into data/gallery/.
    """
    comfy_dir = os.path.join(ROOT_DIR, "ComfyUI", "output")  # adjust if needed
    synced = []
    if not os.path.isdir(comfy_dir):
        return jsonify({"synced": synced, "warning": f"ComfyUI output dir not found: {comfy_dir}"})

    for png_path in glob.glob(os.path.join(comfy_dir, "*.png")):
        name = os.path.basename(png_path)
        target = os.path.join(GALLERY_DIR, name)
        if not os.path.exists(target):
            try:
                os.link(png_path, target)
            except Exception:
                import shutil
                shutil.copy(png_path, target)
            meta = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
                "source": "ComfyUI",
                "filename": name,
                "tags": []
            }
            safe_write_json(os.path.splitext(target)[0] + ".json", meta)
            synced.append(name)
    return jsonify({"synced": synced})

@app.route("/api/summary", methods=["POST"])
def generate_summary():
    """
    Create a simple textual summary for a render using metadata/filename.
    """
    data = request.get_json(force=True)
    filename = data.get("filename")
    if not filename:
        return jsonify({"error": "filename required"}), 400

    meta_path = os.path.join(GALLERY_DIR, os.path.splitext(filename)[0] + ".json")
    if not os.path.exists(meta_path):
        return jsonify({"error": "metadata not found"}), 404

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Simulated summary logic; replace with real LLM call if desired
    summary = f"Scene {meta.get('id', '')[:6]}: Generated image '{filename}' from {meta.get('source', 'unknown')}."

    summary_data = {
        "filename": filename,
        "summary": summary,
        "timestamp": datetime.now().isoformat()
    }
    path = os.path.join(SUMMARIES_DIR, f"{os.path.splitext(filename)[0]}_summary.json")
    safe_write_json(path, summary_data)
    return jsonify(summary_data)

@app.route("/api/export_queue", methods=["POST"])
def export_to_queue():
    """
    Add a render to VN export queue for Ren'Py scene generation.
    """
    data = request.get_json(force=True)
    filename = data.get("filename")
    if not filename:
        return jsonify({"error": "filename required"}), 400

    scene_id = str(uuid.uuid4())[:8]
    entry = {
        "scene_id": scene_id,
        "filename": filename,
        "timestamp": datetime.now().isoformat()
    }
    queue_file = os.path.join(EXPORT_QUEUE_DIR, f"{scene_id}.json")
    safe_write_json(queue_file, entry)
    return jsonify({"queued": True, "scene_id": scene_id})

# ── ren'py exporter (from queue/summaries) ────────────────────────────────────
def build_rpy(scene_data: dict) -> str:
    """Generate minimal Ren'Py script content for one scene."""
    fn = scene_data["filename"]
    sid = scene_data["scene_id"]
    summary = scene_data.get("summary", "No summary provided.")
    # Note: In a real project you'd map filenames to image declarations.
    return f"""# Auto-generated by VN Tools
label scene_{sid}:
    scene {fn}
    with fade
    "{summary}"
    return
"""

@app.route("/api/export_renpy", methods=["POST"])
def export_to_renpy():
    """Build .rpy scripts from queued exports and summaries."""
    exported = []
    for qpath in glob.glob(os.path.join(EXPORT_QUEUE_DIR, "*.json")):
        with open(qpath, "r", encoding="utf-8") as f:
            scene = json.load(f)
        fn = scene["filename"]
        sid = scene["scene_id"]
        summary_path = os.path.join(SUMMARIES_DIR, f"{os.path.splitext(fn)[0]}_summary.json")
        if os.path.exists(summary_path):
            with open(summary_path, "r", encoding="utf-8") as f:
                sdata = json.load(f)
                scene["summary"] = sdata.get("summary")

        out_path = os.path.join(SCRIPT_DIR, f"scene_{sid}.rpy")
        if os.path.exists(out_path):
            # skip duplicates
            continue
        rpy_text = build_rpy(scene)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(rpy_text)
        exported.append(out_path)

    # Generate minimal Ren'Py project scaffold if missing
    options_file = os.path.join(RENPY_PROJECT_DIR, "game", "options.rpy")
    if not os.path.exists(options_file):
        os.makedirs(os.path.dirname(options_file), exist_ok=True)
        with open(options_file, "w", encoding="utf-8") as f:
            f.write('define config.window_title = "VN Toolchain Export"\n')

    return jsonify({"exported": exported})

# ── launcher & preview ────────────────────────────────────────────────────────
@app.route("/api/launch_renpy", methods=["POST"])
def launch_renpy():
    """Launch the Ren'Py project via batch (Windows) or shell (Unix)."""
    script = "launch_renpy.bat" if platform.system() == "Windows" else "./launch_renpy.sh"
    try:
        subprocess.Popen([script], shell=True, cwd=ROOT_DIR)
        return jsonify({"status": "launched"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/preview/<scene_id>")
def preview_scene(scene_id):
    """Lightweight HTML viewer for exported scene scripts."""
    path = os.path.join(SCRIPT_DIR, f"scene_{scene_id}.rpy")
    if not os.path.exists(path):
        return "<h3>Scene not found</h3>", 404
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    return f"""
    <html>
    <head><title>Preview {scene_id}</title>
    <style>
      body {{ background:#111; color:#eee; font-family:sans-serif; padding:20px; }}
      pre {{ background:#222; padding:15px; border-radius:8px; white-space:pre-wrap; }}
      a, a:visited {{ color:#9cf; }}
    </style>
    </head>
    <body>
    <h2>Preview Scene {scene_id}</h2>
    <pre>{txt}</pre>
    </body></html>
    """

# ── main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Note: place your templates/ and static/ next to this file (server/).
    # Run with:  python server/app.py
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
