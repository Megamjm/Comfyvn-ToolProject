from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from comfyvn.gui.central.vn_viewer import MiniVNFallbackWidget
from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.viewer.minivn.player import MiniVNPlayer

LOGGER = logging.getLogger(__name__)


def _preview_text(scene: MappingLike) -> str:
    dialogue = scene.get("dialogue") or scene.get("lines") or []
    if isinstance(dialogue, Iterable):
        for entry in dialogue:
            if isinstance(entry, str):
                stripped = entry.strip()
                if stripped:
                    return stripped
            elif isinstance(entry, dict):
                text = (
                    entry.get("text") or entry.get("line") or entry.get("content") or ""
                )
                if isinstance(text, str) and text.strip():
                    return text.strip()
    title = scene.get("title")
    return str(title).strip() if isinstance(title, str) else ""


def _scene_digest(scene: MappingLike) -> str:
    try:
        payload = json.dumps(scene, sort_keys=True, separators=(",", ":"))
    except Exception:
        payload = json.dumps({"scene": scene.get("id")})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_lines(scene: MappingLike) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    dialogue = scene.get("dialogue") or scene.get("lines") or []
    if not isinstance(dialogue, Iterable):
        return lines
    for entry in dialogue:
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                lines.append({"speaker": "", "text": text, "choices": []})
            continue
        if not isinstance(entry, dict):
            continue
        text = entry.get("text") or entry.get("line") or entry.get("content") or ""
        if isinstance(text, (list, tuple)):
            text = " ".join(str(part) for part in text if part)
        speaker = entry.get("speaker") or entry.get("character") or entry.get("name")
        speaker = str(speaker).strip() if isinstance(speaker, str) else ""
        choices = entry.get("choices") or entry.get("options") or []
        normalized: List[str] = []
        if isinstance(choices, Iterable):
            for choice in choices:
                if isinstance(choice, str) and choice.strip():
                    normalized.append(choice.strip())
                elif isinstance(choice, dict):
                    label = choice.get("text") or choice.get("label") or ""
                    if isinstance(label, str) and label.strip():
                        normalized.append(label.strip())
        lines.append(
            {
                "speaker": speaker,
                "text": str(text).strip(),
                "choices": normalized,
            }
        )
    return lines


MappingLike = Dict[str, Any]


class _ScenePlayerDialog(QDialog):
    def __init__(self, scene: MappingLike, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(scene.get("title") or f"Scene {scene.get('id')}")
        self.resize(540, 420)

        self._scene = scene
        self._lines = _extract_lines(scene)
        self._index = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._header = QLabel(self)
        self._header.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._header)

        self._viewer = QTextBrowser(self)
        self._viewer.setOpenExternalLinks(False)
        self._viewer.setReadOnly(True)
        self._viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._viewer, 1)

        self._choices_label = QLabel(self)
        self._choices_label.setWordWrap(True)
        self._choices_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self._choices_label)

        controls = QHBoxLayout()
        self._prev_btn = QPushButton("Previous", self)
        self._next_btn = QPushButton("Next", self)
        self._close_btn = QPushButton("Close", self)
        controls.addWidget(self._prev_btn)
        controls.addWidget(self._next_btn)
        controls.addStretch(1)
        controls.addWidget(self._close_btn)
        layout.addLayout(controls)

        self._prev_btn.clicked.connect(self._previous)
        self._next_btn.clicked.connect(self._next)
        self._close_btn.clicked.connect(self.accept)

        self._update_meta()
        self._next()

    def _update_meta(self) -> None:
        title = self._scene.get("title") or "Scene"
        scene_id = self._scene.get("id") or self._scene.get("scene_id") or ""
        pov = self._scene.get("pov") or self._scene.get("perspective") or ""
        parts = [title]
        if scene_id:
            parts.append(f"({scene_id})")
        if pov:
            parts.append(f"POV: {pov}")
        self._header.setText(" ".join(parts))

    def _previous(self) -> None:
        if self._index <= 0:
            self._index = -1
        else:
            self._index -= 2
        self._next()

    def _next(self) -> None:
        self._index += 1
        if self._index >= len(self._lines):
            self._viewer.setPlainText("End of scene.")
            self._choices_label.clear()
            self._next_btn.setEnabled(False)
            return
        entry = self._lines[self._index]
        speaker = entry.get("speaker") or ""
        speaker_prefix = f"{speaker}: " if speaker else ""
        self._viewer.setPlainText(f"{speaker_prefix}{entry.get('text') or ''}")
        choices = entry.get("choices") or []
        if choices:
            rendered = "\n".join(f"- {choice}" for choice in choices)
            self._choices_label.setText(f"Choices:\n{rendered}")
        else:
            self._choices_label.clear()
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(True)


