import json
import asyncio
import sys
import time
import types
import zipfile
from pathlib import Path

import pytest


def _install_pyside_stubs() -> None:
    if "PySide6" in sys.modules:
        return
    pyside = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")

    class _DummyAction:  # minimal placeholder for QAction usage during imports
        pass

    qtgui.QAction = _DummyAction
    pyside.QtGui = qtgui
    sys.modules["PySide6"] = pyside
    sys.modules["PySide6.QtGui"] = qtgui


_install_pyside_stubs()

from comfyvn.server.core.vn_importer import import_vn_package
from comfyvn.server.modules import vn_import_api


@pytest.fixture(autouse=True)
def _stub_reindex(monkeypatch):
    import comfyvn.server.core.vn_importer as importer

    class _IndexerStub:
        def reindex(self):
            return {"ok": True}

    monkeypatch.setattr(importer, "indexer", _IndexerStub(), raising=False)


@pytest.fixture(autouse=True)
def _stub_task_registry(monkeypatch):
    from pathlib import Path

    class _Task:
        def __init__(self, task_id: str, kind: str, meta: dict):
            self.id = task_id
            self.kind = kind
            self.status = "queued"
            self.progress = 0.0
            self.message = ""
            self.meta = meta

    class _Registry:
        def __init__(self):
            self._tasks: dict[str, _Task] = {}
            self._counter = 0

        def register(self, kind: str, payload: dict, *, message: str = "", meta: dict | None = None):
            self._counter += 1
            task_id = f"job-{self._counter}"
            task_meta = dict(meta or {})
            task_meta.setdefault("payload", payload)
            task = _Task(task_id, kind, task_meta)
            task.message = message
            self._tasks[task_id] = task
            return task_id

        def update(self, task_id: str, **updates):
            task = self._tasks.get(task_id)
            if not task:
                return
            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)

        def get(self, task_id: str):
            return self._tasks.get(task_id)

        def list(self):
            return list(self._tasks.values())

    registry = _Registry()
    monkeypatch.setattr("comfyvn.server.modules.vn_import_api.task_registry", registry, raising=False)
    monkeypatch.setattr("comfyvn.core.task_registry.task_registry", registry, raising=False)

    class _Tool:
        def __init__(self, name: str, path: Path, extensions: list[str], notes: str, warning: str):
            self.name = name
            self.path = path
            self.extensions = extensions
            self.notes = notes
            self.warning = warning
            self.handler = None

    class _ExtractorStub:
        def __init__(self):
            self._tools: dict[str, _Tool] = {}

        def list_tools(self):
            return list(self._tools.values())

        def register(self, name: str, path: str, *, extensions=None, notes: str = "", warning: str = ""):
            tool = _Tool(name, Path(path), [ext.lower() for ext in (extensions or [])], notes, warning)
            self._tools[name] = tool
            return tool

        def unregister(self, name: str) -> bool:
            return bool(self._tools.pop(name, None))

        def get(self, name: str):
            return self._tools.get(name)

        def resolve_for_extension(self, suffix: str):
            suffix = suffix.lower()
            for tool in self._tools.values():
                if suffix in tool.extensions:
                    return tool
            return None

        def set_handler(self, name: str, handler):
            if name in self._tools:
                self._tools[name].handler = handler

        def invoke(self, name: str, source: Path, *, output_dir: Path):
            tool = self._tools.get(name)
            if not tool:
                raise ValueError("tool not registered")
            if tool.handler:
                tool.handler(source, output_dir)
            else:
                # default: copy zip contents if present
                if zipfile.is_zipfile(source):
                    with zipfile.ZipFile(source, "r") as archive:
                        archive.extractall(output_dir)
                else:
                    raise RuntimeError("no handler defined for extractor stub")
            return output_dir

    extractor = _ExtractorStub()
    monkeypatch.setattr("comfyvn.server.core.external_extractors.extractor_manager", extractor, raising=False)
    monkeypatch.setattr("comfyvn.server.modules.vn_import_api.extractor_manager", extractor, raising=False)
    monkeypatch.setattr("comfyvn.server.core.vn_importer.extractor_manager", extractor, raising=False)


def _build_sample_package(tmp_path: Path) -> Path:
    manifest = {
        "id": "demo-project",
        "title": "Demo Project",
        "licenses": [{"name": "CC-BY", "scope": "backgrounds"}],
    }
    scene = {"scene_id": "demo_scene", "title": "Demo", "lines": []}
    character = {"character_id": "hero", "name": "Hero"}
    timeline = {"timeline_id": "main", "scenes": ["demo_scene"]}

    package_path = tmp_path / "demo.cvnpack"
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("scenes/demo_scene.json", json.dumps(scene))
        archive.writestr("characters/hero.json", json.dumps(character))
        archive.writestr("timelines/main.json", json.dumps(timeline))
        archive.writestr("assets/backgrounds/bg1.png", b"fake-png")
        archive.writestr("licenses/NOTICE.txt", "Licensed assets")
    return package_path


