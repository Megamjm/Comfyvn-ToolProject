from __future__ import annotations
from PySide6.QtGui import QAction
import json, shutil, uuid
from pathlib import Path
from typing import Optional

PROJECTS_DIR = Path("projects")
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
LAST_PTR = PROJECTS_DIR / ".last"

class Project:
    def __init__(self, root: Path):
        self.root = root
        self.meta_path = root / "project.cvnproj"
        self.meta = {}
        if self.meta_path.exists():
            try:
                self.meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            except Exception:
                self.meta = {}

    @property
    def name(self) -> str:
        return self.meta.get("name") or self.root.name

    def save_meta(self):
        self.meta.setdefault("id", str(uuid.uuid4()))
        self.meta.setdefault("name", self.root.name)
        self.meta_path.write_text(json.dumps(self.meta, indent=2), encoding="utf-8")

def new_project(name: str) -> Project:
    root = PROJECTS_DIR / name
    root.mkdir(parents=True, exist_ok=True)
    p = Project(root)
    p.meta.update({"name": name, "version": "0.1"})
    p.save_meta()
    (root / "assets").mkdir(exist_ok=True)
    (root / "scenes").mkdir(exist_ok=True)
    (root / "exports").mkdir(exist_ok=True)
    set_last_project(name)
    return p

def load_project(name: str) -> Optional[Project]:
    root = PROJECTS_DIR / name
    if not root.exists():
        return None
    p = Project(root)
    set_last_project(name)
    return p

def save_project_as(p: Project, new_name: str) -> Project:
    new_root = PROJECTS_DIR / new_name
    new_root.parent.mkdir(parents=True, exist_ok=True)
    if not new_root.exists():
        shutil.copytree(p.root, new_root)
    p2 = Project(new_root)
    p2.meta["name"] = new_name
    p2.save_meta()
    set_last_project(new_name)
    return p2

def list_projects() -> list[str]:
    return [d.name for d in PROJECTS_DIR.iterdir() if d.is_dir() and (d/"project.cvnproj").exists()]

def get_last_project_name() -> Optional[str]:
    try:
        return LAST_PTR.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None

def set_last_project(name: str):
    LAST_PTR.write_text(name, encoding="utf-8")