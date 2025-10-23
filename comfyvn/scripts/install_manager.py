"""Install manager CLI for ComfyVN external integrations.

This utility orchestration covers three external dependencies:

* SillyTavern bridge extension sync
* Ren'Py SDK bootstrap
* ComfyUI custom nodes and model presence checks

It keeps an append-only install report under ``logs/install_report.log`` so the
Studio UI can surface historical runs. Downloads are cached beneath
``tools/cache`` with per-file SHA256 sidecars to guarantee repeatable reuse.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

import httpx

from comfyvn.importers.renpy_setup import ensure_renpy_sdk, get_renpy_executable
from comfyvn.modules.st_bridge import extension_sync as st_sync
from comfyvn.providers import load_nodeset_lock, load_providers_template

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_PATH = REPO_ROOT / "logs" / "install_report.log"
DEFAULT_CACHE_ROOT = REPO_ROOT / "tools" / "cache"
REN_PY_INSTALL_ROOT = REPO_ROOT / "tools" / "renpy"

GITHUB_REPO_API = "https://api.github.com/repos/{repo}"
GITHUB_COMMIT_API = "https://api.github.com/repos/{repo}/commits/{ref}"


@dataclass(slots=True)
class InstallEntry:
    task: str
    status: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "task": self.task,
            "status": self.status,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(slots=True)
class InstallContext:
    cache_dir: Path
    report_path: Path
    client: httpx.Client
    dry_run: bool = False
    repo_root: Path = REPO_ROOT
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    start_time: float = field(default_factory=time.time)

    def cache_subdir(self, name: str) -> Path:
        target = self.cache_dir / name
        target.mkdir(parents=True, exist_ok=True)
        return target


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m comfyvn.scripts.install_manager",
        description="Install or verify external integrations for ComfyVN.",
    )
    parser.add_argument(
        "--sillytavern",
        type=str,
        help="Path to SillyTavern root or extensions directory (defaults to SILLYTAVERN_PATH/public/scripts/extensions).",
    )
    parser.add_argument(
        "--renpy",
        type=str,
        default="auto",
        help="Existing Ren'Py SDK path or 'auto' (default) to download the latest stable release.",
    )
    parser.add_argument(
        "--comfyui",
        type=str,
        help="Path to the ComfyUI checkout to manage custom node packs (default: ~/ComfyUI if present).",
    )
    parser.add_argument(
        "--models",
        type=str,
        default="auto",
        choices=["auto", "skip"],
        help="Verify provider model placeholders ('auto') or skip (use --models skip).",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        help="Override download cache directory (default: tools/cache/).",
    )
    parser.add_argument(
        "--report",
        type=str,
        help="Override install report path (default: logs/install_report.log).",
    )
    parser.add_argument(
        "--force-renpy",
        action="store_true",
        help="Force re-download of the Ren'Py SDK even if a valid install already exists.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Run in verification mode without writing to disk.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )
    return parser.parse_args(argv)


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(message)s")


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def cached_download(
    client: httpx.Client, url: str, dest: Path
) -> Tuple[Path, str, bool]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    checksum_path = dest.with_suffix(dest.suffix + ".sha256")
    if dest.exists():
        checksum = compute_sha256(dest)
        if checksum_path.exists():
            recorded = checksum_path.read_text(encoding="utf-8").strip()
            if recorded != checksum:
                LOGGER.warning(
                    "Cached download checksum mismatch for %s (expected %s, got %s); redownloading",
                    dest.name,
                    recorded,
                    checksum,
                )
                dest.unlink(missing_ok=True)
                checksum_path.unlink(missing_ok=True)
            else:
                LOGGER.info(
                    "Reusing cached download %s (sha256=%s)", dest.name, checksum
                )
                return dest, checksum, False
        else:
            checksum_path.write_text(checksum, encoding="utf-8")
            LOGGER.info(
                "Recorded checksum for cached download %s (sha256=%s)",
                dest.name,
                checksum,
            )
            return dest, checksum, False

    LOGGER.info("Downloading %s", url)
    digest = hashlib.sha256()
    tmp_path = dest.with_suffix(dest.suffix + ".part")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with client.stream("GET", url, timeout=120.0) as resp:
            resp.raise_for_status()
            with tmp_path.open("wb") as handle:
                for chunk in resp.iter_bytes():
                    if not chunk:
                        continue
                    digest.update(chunk)
                    handle.write(chunk)
    except (
        httpx.HTTPError
    ) as exc:  # pragma: no cover - network failures are environment-specific
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc

    checksum = digest.hexdigest()
    tmp_path.rename(dest)
    checksum_path.write_text(checksum, encoding="utf-8")
    LOGGER.info("Saved %s (sha256=%s)", dest.name, checksum)
    return dest, checksum, True


def resolve_sillytavern_base(arg: Optional[str]) -> Tuple[Optional[Path], str]:
    if arg:
        return Path(arg).expanduser(), "cli"

    env_dest = os.getenv(st_sync.ENV_DEST_DIR)
    if env_dest:
        return Path(env_dest).expanduser(), f"env:{st_sync.ENV_DEST_DIR}"

    env_root = os.getenv(st_sync.ENV_ST_ROOT)
    if env_root:
        path = Path(env_root).expanduser() / "public" / "scripts" / "extensions"
        return path, f"env:{st_sync.ENV_ST_ROOT}"

    default_root = Path.home() / "SillyTavern"
    if default_root.exists():
        return default_root / "public" / "scripts" / "extensions", "default-home"

    return None, "missing"


def handle_sillytavern(ctx: InstallContext, arg: Optional[str]) -> InstallEntry:
    base, source_hint = resolve_sillytavern_base(arg)
    if base is None:
        message = (
            "SillyTavern install not detected; set --sillytavern PATH or export "
            "SILLYTAVERN_PATH before re-running."
        )
        return InstallEntry(
            task="sillytavern",
            status="skipped",
            message=message,
            details={"reason": "not-detected"},
        )

    try:
        source_dir = st_sync._resolve_source(None, st_sync.DEFAULT_EXTENSION_NAME)
    except FileNotFoundError as exc:
        return InstallEntry(
            task="sillytavern",
            status="error",
            message=f"Bundled SillyTavern extension missing: {exc}",
            details={"expected": str(source_dir) if "source_dir" in locals() else ""},
        )

    destination = st_sync._resolve_destination(base, st_sync.DEFAULT_EXTENSION_NAME)
    st_root = (
        destination.parents[3] if len(destination.parents) >= 4 else destination.parent
    )
    if not st_root.exists():
        hint = "Pass --sillytavern /path/to/SillyTavern (containing public/scripts/extensions)."
        return InstallEntry(
            task="sillytavern",
            status="error",
            message=f"SillyTavern root not found at {st_root}",
            details={
                "destination": str(destination),
                "hint": hint,
                "source": source_hint,
            },
        )

    if ctx.dry_run:
        summary = st_sync.copy_extension_tree(source_dir, destination, dry_run=True)
        message = (
            f"Dry-run: {summary.files_processed} files would sync to {destination} "
            f"(created {summary.created}, updated {summary.updated})."
        )
        details = summary.as_dict()
        details.update(
            {"origin": str(source_dir), "mode": "dry-run", "source_hint": source_hint}
        )
        return InstallEntry(
            task="sillytavern", status="ok", message=message, details=details
        )

    summary = st_sync.copy_extension_tree(source_dir, destination, dry_run=False)
    message = (
        f"SillyTavern extension synced to {destination} "
        f"(created {summary.created}, updated {summary.updated}, skipped {summary.skipped})."
    )
    details = summary.as_dict()
    details.update({"origin": str(source_dir), "source_hint": source_hint})
    return InstallEntry(
        task="sillytavern", status="ok", message=message, details=details
    )


def _detect_existing_renpy(base: Path) -> Optional[Path]:
    if not base.exists():
        return None
    candidates = sorted(
        (path for path in base.glob("renpy-*-sdk") if path.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    for candidate in candidates:
        if get_renpy_executable(candidate):
            return candidate
    return None


def handle_renpy(
    ctx: InstallContext, arg: Optional[str], *, force: bool
) -> InstallEntry:
    value = (arg or "auto").strip()
    if value.lower() != "auto":
        install_path = Path(value).expanduser()
        executable = get_renpy_executable(install_path)
        if executable:
            metadata = read_json(install_path / "comfyvn.install.json")
            version = metadata.get("version") or "unknown"
            message = (
                f"Using existing Ren'Py SDK at {install_path} (version {version})."
            )
            details = {
                "path": str(install_path),
                "executable": str(executable),
                "version": version,
                "source": "cli",
            }
            return InstallEntry(
                task="renpy", status="ok", message=message, details=details
            )
        status = "missing" if ctx.dry_run else "error"
        message = (
            f"{install_path} does not look like a Ren'Py SDK; ensure the path contains "
            "renpy.sh or renpy.exe."
        )
        return InstallEntry(
            task="renpy",
            status=status,
            message=message,
            details={"path": str(install_path)},
        )

    existing = _detect_existing_renpy(REN_PY_INSTALL_ROOT)
    if ctx.dry_run:
        if existing:
            metadata = read_json(existing / "comfyvn.install.json")
            version = metadata.get("version") or "unknown"
            message = f"Ren'Py SDK detected at {existing} (version {version})."
            details = {"path": str(existing), "version": version, "mode": "dry-run"}
            return InstallEntry(
                task="renpy", status="ok", message=message, details=details
            )
        message = (
            f"No Ren'Py SDK found under {REN_PY_INSTALL_ROOT}; run without --verify-only "
            "to bootstrap automatically."
        )
        return InstallEntry(
            task="renpy",
            status="missing",
            message=message,
            details={"path": str(REN_PY_INSTALL_ROOT)},
        )

    try:
        install_path = ensure_renpy_sdk(
            install_root=REN_PY_INSTALL_ROOT,
            client=ctx.client,
            force=force,
            cache_dir=ctx.cache_subdir("renpy"),
        )
    except Exception as exc:
        return InstallEntry(
            task="renpy",
            status="error",
            message=f"Ren'Py installation failed: {exc}",
            details={"path": str(REN_PY_INSTALL_ROOT)},
        )

    metadata = read_json(install_path / "comfyvn.install.json")
    version = metadata.get("version") or "unknown"
    executable = get_renpy_executable(install_path)
    details = {
        "path": str(install_path),
        "version": version,
        "executable": str(executable) if executable else None,
        "archive": metadata.get("archive"),
    }
    message = f"Ren'Py SDK ready at {install_path} (version {version})."
    return InstallEntry(task="renpy", status="ok", message=message, details=details)


def resolve_comfyui_base(arg: Optional[str]) -> Optional[Path]:
    if arg:
        return Path(arg).expanduser()
    env_root = os.getenv("COMFYUI_ROOT") or os.getenv("COMFYVN_COMFYUI_ROOT")
    if env_root:
        return Path(env_root).expanduser()
    default_root = Path.home() / "ComfyUI"
    if default_root.exists():
        return default_root
    return None


def _gather_node_packs() -> Iterable[Dict[str, Any]]:
    catalog = load_providers_template()
    lock_entries = {pack.repo: pack for pack in load_nodeset_lock()}
    for pack_id, info in sorted(catalog.node_packs.items()):
        repo = info.get("repo")
        if not repo:
            continue
        lock = lock_entries.get(repo)
        commit = ""
        if lock and lock.commit and not lock.commit.startswith("000"):
            commit = lock.commit
        yield {
            "id": pack_id,
            "repo": repo,
            "commit": commit,
            "category": list(info.get("category") or ()),
        }


def resolve_remote_commit(client: httpx.Client, repo: str) -> Tuple[str, Optional[str]]:
    default_branch = "main"
    try:
        resp = client.get(GITHUB_REPO_API.format(repo=repo), timeout=30.0)
        if resp.status_code < 400:
            data = resp.json()
            default_branch = data.get("default_branch") or default_branch
    except Exception as exc:  # pragma: no cover - network variability
        LOGGER.debug("Failed to read repo metadata for %s: %s", repo, exc)

    try:
        resp = client.get(
            GITHUB_COMMIT_API.format(repo=repo, ref=default_branch), timeout=30.0
        )
        if resp.status_code < 400:
            data = resp.json()
            sha = data.get("sha")
            if sha:
                return sha, sha
    except Exception as exc:  # pragma: no cover - network variability
        LOGGER.warning("Failed to resolve commit for %s: %s", repo, exc)

    return default_branch, None


def extract_zip(archive_path: Path, destination: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="comfyvn-nodes-") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(tmp_path)
        candidates = [path for path in tmp_path.iterdir() if path.is_dir()]
        if not candidates:
            raise RuntimeError(
                f"Archive {archive_path.name} did not contain a directory root."
            )
        source_dir = candidates[0]
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_dir), str(destination))
    return destination


def ensure_node_pack(
    ctx: InstallContext, custom_nodes_dir: Path, pack: Dict[str, Any]
) -> Dict[str, Any]:
    repo = pack["repo"]
    slug = repo.split("/")[-1]
    destination = custom_nodes_dir / slug
    meta_path = destination / "comfyvn.install.json"
    existing_meta = read_json(meta_path)

    commit_hint = pack.get("commit") or ""
    if commit_hint and not commit_hint.startswith("000"):
        download_ref = commit_hint
        resolved_commit: Optional[str] = commit_hint
    elif ctx.dry_run:
        download_ref = "latest"
        resolved_commit = None
    else:
        download_ref, resolved_commit = resolve_remote_commit(ctx.client, repo)

    current_commit = existing_meta.get("commit")
    if destination.exists() and current_commit == resolved_commit and not ctx.dry_run:
        LOGGER.debug("ComfyUI node pack %s already at %s", repo, resolved_commit)
        checksum = existing_meta.get("sha256")
        return {
            "id": pack["id"],
            "repo": repo,
            "path": str(destination),
            "status": "ok",
            "commit": resolved_commit,
            "downloaded": False,
            "checksum": checksum,
        }

    if ctx.dry_run:
        status = "ok" if destination.exists() else "missing"
        message = (
            f"Dry-run: would install {repo} at {destination} (ref {download_ref})."
        )
        return {
            "id": pack["id"],
            "repo": repo,
            "path": str(destination),
            "status": status,
            "commit": resolved_commit or download_ref,
            "downloaded": False,
            "message": message,
        }

    cache_dir = ctx.cache_subdir("comfyui")
    archive_name = f"{repo.replace('/', '_')}-{download_ref}.zip"
    archive_path = cache_dir / archive_name

    try:
        archive_path, checksum, downloaded = cached_download(
            ctx.client,
            f"https://codeload.github.com/{repo}/zip/{download_ref}",
            archive_path,
        )
        extract_zip(archive_path, destination)
    except Exception as exc:
        LOGGER.error("Failed to install ComfyUI node pack %s: %s", repo, exc)
        return {
            "id": pack["id"],
            "repo": repo,
            "path": str(destination),
            "status": "error",
            "commit": resolved_commit or download_ref,
            "message": str(exc),
            "hint": (
                "Verify network connectivity or install manually: "
                f"https://github.com/{repo}"
            ),
        }

    metadata = {
        "repo": repo,
        "commit": resolved_commit or download_ref,
        "download_ref": download_ref,
        "categories": pack.get("category") or [],
        "sha256": checksum,
        "archive": archive_path.name,
        "installed": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    write_json(meta_path, metadata)

    file_count = sum(1 for path in destination.rglob("*") if path.is_file())
    return {
        "id": pack["id"],
        "repo": repo,
        "path": str(destination),
        "status": "ok",
        "commit": metadata["commit"],
        "downloaded": True,
        "checksum": checksum,
        "files": file_count,
    }


def handle_comfyui(ctx: InstallContext, arg: Optional[str]) -> InstallEntry:
    base = resolve_comfyui_base(arg)
    if base is None:
        message = "ComfyUI path not detected; set --comfyui /path/to/ComfyUI to manage node packs."
        return InstallEntry(
            task="comfyui",
            status="skipped",
            message=message,
            details={"reason": "not-detected"},
        )

    base = base.expanduser()
    if not base.exists():
        return InstallEntry(
            task="comfyui",
            status="error",
            message=f"ComfyUI path {base} does not exist; install ComfyUI first.",
            details={"path": str(base)},
        )

    custom_nodes_dir = base / "custom_nodes"
    custom_nodes_dir.mkdir(parents=True, exist_ok=True)

    packs = list(_gather_node_packs())
    if not packs:
        return InstallEntry(
            task="comfyui",
            status="skipped",
            message="No ComfyUI node packs defined in providers.json.",
            details={"path": str(custom_nodes_dir)},
        )

    results = [ensure_node_pack(ctx, custom_nodes_dir, pack) for pack in packs]
    errors = sum(1 for result in results if result.get("status") == "error")
    pending = sum(1 for result in results if result.get("status") == "missing")
    message = (
        f"Processed {len(results)} ComfyUI packs "
        f"({errors} errors, {pending} pending)."
    )
    if errors:
        status = "error"
    elif pending:
        status = "missing"
    else:
        status = "ok"
    return InstallEntry(
        task="comfyui",
        status=status,
        message=message,
        details={
            "base": str(base),
            "custom_nodes": str(custom_nodes_dir),
            "packs": results,
        },
    )


def handle_models(ctx: InstallContext, mode: str) -> InstallEntry:
    if mode == "skip":
        return InstallEntry(
            task="models",
            status="skipped",
            message="Model verification skipped (--models skip).",
        )

    catalog = load_providers_template()
    entries = []
    missing = 0
    for model_id, info in sorted(catalog.models.items()):
        rel_path = info.get("path") or ""
        model_path = Path(rel_path)
        if not model_path.is_absolute():
            model_path = ctx.repo_root / model_path
        exists = model_path.exists()
        entry: Dict[str, Any] = {
            "id": model_id,
            "path": str(model_path),
            "exists": exists,
        }
        hint = info.get("hint")
        if hint:
            entry["hint"] = hint
        if exists and model_path.is_file():
            entry["sha256"] = compute_sha256(model_path)
        if not exists:
            missing += 1
        entries.append(entry)

    if missing:
        message = f"{missing} model(s) missing; download assets manually (see hints)."
        status = "missing"
    else:
        message = "All provider model entries present."
        status = "ok"
    return InstallEntry(
        task="models",
        status=status,
        message=message,
        details={"entries": entries},
    )


def write_report(ctx: InstallContext, entries: Sequence[InstallEntry]) -> None:
    record = {
        "run_id": ctx.run_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "elapsed_seconds": round(time.time() - ctx.start_time, 2),
        "dry_run": ctx.dry_run,
        "entries": [entry.as_dict() for entry in entries],
    }
    ctx.report_path.parent.mkdir(parents=True, exist_ok=True)
    with ctx.report_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
        handle.write("\n")


def print_summary(entries: Sequence[InstallEntry]) -> None:
    for entry in entries:
        print(f"[{entry.status.upper():>7}] {entry.task}: {entry.message}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    cache_dir = (
        Path(args.cache_dir).expanduser().resolve()
        if args.cache_dir
        else DEFAULT_CACHE_ROOT
    )
    report_path = (
        Path(args.report).expanduser().resolve() if args.report else DEFAULT_REPORT_PATH
    )
    cache_dir.mkdir(parents=True, exist_ok=True)

    client_headers = {"User-Agent": "ComfyVN-Installer/1.0"}
    timeout = httpx.Timeout(120.0, connect=15.0, read=120.0, write=120.0, pool=None)

    entries: list[InstallEntry] = []
    with httpx.Client(
        follow_redirects=True, timeout=timeout, headers=client_headers
    ) as client:
        ctx = InstallContext(
            cache_dir=cache_dir,
            report_path=report_path,
            client=client,
            dry_run=args.verify_only,
        )

        tasks = [
            ("sillytavern", lambda: handle_sillytavern(ctx, args.sillytavern)),
            ("renpy", lambda: handle_renpy(ctx, args.renpy, force=args.force_renpy)),
            ("comfyui", lambda: handle_comfyui(ctx, args.comfyui)),
            ("models", lambda: handle_models(ctx, args.models)),
        ]

        for name, func in tasks:
            try:
                entries.append(func())
            except Exception as exc:  # pragma: no cover - defensive catch
                LOGGER.exception("Unhandled error during %s task", name)
                entries.append(
                    InstallEntry(
                        task=name,
                        status="error",
                        message=str(exc),
                    )
                )

        if not args.verify_only:
            write_report(ctx, entries)

    print_summary(entries)
    return 0 if all(entry.status != "error" for entry in entries) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