class VnLoaderPanel(QWidget):
    """Visual novel loader + debugger surface for project builds and Mini-VN previews."""

    def __init__(
        self,
        bridge: Optional[ServerBridge] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.bridge = bridge or ServerBridge()
        self._projects: List[MappingLike] = []
        self._scene_cache: Dict[str, MappingLike] = {}
        self._build_inflight = False
        self._init_ui()
        self._refresh_projects()

    # ------------------------------------------------------------------ UI --
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("VN Loader Panel", self)
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Select a compiled VN project, trigger rebuilds, and preview scenes using the Mini-VN fallback."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        selector_row = QHBoxLayout()
        selector_label = QLabel("Project:", self)
        self.projects = QComboBox(self)
        self.projects.currentIndexChanged.connect(self._refresh_scenes)
        self.btn_projects_refresh = QPushButton("Refresh", self)
        self.btn_projects_refresh.clicked.connect(self._refresh_projects)
        selector_row.addWidget(selector_label)
        selector_row.addWidget(self.projects, 1)
        selector_row.addWidget(self.btn_projects_refresh)
        layout.addLayout(selector_row)

        controls = QHBoxLayout()
        self.btn_build = QPushButton("Build from Imports", self)
        self.btn_rebuild = QPushButton("Rebuild Timeline", self)
        self.btn_play = QPushButton("Play from Here", self)
        self.btn_view = QPushButton("Open in Viewer", self)
        self.btn_renpy = QPushButton("Open in Ren'Py", self)
        controls.addWidget(self.btn_build)
        controls.addWidget(self.btn_rebuild)
        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_view)
        controls.addWidget(self.btn_renpy)
        layout.addLayout(controls)

        self.scenes = QListWidget(self)
        self.scenes.setSelectionMode(QListWidget.SingleSelection)
        self.scenes.itemDoubleClicked.connect(lambda *_: self._play_scene())
        layout.addWidget(self.scenes, 1)

        self.status = QLabel("", self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.debug_output = QPlainTextEdit(self)
        self.debug_output.setReadOnly(True)
        self.debug_output.setMaximumBlockCount(800)
        self.debug_output.setPlaceholderText(
            "API responses and debug hooks appear here."
        )
        layout.addWidget(self.debug_output, 1)

        self.hooks_label = QLabel(
            "API hooks:\n"
            "- GET /api/vn/projects — enumerate build targets.\n"
            "- POST /api/vn/build — rebuild from imports.\n"
            "- GET /api/vn/scenes?projectId=… — list compiled scenes.\n"
            "- GET /api/vn/preview/{scene_id} — fetch scene payload.\n"
            "- POST /api/viewer/start — launch native viewer or Mini-VN fallback.",
            self,
        )
        self.hooks_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.hooks_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.hooks_label)

        self.btn_build.clicked.connect(self._build_from_imports)
        self.btn_rebuild.clicked.connect(self._rebuild)
        self.btn_play.clicked.connect(self._play_scene)
        self.btn_view.clicked.connect(self._open_in_viewer)
        self.btn_renpy.clicked.connect(self._open_in_renpy)

    # ----------------------------------------------------------------- Util --
    def _log_debug(self, context: str, payload: Any) -> None:
        text: str
        try:
            text = json.dumps(payload, indent=2, ensure_ascii=False)
        except Exception:
            text = repr(payload)
        self.debug_output.appendPlainText(f"[{context}] {text}")
        cursor = self.debug_output.textCursor()
        cursor.movePosition(cursor.End)
        self.debug_output.setTextCursor(cursor)

    def _set_status(self, message: str, *, success: bool = False) -> None:
        color = "#16a085" if success else "#c0392b"
        if not message:
            self.status.clear()
            return
        self.status.setText(f'<span style="color:{color};">{message}</span>')

    def _current_project(self) -> Optional[MappingLike]:
        index = self.projects.currentIndex()
        if index < 0:
            return None
        project = self.projects.itemData(index)
        return project if isinstance(project, dict) else None

    def _current_scene_item(self) -> Optional[QListWidgetItem]:
        item = self.scenes.currentItem()
        return item

    def _current_scene(self) -> Optional[MappingLike]:
        item = self._current_scene_item()
        if not item:
            return None
        data = item.data(Qt.UserRole)
        return data if isinstance(data, dict) else None

    def _normalize_projects(self, payload: Any) -> List[MappingLike]:
        items: Iterable[Any]
        if isinstance(payload, dict):
            items = payload.get("items") or payload.get("projects") or []
        elif isinstance(payload, list):
            items = payload
        else:
            items = []
        normalized: List[MappingLike] = []
        for entry in items:
            project: MappingLike
            if isinstance(entry, dict):
                project_id = (
                    entry.get("id")
                    or entry.get("project_id")
                    or entry.get("slug")
                    or entry.get("name")
                )
                if not project_id:
                    continue
                label = (
                    entry.get("title")
                    or entry.get("display_name")
                    or entry.get("label")
                    or str(project_id)
                )
                path = (
                    entry.get("project_path")
                    or entry.get("path")
                    or entry.get("root")
                    or entry.get("workspace")
                )
                project = {
                    "id": str(project_id),
                    "title": str(label),
                    "path": str(path) if isinstance(path, str) else "",
                    "meta": entry,
                }
            elif isinstance(entry, str):
                project = {"id": entry, "title": entry, "path": "", "meta": {}}
            else:
                continue
            normalized.append(project)
        return normalized

    def _normalize_scenes(self, payload: Any) -> List[MappingLike]:
        items: Iterable[Any]
        if isinstance(payload, dict):
            items = payload.get("items") or payload.get("scenes") or []
        elif isinstance(payload, list):
            items = payload
        else:
            items = []
        normalized: List[MappingLike] = []
        for entry in items:
            if isinstance(entry, dict):
                scene_id = entry.get("id") or entry.get("scene_id")
                if not scene_id:
                    continue
                title = entry.get("title") or entry.get("label") or scene_id
                normalized.append(
                    {
                        "id": str(scene_id),
                        "title": str(title),
                        "timeline_id": entry.get("timeline")
                        or entry.get("timeline_id"),
                        "meta": entry,
                    }
                )
            elif isinstance(entry, str):
                normalized.append({"id": entry, "title": entry, "meta": {"id": entry}})
        return normalized

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        context: str,
        timeout: float = 8.0,
    ) -> Optional[Any]:
        try:
            if method.upper() == "GET":
                result = self.bridge.get_json(
                    path, params=params or payload, timeout=timeout
                )
            else:
                result = self.bridge.post_json(
                    path, payload or {}, timeout=timeout, default=None
                )
                if result is None:
                    result = {"ok": False, "error": "no response"}
        except Exception as exc:
            LOGGER.warning("%s request failed: %s", context, exc)
            self._set_status(f"{context} failed: {exc}")
            return None

        if not isinstance(result, dict):
            self._set_status(f"{context} failed: unexpected response")
            return None
        self._log_debug(context, result)
        if not result.get("ok"):
            error = (
                result.get("error")
                or (result.get("data") if isinstance(result.get("data"), str) else None)
                or "request failed"
            )
            self._set_status(f"{context} failed: {error}")
            return None
        return result.get("data")

    # ----------------------------------------------------------- Workflows --
    def _refresh_projects(self) -> None:
        data = self._request_json(
            "GET",
            "/api/vn/projects",
            context="Project discovery",
            timeout=10.0,
        )
        if data is None:
            return
        projects = self._normalize_projects(data)
        self._projects = projects
        self.projects.blockSignals(True)
        self.projects.clear()
        for project in projects:
            label = project["title"]
            path = project.get("path") or ""
            display = f"{label} ({path})" if path else label
            self.projects.addItem(display, project)
        self.projects.blockSignals(False)
        if projects:
            self.projects.setCurrentIndex(0)
            self._refresh_scenes()
            self._set_status(f"Loaded {len(projects)} project(s).", success=True)
        else:
            self.scenes.clear()
            self._set_status("No VN projects found.")

    def _refresh_scenes(self) -> None:
        project = self._current_project()
        if not project:
            self.scenes.clear()
            self._set_status("Select a project to load scenes.")
            return
        params = {"projectId": project["id"]}
        data = self._request_json(
            "GET",
            "/api/vn/scenes",
            params=params,
            context=f"Scene listing ({project['id']})",
            timeout=10.0,
        )
        if data is None:
            return
        scenes = self._normalize_scenes(data)
        self._scene_cache.clear()
        self.scenes.clear()
        for scene in scenes:
            label = f"{scene['id']} — {scene['title']}"
            item = QListWidgetItem(label, self.scenes)
            item.setData(Qt.UserRole, scene)
            self.scenes.addItem(item)
            self._scene_cache[scene["id"]] = scene.get("meta", scene)
        if scenes:
            self.scenes.setCurrentRow(0)
            self._set_status(
                f"Loaded {len(scenes)} scene(s) for {project['title']}.", success=True
            )
        else:
            self._set_status("No scenes available for this project.")

    def _build_from_imports(self) -> None:
        project = self._current_project()
        if not project or self._build_inflight:
            return
        payload = {"projectId": project["id"], "sources": []}
        self._build_inflight = True
        self.btn_build.setEnabled(False)
        data = self._request_json(
            "POST",
            "/api/vn/build",
            payload=payload,
            context=f"Build ({project['id']})",
            timeout=30.0,
        )
        self._build_inflight = False
        self.btn_build.setEnabled(True)
        if data is None:
            return
        status = data.get("status") if isinstance(data, dict) else None
        message = status or "Build completed."
        self._set_status(message, success=True)
        self._refresh_scenes()

    def _rebuild(self) -> None:
        project = self._current_project()
        if not project:
            self._set_status("Select a project before rebuilding.")
            return
        payload = {"projectId": project["id"], "rebuild": True}
        data = self._request_json(
            "POST",
            "/api/vn/build",
            payload=payload,
            context=f"Rebuild ({project['id']})",
            timeout=30.0,
        )
        if data is None:
            return
        message = data.get("status") if isinstance(data, dict) else "Rebuild completed."
        self._set_status(message, success=True)
        self._refresh_scenes()

    def _fetch_scene_payload(
        self, project: MappingLike, scene_id: str
    ) -> Optional[MappingLike]:
        params = {"projectId": project["id"]}
        data = self._request_json(
            "GET",
            f"/api/vn/preview/{scene_id}",
            params=params,
            context=f"Scene preview ({scene_id})",
            timeout=8.0,
        )
        if data is None:
            cached = self._scene_cache.get(scene_id)
            if isinstance(cached, dict):
                return cached
            return None
        if isinstance(data, dict) and "scene" in data:
            scene = data.get("scene")
            return scene if isinstance(scene, dict) else data
        if isinstance(data, dict):
            return data
        return None

    def _play_scene(self) -> None:
        project = self._current_project()
        if not project:
            self._set_status("Select a project first.")
            return
        scene = self._current_scene()
        if not scene:
            self._set_status("Select a scene to preview.")
            return
        scene_id = scene["id"]
        payload = self._fetch_scene_payload(project, scene_id)
        if payload is None:
            self._set_status("Scene payload unavailable.")
            return
        dialog = _ScenePlayerDialog(payload, self)
        dialog.exec()

    def _open_in_viewer(self) -> None:
        project = self._current_project()
        scene = self._current_scene()
        if not project or not scene:
            self._set_status("Select a project and scene.")
            return
        scene_id = scene["id"]
        payload = self._fetch_scene_payload(project, scene_id) or {}
        digest = _scene_digest(payload)
        base_snapshot = {
            "timeline_id": payload.get("timeline_id")
            or scene.get("timeline_id")
            or "ad-hoc",
            "seed": 0,
            "pov": payload.get("pov") or payload.get("perspective") or "auto",
            "digest": digest,
            "scenes": [
                {
                    "order": 0,
                    "scene_id": scene_id,
                    "title": payload.get("title") or scene.get("title") or scene_id,
                    "preview_text": _preview_text(payload),
                }
            ],
            "thumbnails": [],
        }
        project_path = project.get("path") or ""
        try:
            player = MiniVNPlayer(
                project_id=project["id"],
                project_path=Path(project_path) if project_path else None,
                timeline_id=payload.get("timeline_id"),
            )
            snapshot, thumbnails = player.generate_snapshot()
            filtered = [
                entry
                for entry in snapshot.get("scenes", [])
                if isinstance(entry, dict) and entry.get("scene_id") == scene_id
            ]
            if filtered:
                base_snapshot["scenes"] = filtered
            thumb_catalog: List[Dict[str, Any]] = []
            for record in thumbnails.values():
                if getattr(record, "scene_id", None) == scene_id:
                    thumb_catalog.append(
                        {
                            "scene_id": record.scene_id,
                            "key": record.key,
                            "digest": record.digest,
                            "width": record.width,
                            "height": record.height,
                        }
                    )
            if thumb_catalog:
                base_snapshot["thumbnails"] = thumb_catalog
        except Exception as exc:
            LOGGER.debug("Mini-VN snapshot fallback failed: %s", exc)

        viewer = MiniVNFallbackWidget()
        viewer.update_snapshot(base_snapshot, self.bridge.base)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Mini-VN preview — {scene_id}")
        dialog.resize(640, 520)
        container = QVBoxLayout(dialog)
        container.setContentsMargins(12, 12, 12, 12)
        container.addWidget(viewer)
        close_btn = QPushButton("Close", dialog)
        close_btn.clicked.connect(dialog.accept)
        container.addWidget(close_btn, alignment=Qt.AlignRight)
        dialog.exec()

    def _open_in_renpy(self) -> None:
        project = self._current_project()
        if not project:
            self._set_status("Select a project first.")
            return
        project_path = project.get("path") or ""
        if not project_path:
            QMessageBox.information(
                self,
                "Open in Ren'Py",
                "Selected project did not report a project_path; rebuild first or update /api/vn/projects.",
            )
        payload: Dict[str, Any] = {"project_id": project["id"]}
        if project_path:
            payload["project_path"] = project_path
        data = self._request_json(
            "POST",
            "/api/viewer/start",
            payload=payload,
            context="Ren'Py viewer launch",
            timeout=10.0,
        )
        if data is None:
            return
        runtime_mode = data.get("runtime_mode")
        message = "Viewer launched."
        if runtime_mode:
            message = f"Viewer launched ({runtime_mode})."
        self._set_status(message, success=True)
