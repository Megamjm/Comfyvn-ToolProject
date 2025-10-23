from __future__ import annotations

import hashlib
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
REN_PY_CACHE_ROOT = Path("tools/cache/renpy")
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _ensure_cache_root(cache_dir: Optional[Path] = None) -> Path:
    base = Path(cache_dir) if cache_dir else _repo_root() / REN_PY_CACHE_ROOT
    base.mkdir(parents=True, exist_ok=True)
    return base


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _record_checksum(path: Path, checksum: str) -> None:
    path.write_text(checksum, encoding="utf-8")


def _validate_cached_archive(archive_path: Path, checksum_path: Path) -> bool:
    checksum = _compute_sha256(archive_path)
    if checksum_path.exists():
        recorded = checksum_path.read_text(encoding="utf-8").strip()
        if recorded != checksum:
            LOGGER.warning(
                "Cached Ren'Py archive checksum mismatch (%s); redownloading",
                archive_path.name,
            )
            return False
    _record_checksum(checksum_path, checksum)
    LOGGER.info(
        "Reusing cached Ren'Py archive %s (sha256=%s)",
        archive_path.name,
        checksum,
    )
    return True


def _download_archive(
    version: str, client: httpx.Client, *, cache_dir: Optional[Path] = None
) -> Path:
    cache_root = _ensure_cache_root(cache_dir)
    errors: list[str] = []
    for filename in _candidate_archives(version):
        url = f"{REN_PY_BASE_URL}{version}/{filename}"
        archive_path = cache_root / filename
        checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
        if archive_path.exists():
            if checksum_path.exists():
                if _validate_cached_archive(archive_path, checksum_path):
                    return archive_path
                archive_path.unlink(missing_ok=True)
                checksum_path.unlink(missing_ok=True)
            else:
                checksum = _compute_sha256(archive_path)
                _record_checksum(checksum_path, checksum)
                LOGGER.info(
                    "Recorded checksum for cached Ren'Py archive %s (sha256=%s)",
                    archive_path.name,
                    checksum,
                )
                return archive_path
        try:
            with client.stream("GET", url, timeout=_TIMEOUT) as resp:
                status = getattr(resp, "status_code", 0)
                if status == 404:
                    continue
                if status and status >= 400:
                    errors.append(f"{filename}: HTTP {status}")
                    continue
                tmp_path = archive_path.with_suffix(archive_path.suffix + ".part")
                tmp_path.parent.mkdir(parents=True, exist_ok=True)
                with tmp_path.open("wb") as fh:
                    for chunk in resp.iter_bytes():
                        if chunk:
                            fh.write(chunk)
                tmp_checksum = _compute_sha256(tmp_path)
                tmp_path.rename(archive_path)
                _record_checksum(checksum_path, tmp_checksum)
                LOGGER.info(
                    "Downloaded Ren'Py archive %s (sha256=%s)",
                    filename,
                    tmp_checksum,
                )
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


def _extract_archive(archive_path: Path, dest_dir: Path, *, work_dir: Path) -> Path:
    extract_root = work_dir / "extracted"
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
    cache_dir: Optional[Path] = None,
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

        cache_root = _ensure_cache_root(cache_dir)
        archive_path = _download_archive(resolved_version, client, cache_dir=cache_root)

        with tempfile.TemporaryDirectory(
            prefix="comfyvn-renpy-", dir=cache_root
        ) as tmp:
            tmp_path = Path(tmp)
            installed_dir = _extract_archive(
                archive_path, target_dir, work_dir=tmp_path
            )

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
