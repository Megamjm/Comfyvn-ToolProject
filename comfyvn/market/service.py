from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence
from zipfile import ZipFile

from comfyvn.market.manifest import (
    DEFAULT_GLOBAL_ROUTE_ALLOWLIST,
    ExtensionManifest,
    ManifestError,
    TrustInfo,
    load_manifest,
    validate_manifest_payload,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_CATALOG_PATH = Path("config/market_catalog.json")
STATE_FILENAME = ".market.json"


@dataclass
class MarketEntry:
    id: str
    name: str
    version: str
    summary: str
    trust: str
    package: str | None
    permissions: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    homepage: str | None = None
    manifest: ExtensionManifest | None = None
    source: str = "catalog"

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "summary": self.summary,
            "trust": self.trust,
            "permissions": self.permissions,
            "hooks": self.hooks,
            "tags": self.tags,
            "authors": self.authors,
            "homepage": self.homepage,
            "package": self.package,
            "source": self.source,
        }


class MarketCatalog:
    """Load marketplace metadata from disk with a local fallback."""

    def __init__(
        self,
        catalog_path: Path | str | None = None,
        extensions_root: Path | str = "extensions",
    ) -> None:
        self.catalog_path = (
            Path(catalog_path).expanduser()
            if catalog_path is not None
            else DEFAULT_CATALOG_PATH
        )
        self.extensions_root = Path(extensions_root).expanduser()
        self._entries: dict[str, MarketEntry] = {}
        self.reload()

    # ------------------------------------------------------------------ Loaders
    def reload(self) -> None:
        entries: dict[str, MarketEntry] = {}
        if self.catalog_path.exists():
            for entry in self._load_from_file(self.catalog_path):
                entries[entry.id] = entry
        if not entries:
            for entry in self._load_from_extensions_root(self.extensions_root):
                entries.setdefault(entry.id, entry)
        self._entries = entries

    def _load_from_file(self, path: Path) -> Iterable[MarketEntry]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("Failed to read market catalog %s: %s", path, exc)
            return []
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            LOGGER.warning("Catalog %s missing 'items' array", path)
            return []
        for raw in items:
            entry = self._entry_from_payload(raw, base_path=path.parent)
            if entry:
                yield entry

    def _entry_from_payload(
        self, payload: Any, *, base_path: Path
    ) -> MarketEntry | None:
        if not isinstance(payload, dict):
            return None
        manifest_obj: ExtensionManifest | None = None
        manifest_hint = payload.get("manifest")
        if manifest_hint:
            manifest_path = (base_path / str(manifest_hint)).expanduser()
            try:
                manifest_obj = load_manifest(manifest_path)
            except ManifestError:
                LOGGER.debug(
                    "Skipping manifest for catalog entry %s (invalid)",
                    payload.get("id"),
                    exc_info=True,
                )
                manifest_obj = None
        entry_id = str(
            payload.get("id") or (manifest_obj.id if manifest_obj else "")
        ).strip()
        if not entry_id:
            LOGGER.debug("Catalog entry missing id; skipping: %s", payload)
            return None
        name = str(
            payload.get("name") or (manifest_obj.name if manifest_obj else entry_id)
        )
        version = str(
            payload.get("version")
            or (manifest_obj.version if manifest_obj else "0.0.0")
        )
        manifest_summary = (
            manifest_obj.summary if manifest_obj else str(payload.get("summary") or "")
        )
        if not manifest_summary:
            manifest_summary = str(payload.get("description") or "")
        if not manifest_summary:
            manifest_summary = name
        trust = str(
            payload.get("trust")
            or (manifest_obj.trust.level if manifest_obj else "unverified")
        ).lower()
        package_value = str(payload.get("package") or "").strip() or None

        return MarketEntry(
            id=entry_id,
            name=name,
            version=version,
            summary=manifest_summary,
            trust=trust,
            package=package_value,
            permissions=[str(scope) for scope in payload.get("permissions", [])]
            or (
                [perm.scope for perm in manifest_obj.permissions]
                if manifest_obj
                else []
            ),
            hooks=list(
                payload.get("hooks") or (manifest_obj.hooks if manifest_obj else [])
            ),
            tags=list(
                payload.get("tags") or (manifest_obj.categories if manifest_obj else [])
            ),
            authors=list(
                payload.get("authors") or (manifest_obj.authors if manifest_obj else [])
            ),
            homepage=str(
                payload.get("homepage")
                or (manifest_obj.homepage if manifest_obj else "")
            )
            or None,
            manifest=manifest_obj,
            source="catalog",
        )

    def _load_from_extensions_root(self, root: Path) -> Iterable[MarketEntry]:
        if not root.exists():
            return []
        for manifest_path in root.glob("*/manifest.json"):
            try:
                manifest = load_manifest(manifest_path)
            except ManifestError:
                LOGGER.debug(
                    "Skipping invalid manifest: %s", manifest_path, exc_info=True
                )
                continue
            summary = manifest.summary or manifest.description or manifest.name
            yield MarketEntry(
                id=manifest.id,
                name=manifest.name,
                version=manifest.version,
                summary=summary,
                trust=manifest.trust.level,
                package=None,
                permissions=[perm.scope for perm in manifest.permissions],
                hooks=list(manifest.hooks),
                tags=list(manifest.categories),
                authors=list(manifest.authors),
                homepage=str(manifest.homepage) if manifest.homepage else None,
                manifest=manifest,
                source="local",
            )

    # ------------------------------------------------------------------ Public
    def entries(self) -> list[MarketEntry]:
        return list(self._entries.values())

    def find(self, extension_id: str) -> MarketEntry | None:
        return self._entries.get(extension_id)