def _build_renpy_package(tmp_path: Path) -> Path:
    manifest = {
        "id": "renpy-demo",
        "title": "RenPy Demo",
        "engine": "RenPy",
    }
    package_path = tmp_path / "renpy.cvnpack"
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("game/script.rpy", "label start:\n    return")
        archive.writestr("scenes/start.json", json.dumps({"scene_id": "start", "lines": []}))
    return package_path


def test_import_vn_package(tmp_path: Path):
    package_path = _build_sample_package(tmp_path)
    data_root = tmp_path / "data_root"

    summary = import_vn_package(package_path, data_root=data_root)

    assert summary["scenes"] == ["demo_scene"]
    assert summary["characters"] == ["hero"]
    assert summary["timelines"] == ["main"]
    assert summary["assets"] == ["backgrounds/bg1.png"]
    assert summary["manifest"]["id"] == "demo-project"
    assert summary["licenses"] == [{"name": "CC-BY", "scope": "backgrounds"}]
    assert summary["adapter"] == "generic"
    assert summary["summary_path"]

    assert (data_root / "scenes" / "demo_scene.json").exists()
    assert (data_root / "characters" / "hero.json").exists()
    assert (data_root / "timelines" / "main.json").exists()
    assert (data_root / "assets" / "backgrounds" / "bg1.png").exists()
    assert (data_root / "imports" / "vn").exists()
    assert Path(summary["summary_path"]).exists()


def test_import_vn_adapter_detection(tmp_path: Path):
    package_path = _build_renpy_package(tmp_path)
    data_root = tmp_path / "renpy_data"

    summary = import_vn_package(package_path, data_root=data_root)

    assert summary["adapter"] == "renpy"
    assert (data_root / "scenes" / "start.json").exists()


def test_import_with_external_tool(tmp_path: Path):
    from comfyvn.server.core import external_extractors as ext_mgr

    tool_path = tmp_path / "arc_unpacker_stub"
    tool_path.write_text("#!/bin/sh\n", encoding="utf-8")

    tool = ext_mgr.extractor_manager.register(
        "arc_unpacker",
        str(tool_path),
        extensions=[".arc"],
        warning="Check local laws before extracting VN archives.",
    )

    def _handler(source: Path, output_dir: Path):
        with zipfile.ZipFile(source, "r") as archive:
            archive.extractall(output_dir)

    ext_mgr.extractor_manager.set_handler(tool.name, _handler)

    arc_path = tmp_path / "demo.arc"
    with zipfile.ZipFile(arc_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"id": "ext-demo"}))
        archive.writestr("scenes/demo_scene.json", json.dumps({"scene_id": "demo_scene", "lines": []}))

    data_root = tmp_path / "ext_data"

    summary = import_vn_package(arc_path, data_root=data_root, tool="arc_unpacker")

    assert summary["extractor"] == "arc_unpacker"
    assert summary["adapter"] == "generic"
    assert (data_root / "scenes" / "demo_scene.json").exists()


def test_import_vn_api_blocking(tmp_path: Path, monkeypatch):
    package_path = _build_sample_package(tmp_path)
    data_root = tmp_path / "api_data"
    monkeypatch.setenv("COMFYVN_DATA_ROOT", str(data_root))

    payload = asyncio.run(vn_import_api.import_vn({"path": str(package_path), "blocking": True}))
    assert payload["ok"] is True
    summary = payload["import"]
    assert summary["scenes"] == ["demo_scene"]
    assert summary["characters"] == ["hero"]
    assert summary["adapter"] == "generic"
    assert Path(summary["summary_path"]).exists()
    assert (data_root / "scenes" / "demo_scene.json").exists()

    status_payload = asyncio.run(vn_import_api.import_status(payload["job"]["id"], True))
    assert status_payload["job"]["status"] == "done"
    assert status_payload["summary"]["scenes"] == ["demo_scene"]
    assert status_payload["summary"]["adapter"] == "generic"


