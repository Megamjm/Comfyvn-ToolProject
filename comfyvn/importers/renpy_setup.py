from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Optional

import httpx

LOGGER = logging.getLogger(__name__)

REN_PY_BASE_URL = "https://www.renpy.org/dl/"
REN_PY_DEFAULT_VERSION = "8.2.1"
REN_PY_ENV_ROOT = "COMFYVN_RENPY_ROOT"
REN_PY_INSTALL_ROOT = Path("tools/renpy")
_TIMEOUT = 90.0
_VERSION_PATTERN = re.compile(r'href="(\d+(?:\.\d+)*)/')


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(piece) for piece in re.findall(r"\d+", version))


def _parse_versions(html: str) -> list[str]:
    versions = {match.group(1) for match in _VERSION_PATTERN.finditer(html)}
    sorted_versions = sorted(versions, key=_version_key)
    return sorted_versions


def discover_latest_version(client: httpx.Client) -> str:
    try:
        response = client.get(REN_PY_BASE_URL, timeout=_TIMEOUT)
    except Exception as exc:
        LOGGER.warning(
            "Failed to fetch Ren'Py release list (%s); falling back to %s",
            exc,
            REN_PY_DEFAULT_VERSION,
        )
        return REN_PY_DEFAULT_VERSION

    if response.status_code >= 400:
        LOGGER.warning(
            "Ren'Py release index returned HTTP %s; falling back to %s",
            response.status_code,
            REN_PY_DEFAULT_VERSION,
        )
        return REN_PY_DEFAULT_VERSION

    versions = _parse_versions(response.text or "")
    if not versions:
        LOGGER.warning(
            "Ren'Py release index yielded no versions; falling back to %s",
            REN_PY_DEFAULT_VERSION,
        )
        return REN_PY_DEFAULT_VERSION

    return versions[-1]


def _candidate_archives(version: str) -> Iterable[str]:
    yield f"renpy-{version}-sdk.zip"
    yield f"renpy-{version}-sdk.tar.bz2"


def _download_archive(version: str, client: httpx.Client, *, tmp_dir: Path) -> Path:
    errors: list[str] = []
    for filename in _candidate_archives(version):
        url = f"{REN_PY_BASE_URL}{version}/{filename}"
        try:
            with client.stream("GET", url, timeout=_TIMEOUT) as resp:
                status = getattr(resp, "status_code", 0)
                if status == 404:
                    continue
                if status and status >= 400:
                    errors.append(f"{filename}: HTTP {status}")
                    continue
                archive_path = tmp_dir / filename
                with archive_path.open("wb") as fh:
                    for chunk in resp.iter_bytes():
                        if chunk:
                            fh.write(chunk)
                LOGGER.info("Downloaded Ren'Py archive %s", filename)
                return archive_path
        except Exception as exc:
            LOGGER.warning("Failed to download %s (%s)", filename, exc)
            errors.append(f"{filename}: {exc}")
            continue

    if errors:
        raise RuntimeError(
            f"Unable to download Ren'Py SDK {version}; attempts: {', '.join(errors)}"
        )
    raise RuntimeError(
        f"Unable to download Ren'Py SDK {version}; no candidate archives succeeded."
    )


def _locate_install_root(path: Path) -> Path:
    binaries = ["renpy.sh", "renpy.exe", "Ren'Py Launcher.app"]
    for binary in binaries:
        for match in path.rglob(binary):
            if match.is_dir():
                return match
            return match.parent
    raise RuntimeError("Downloaded Ren'Py archive did not contain a launcher script.")


def _extract_archive(archive_path: Path, dest_dir: Path) -> Path:
    extract_root = archive_path.parent / "extracted"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    if archive_path.suffix == ".zip":
        import zipfile

        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(extract_root)
    elif archive_path.suffixes[-2:] == [".tar", ".bz2"]:
        import tarfile

        with tarfile.open(archive_path, "r:bz2") as tf:
            tf.extractall(extract_root)
    else:
        raise RuntimeError(f"Unsupported Ren'Py archive format: {archive_path.name}")

    install_root = _locate_install_root(extract_root)
    if install_root == extract_root:
        result = dest_dir
        if result.exists():
            shutil.rmtree(result)
        shutil.move(str(extract_root), str(result))
        return result

    result = dest_dir
    if result.exists():
        shutil.rmtree(result)
    result.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(install_root), str(result))
    return result


