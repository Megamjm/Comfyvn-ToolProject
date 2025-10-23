from __future__ import annotations

from pathlib import Path

import comfyvn.scripts.install_manager as install_manager


class DummyClient:
    def get(self, *args, **kwargs):
        raise AssertionError("Network access not expected in tests.")

    def stream(self, *args, **kwargs):
        raise AssertionError("Network access not expected in tests.")


def make_context(
    tmp_path: Path, dry_run: bool = True
) -> install_manager.InstallContext:
    cache_dir = tmp_path / "cache"
    report_path = tmp_path / "install.log"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return install_manager.InstallContext(
        cache_dir=cache_dir,
        report_path=report_path,
        client=DummyClient(),
        dry_run=dry_run,
        repo_root=tmp_path,
    )


def test_handle_sillytavern_dry_run(tmp_path: Path, monkeypatch):
    ctx = make_context(tmp_path, dry_run=True)
    target = tmp_path / "SillyTavern" / "public" / "scripts" / "extensions"
    target.mkdir(parents=True, exist_ok=True)
    entry = install_manager.handle_sillytavern(ctx, str(target))
    assert entry.status == "ok"
    assert entry.details.get("mode") == "dry-run"


def test_handle_comfyui_dry_run_reports_missing(tmp_path: Path, monkeypatch):
    ctx = make_context(tmp_path, dry_run=True)
    base = tmp_path / "ComfyUI"
    (base / "custom_nodes").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        install_manager,
        "_gather_node_packs",
        lambda: [{"id": "demo", "repo": "owner/repo", "commit": "", "category": []}],
    )

    entry = install_manager.handle_comfyui(ctx, str(base))
    assert entry.status == "missing"
    packs = entry.details["packs"]
    assert packs and packs[0]["status"] == "missing"


def test_handle_models_marks_missing(tmp_path: Path):
    ctx = make_context(tmp_path, dry_run=True)
    entry = install_manager.handle_models(ctx, mode="auto")
    assert entry.status == "missing"
    assert entry.details["entries"], "model entries should be enumerated"