def test_import_vn_api_job(tmp_path: Path, monkeypatch):
    package_path = _build_sample_package(tmp_path)
    data_root = tmp_path / "async_data"
    monkeypatch.setenv("COMFYVN_DATA_ROOT", str(data_root))

    payload = asyncio.run(vn_import_api.import_vn({"path": str(package_path)}))
    assert payload["ok"] is True
    job_id = payload["job"]["id"]

    summary = None
    for _ in range(40):
        status_payload = asyncio.run(vn_import_api.import_status(job_id, True))
        job_payload = status_payload["job"]
        if job_payload["status"] == "done":
            summary = (job_payload.get("meta") or {}).get("result")
            break
        if job_payload["status"] == "error":
            error_message = job_payload.get("message") or job_payload.get("meta", {}).get("error")
            pytest.fail(f"job errored: {error_message}")
        time.sleep(0.01)

    assert summary is not None
    assert summary["scenes"] == ["demo_scene"]
    assert summary["adapter"] in {"generic", "renpy"}
    assert (data_root / "scenes" / "demo_scene.json").exists()

    detail_payload = asyncio.run(vn_import_api.import_status(job_id, True))
    assert detail_payload["job"]["status"] in {"done", "error"}
    if detail_payload["summary"]:
        assert detail_payload["summary"]["scenes"] == ["demo_scene"]
        assert "adapter" in detail_payload["summary"]


def test_import_history_endpoint(tmp_path: Path, monkeypatch):
    data_root = tmp_path / "history"
    monkeypatch.setenv("COMFYVN_DATA_ROOT", str(data_root))

    pkg1 = _build_sample_package(tmp_path)
    pkg2 = _build_renpy_package(tmp_path)

    for pkg in (pkg1, pkg2):
        resp = asyncio.run(vn_import_api.import_vn({"path": str(pkg), "blocking": True}))
        assert resp["ok"] is True

    data = asyncio.run(vn_import_api.import_history(limit=5, _=True))
    assert data["ok"] is True
    imports = data["imports"]
    assert len(imports) >= 2
    adapters = {item.get("adapter") for item in imports}
    assert "renpy" in adapters
    assert "generic" in adapters

def test_tool_endpoints(tmp_path: Path, monkeypatch):
    data_root = tmp_path / "tools"
    monkeypatch.setenv("COMFYVN_DATA_ROOT", str(data_root))

    binary_path = tmp_path / "arc_unpacker"
    binary_path.write_text("#!/bin/sh\n", encoding="utf-8")

    resp = asyncio.run(
        vn_import_api.register_tool(
            {
                "name": "arc_unpacker",
                "path": str(binary_path),
                "extensions": [".arc"],
                "warning": "Check regional restrictions.",
            },
            True,
        )
    )
    assert resp["tool"]["name"] == "arc_unpacker"

    tools = asyncio.run(vn_import_api.list_tools(True))
    names = [tool["name"] for tool in tools["tools"]]
    assert "arc_unpacker" in names

    delete = asyncio.run(vn_import_api.remove_tool("arc_unpacker", True))
    assert delete["ok"] is True

    tools_after = asyncio.run(vn_import_api.list_tools(True))
    names_after = [tool["name"] for tool in tools_after["tools"]]
    assert "arc_unpacker" not in names_after


def test_tool_install(monkeypatch, tmp_path: Path):
    data_root = tmp_path / "tools_install"
    monkeypatch.setenv("COMFYVN_DATA_ROOT", str(data_root))

    from comfyvn.server.core import extractor_installer as installer
    from comfyvn.server.core import external_extractors as registry

    def fake_download(url: str, dest: Path):
        dest.write_text("binary", encoding="utf-8")

    registry.extractor_manager.register(
        "arc_unpacker",
        str(tmp_path / "existing"),
        extensions=[".arc"],
        notes="",
        warning="",
    )
    def fake_install(name: str, target_dir=None):
        fake_path = tmp_path / "fake" / "arc_unpacker.exe"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.write_text("binary", encoding="utf-8")
        meta = installer.KNOWN_EXTRACTORS[name]
        return {
            "name": name,
            "path": str(fake_path),
            "warning": meta.warning,
            "license": meta.license,
            "notes": meta.notes,
            "extensions": meta.extensions,
        }

    monkeypatch.setattr(installer, "install_extractor", fake_install, raising=False)
    monkeypatch.setattr(installer, "_download_to_file", fake_download, raising=False)

    result = asyncio.run(
        vn_import_api.install_tool({"name": "arc_unpacker", "accept_terms": True}, True)
    )
    assert result["ok"] is True
    assert result["tool"]["name"] == "arc_unpacker"


def test_tool_catalog_contains_known_entries():
    catalog = asyncio.run(vn_import_api.tool_catalog())
    assert catalog["ok"] is True
    tools = catalog["tools"]
    ids = {tool["id"] for tool in tools}
    assert len(tools) >= 20
    assert "arc_unpacker" in ids
    assert "lightvntools_github" in ids