def _is_valid_install(path: Path) -> bool:
    if not path or not path.exists() or not path.is_dir():
        return False
    if (path / "renpy.sh").exists():
        return True
    if (path / "renpy.exe").exists():
        return True
    if (path / "Ren'Py Launcher.app").exists():
        return True
    return False


def _install_root() -> Path:
    env = os.getenv(REN_PY_ENV_ROOT)
    if env:
        return Path(env).expanduser()
    return REN_PY_INSTALL_ROOT


def _write_metadata(target_dir: Path, *, version: str, archive_name: str) -> None:
    payload = {
        "engine": "Ren'Py",
        "version": version,
        "archive": archive_name,
    }
    metadata_path = target_dir / "comfyvn.install.json"
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _chmod_x(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        path.chmod(mode | 0o111)
    except Exception as exc:  # pragma: no cover - permissions vary per platform
        LOGGER.debug("Failed to set executable bit on %s: %s", path, exc)


def _ensure_exec_bits(home: Path) -> None:
    candidates = [
        home / "renpy.sh",
        home / "renpy",
        home / "renpy.exe",
        home / "launcher" / "Renpy.exe",
    ]
    lib_dir = home / "lib"
    if lib_dir.exists():
        for root in lib_dir.rglob("renpy"):
            if root.is_file():
                candidates.append(root)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            _chmod_x(candidate)


def ensure_renpy_sdk(
    version: Optional[str] = None,
    *,
    install_root: Optional[Path] = None,
    client: Optional[httpx.Client] = None,
    force: bool = False,
) -> Path:
    base = Path(install_root) if install_root else _install_root()
    base.mkdir(parents=True, exist_ok=True)

    created_client = False
    if client is None:
        client = httpx.Client(follow_redirects=True, timeout=_TIMEOUT)
        created_client = True

    try:
        resolved_version = version or discover_latest_version(client)
        target_dir = base / f"renpy-{resolved_version}-sdk"
        if not force and _is_valid_install(target_dir):
            LOGGER.debug("Ren'Py SDK already present at %s", target_dir)
            return target_dir

        with tempfile.TemporaryDirectory(prefix="comfyvn-renpy-") as tmp:
            tmp_path = Path(tmp)
            archive_path = _download_archive(resolved_version, client, tmp_dir=tmp_path)
            installed_dir = _extract_archive(archive_path, target_dir)

        _write_metadata(
            target_dir, version=resolved_version, archive_name=archive_path.name
        )
        _ensure_exec_bits(installed_dir)
        executable = get_renpy_executable(installed_dir)
        LOGGER.info(
            "Ren'Py SDK ready at %s (version %s)", installed_dir, resolved_version
        )
        return installed_dir
    finally:
        if created_client:
            client.close()


def get_renpy_executable(home: Path) -> Optional[Path]:
    candidates: list[Path] = []
    if sys.platform.startswith("win"):
        candidates.append(home / "renpy.exe")
        candidates.append(home / "launcher" / "Renpy.exe")
    elif sys.platform == "darwin":
        candidates.append(home / "Ren'Py Launcher.app" / "Contents" / "MacOS" / "renpy")
        candidates.append(home / "renpy.sh")
    else:
        candidates.append(home / "renpy.sh")
        candidates.append(home / "renpy.py")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    fallback = list(home.rglob("renpy.sh"))
    if fallback:
        return fallback[0]
    fallback = list(home.rglob("renpy.exe"))
    if fallback:
        return fallback[0]
    fallback = list(home.rglob("renpy"))
    if fallback:
        return fallback[0]
    return None


__all__ = ["ensure_renpy_sdk", "discover_latest_version", "get_renpy_executable"]