@dataclass
class InstallResult:
    extension_id: str
    manifest: ExtensionManifest
    target_path: Path
    trust: TrustInfo
    package_path: Path
    package_sha256: str
    installed_at: datetime

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.extension_id,
            "trust": self.trust.model_dump(exclude_none=True),
            "path": str(self.target_path),
            "manifest": self.manifest.to_loader_payload(),
            "package": str(self.package_path),
            "sha256": self.package_sha256,
            "installed_at": self.installed_at.replace(tzinfo=timezone.utc).isoformat(),
        }


class ExtensionMarket:
    """Handle install/uninstall flows for marketplace extensions."""

    def __init__(
        self,
        *,
        extensions_root: Path | str = "extensions",
        catalog: MarketCatalog | None = None,
        state_path: Path | str | None = None,
        route_allowlist: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self.extensions_root = Path(extensions_root).expanduser()
        self.extensions_root.mkdir(parents=True, exist_ok=True)
        self.catalog = catalog or MarketCatalog(extensions_root=self.extensions_root)
        self.state_path = (
            Path(state_path).expanduser()
            if state_path is not None
            else (self.extensions_root / STATE_FILENAME)
        )
        self.route_allowlist = route_allowlist or DEFAULT_GLOBAL_ROUTE_ALLOWLIST
        self._state: MutableMapping[str, Any] = self._load_state()

    # ------------------------------------------------------------------ State IO
    def _load_state(self) -> MutableMapping[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            LOGGER.debug("Failed to read market state; starting fresh", exc_info=True)
        return {}

    def _save_state(self) -> None:
        payload = json.dumps(self._state, indent=2, sort_keys=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(payload, encoding="utf-8")

    # ------------------------------------------------------------------ Helpers
    def _compute_sha256(self, path: Path, chunk_size: int = 65536) -> str:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _extract_archive(self, archive: ZipFile, destination: Path) -> None:
        for member in archive.infolist():
            name = member.filename
            if not name or name.endswith("/"):
                continue
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts:
                raise ManifestError(f"package member escapes extension root: {name}")
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)

    def _detect_manifest_from_archive(
        self, archive: ZipFile
    ) -> tuple[str, ExtensionManifest]:
        for candidate in ("manifest.json", "extension.json"):
            try:
                raw = archive.read(candidate)
            except KeyError:
                continue
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ManifestError(
                    f"{candidate} in archive is not valid JSON: {exc}"
                ) from exc
            manifest = validate_manifest_payload(
                payload, route_allowlist=self.route_allowlist
            )
            return candidate, manifest
        raise ManifestError("archive is missing manifest.json or extension.json")

    # ------------------------------------------------------------------ Public
    def list_catalog(self) -> list[dict[str, Any]]:
        return [entry.to_payload() for entry in self.catalog.entries()]

    def list_installed(self) -> list[dict[str, Any]]:
        return list(self._state.values())

    def install(
        self,
        package_path: Path | str,
        *,
        trust_override: str | None = None,
    ) -> InstallResult:
        package = Path(package_path).expanduser()
        if not package.exists():
            raise ManifestError(f"package file not found: {package}")
        package_sha = self._compute_sha256(package)
        with ZipFile(package, "r") as archive:
            manifest_name, manifest = self._detect_manifest_from_archive(archive)
            if trust_override:
                trust = trust_override
            else:
                catalog_entry = self.catalog.find(manifest.id)
                trust = catalog_entry.trust if catalog_entry else manifest.trust.level
            trust = str(trust).lower()
            manifest = validate_manifest_payload(
                manifest.model_dump(mode="python"),
                trust_level=trust,
                route_allowlist=self.route_allowlist,
            )
            target = self.extensions_root / manifest.id
            if target.exists():
                raise ManifestError(f"extension '{manifest.id}' already installed")
            target.mkdir(parents=True, exist_ok=True)
            self._extract_archive(archive, target)

        installed_at = datetime.now(timezone.utc)
        sidecar_payload = {
            "id": manifest.id,
            "version": manifest.version,
            "trust": manifest.trust.model_dump(exclude_none=True),
            "package": str(package),
            "sha256": package_sha,
            "installed_at": installed_at.isoformat(),
        }
        (target / STATE_FILENAME).write_text(
            json.dumps(sidecar_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._state[manifest.id] = sidecar_payload
        self._save_state()

        return InstallResult(
            extension_id=manifest.id,
            manifest=manifest,
            target_path=target,
            trust=manifest.trust,
            package_path=package,
            package_sha256=package_sha,
            installed_at=installed_at,
        )

    def uninstall(self, extension_id: str) -> bool:
        target = self.extensions_root / extension_id
        if not target.exists():
            raise ManifestError(f"extension '{extension_id}' is not installed")
        try:
            shutil.rmtree(target)
        except Exception as exc:
            raise ManifestError(
                f"failed to remove extension '{extension_id}': {exc}"
            ) from exc
        self._state.pop(extension_id, None)
        self._save_state()
        return True
