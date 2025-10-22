from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

TRUST_LEVELS = ("verified", "unverified")
MANIFEST_VERSION = "1.1"
MANIFEST_FILE_NAMES: tuple[str, ...] = ("manifest.json", "extension.json")
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,63}$")
KNOWN_PERMISSION_SCOPES: Mapping[str, str] = {
    "assets.read": "Read assets registry metadata and list assets.",
    "assets.write": "Register or update asset metadata/sidecars.",
    "assets.events": "Subscribe to asset registry hook events.",
    "assets.debug": "Access asset debug metrics, traces, and thumbnails.",
    "hooks.emit": "Emit modder hook events via the internal bus.",
    "hooks.listen": "Subscribe to modder hook events from the bus.",
    "ui.panels": "Register UI panels within the Studio shell.",
    "api.global": "Expose HTTP routes outside the extension namespace.",
    "sandbox.fs.limited": "Request write access to additional filesystem roots.",
    "diagnostics.read": "Access debug tooling endpoints exposed by the extension.",
    "extensions.lifecycle": "Listen for extension install/uninstall lifecycle events.",
}
DEFAULT_GLOBAL_ROUTE_ALLOWLIST: Mapping[str, Sequence[str]] = {
    "verified": ("/api/modder/", "/api/hooks/", "/api/extensions/", "/ws/modder"),
    "unverified": (),
}


class ManifestError(ValueError):
    """Raised when an extension manifest cannot be parsed or validated."""


class PermissionSpec(BaseModel):
    """Declarative permission request inside a manifest."""

    model_config = ConfigDict(extra="forbid")

    scope: str = Field(pattern=r"^[a-z0-9_.:-]+$", min_length=3)
    description: str | None = None
    optional: bool = False
    default: bool = False

    @field_validator("scope")
    @classmethod
    def _ensure_known_scope(cls, value: str) -> str:
        if value not in KNOWN_PERMISSION_SCOPES:
            raise ManifestError(f"permission scope '{value}' is not recognised")
        return value


class RouteSpec(BaseModel):
    """HTTP contribution declared by an extension."""

    model_config = ConfigDict(extra="allow")

    path: str = Field(min_length=1)
    entry: str = Field(min_length=1)
    callable: str = Field(min_length=1)
    methods: list[str] = Field(default_factory=lambda: ["GET"])
    expose: str = Field(default="extension")
    summary: str | None = None
    name: str | None = None
    status_code: int | None = None
    tags: list[str] = Field(default_factory=list)
    sandbox: str | None = None

    @field_validator("methods")
    @classmethod
    def _normalise_methods(cls, value: Iterable[str]) -> list[str]:
        methods: list[str] = []
        for method in value:
            if not isinstance(method, str):
                continue
            trimmed = method.strip().upper()
            if trimmed:
                methods.append(trimmed)
        return methods or ["GET"]

    @field_validator("expose")
    @classmethod
    def _validate_expose(cls, expose: str) -> str:
        expose_norm = expose.strip().lower()
        if expose_norm not in {"extension", "global"}:
            raise ManifestError("route.expose must be 'extension' or 'global'")
        return expose_norm

    @field_validator("path")
    @classmethod
    def _clean_path(cls, path: str) -> str:
        cleaned = path.strip()
        if not cleaned:
            raise ManifestError("route.path cannot be empty")
        if ".." in Path(cleaned).parts:
            raise ManifestError("route.path may not traverse directories")
        return cleaned

    @field_validator("entry")
    @classmethod
    def _validate_entry(cls, entry: str) -> str:
        candidate = Path(entry)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ManifestError("route.entry must stay within the extension directory")
        if candidate.suffix != ".py":
            raise ManifestError("route.entry must reference a Python file (.py)")
        return entry

    @field_validator("callable")
    @classmethod
    def _validate_callable(cls, value: str) -> str:
        if "." not in value:
            return value
        for segment in value.split("."):
            if not segment:
                raise ManifestError("route.callable contains empty attribute segment")
        return value


class EventSpec(BaseModel):
    """Event subscription contributions inside a manifest."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1)
    entry: str = Field(min_length=1)
    callable: str = Field(min_length=1)
    once: bool = False

    @field_validator("entry")
    @classmethod
    def _validate_entry(cls, entry: str) -> str:
        candidate = Path(entry)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ManifestError("event.entry must stay within the extension directory")
        if candidate.suffix != ".py":
            raise ManifestError("event.entry must reference a Python file (.py)")
        return entry

    @field_validator("callable")
    @classmethod
    def _validate_callable(cls, value: str) -> str:
        if "." not in value:
            return value
        for segment in value.split("."):
            if not segment:
                raise ManifestError("event.callable contains empty attribute segment")
        return value


class PanelSpec(BaseModel):
    """UI slot contributions."""

    model_config = ConfigDict(extra="allow")

    slot: str = Field(min_length=1)
    label: str = Field(min_length=1)
    path: str = Field(min_length=1)
    icon: str | None = None

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ManifestError(
                "ui.panel.path must be relative and stay inside the package"
            )
        return value


class UIConfig(BaseModel):
    """Aggregate UI contributions from a manifest."""

    model_config = ConfigDict(extra="allow")

    panels: list[PanelSpec] = Field(default_factory=list)


class DiagnosticsSpec(BaseModel):
    """Describes debug aids provided by an extension."""

    model_config = ConfigDict(extra="allow")

    log_topics: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    traces: list[str] = Field(default_factory=list)


class TrustInfo(BaseModel):
    """Trust metadata attached to an extension manifest or catalog entry."""

    model_config = ConfigDict(extra="allow")

    level: str = Field(default="unverified")
    signed_by: str | None = None
    signature: str | None = None
    reason: str | None = None
    verified_at: str | None = None
    signature_type: str | None = None

    @field_validator("level")
    @classmethod
    def _check_level(cls, level: str) -> str:
        normalised = level.strip().lower()
        if normalised not in TRUST_LEVELS:
            raise ManifestError(f"unsupported trust level '{level}'")
        return normalised

    @field_validator("signature", mode="before")
    @classmethod
    def _normalise_signature(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray)):
            return base64.b64encode(bytes(value)).decode("ascii")
        return str(value).strip() or None

    @field_validator("signature_type")
    @classmethod
    def _normalise_signature_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        return cleaned or None


class ExtensionManifest(BaseModel):
    """
    Typed representation of an extension manifest.

    The structure extends the legacy ``manifest.json`` schema used by the
    plugin loader with additional metadata fields. Existing manifests remain
    forward compatible because extra keys are preserved.
    """

    model_config = ConfigDict(extra="allow")

    manifest_version: str = Field(default=MANIFEST_VERSION)
    id: str = Field(pattern=ID_PATTERN.pattern, min_length=3, max_length=64)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    description: str | None = None
    license: str | None = None
    readme: str | None = None
    homepage: AnyHttpUrl | None = None
    repository: AnyHttpUrl | None = None
    issue_tracker: AnyHttpUrl | None = None
    authors: list[str] = Field(default_factory=list)
    maintainer: str | None = None
    categories: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    compatibility: dict[str, str] = Field(default_factory=dict)
    permissions: list[PermissionSpec] = Field(default_factory=list)
    routes: list[RouteSpec] = Field(default_factory=list)
    events: list[EventSpec] = Field(default_factory=list)
    ui: UIConfig = Field(default_factory=UIConfig)
    hooks: list[str] = Field(default_factory=list)
    diagnostics: DiagnosticsSpec = Field(default_factory=DiagnosticsSpec)
    trust: TrustInfo = Field(default_factory=TrustInfo)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _ensure_summary(cls, data: Any) -> Any:
        if not isinstance(data, MutableMapping):
            return data
        payload: MutableMapping[str, Any] = dict(data)
        if not payload.get("summary"):
            description = payload.get("description")
            if isinstance(description, str) and description.strip():
                payload["summary"] = description.strip()
        author = payload.get("author")
        authors = payload.get("authors")
        if author and not authors:
            if isinstance(author, str):
                payload["authors"] = [author.strip()]
            elif isinstance(author, Iterable):
                payload["authors"] = [str(item).strip() for item in author]
        return payload
        return data

    @field_validator("hooks")
    @classmethod
    def _deduplicate_hooks(cls, hooks: Iterable[str]) -> list[str]:
        result: list[str] = []
        for hook in hooks:
            if not isinstance(hook, str):
                continue
            trimmed = hook.strip()
            if trimmed and trimmed not in result:
                result.append(trimmed)
        return result

    @field_validator("authors")
    @classmethod
    def _sanitise_authors(cls, authors: Iterable[str]) -> list[str]:
        cleaned: list[str] = []
        for author in authors:
            if not isinstance(author, str):
                continue
            trimmed = author.strip()
            if trimmed:
                cleaned.append(trimmed)
        return cleaned

    @field_validator("categories")
    @classmethod
    def _sanitise_categories(cls, categories: Iterable[str]) -> list[str]:
        cleaned = []
        for category in categories:
            if not isinstance(category, str):
                continue
            trimmed = category.strip().lower().replace(" ", "-")
            if trimmed and trimmed not in cleaned:
                cleaned.append(trimmed)
        return cleaned

    def to_loader_payload(self) -> dict[str, Any]:
        """Return a dict matching the legacy loader expectations."""
        payload = self.model_dump(mode="python", exclude_none=True)
        payload.setdefault("description", self.description or self.summary)
        return payload

    # ------------------------------------------------------------------ Helpers
    def primary_author(self) -> str | None:
        """Return the first listed author when available."""
        return self.authors[0] if self.authors else None

    def contribution_summary(self) -> dict[str, Any]:
        """Summarise surfaced capabilities for marketplace listings."""
        return {
            "permissions": [perm.scope for perm in self.permissions],
            "routes": [
                {
                    "path": route.path,
                    "methods": route.methods,
                    "expose": route.expose,
                    "summary": route.summary,
                    "tags": route.tags,
                }
                for route in self.routes
            ],
            "events": [event.topic for event in self.events],
            "ui": {
                "panels": [
                    {"slot": panel.slot, "label": panel.label, "path": panel.path}
                    for panel in self.ui.panels
                ]
            },
            "hooks": list(self.hooks),
            "diagnostics": self.diagnostics.model_dump(),
        }

    def canonical_json(self) -> str:
        """Return the canonical marketplace JSON representation."""
        payload = self.to_loader_payload()
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def find_manifest_path(root: Path) -> Path:
    for candidate in MANIFEST_FILE_NAMES:
        manifest_path = root / candidate
        if manifest_path.exists():
            return manifest_path
    raise ManifestError(
        f"no manifest file found under {root} (expected one of {', '.join(MANIFEST_FILE_NAMES)})"
    )


def load_manifest(
    path: str | Path,
    *,
    trust_level: str | None = None,
    route_allowlist: Mapping[str, Sequence[str]] | None = None,
) -> ExtensionManifest:
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = find_manifest_path(manifest_path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - IO guard
        raise ManifestError(f"manifest file not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc
    return validate_manifest_payload(
        payload, trust_level=trust_level, route_allowlist=route_allowlist
    )


def validate_manifest_payload(
    payload: Mapping[str, Any],
    *,
    trust_level: str | None = None,
    route_allowlist: Mapping[str, Sequence[str]] | None = None,
) -> ExtensionManifest:
    try:
        manifest = ExtensionManifest.model_validate(payload)
    except ValidationError as exc:
        raise ManifestError(str(exc)) from exc
    except ManifestError:
        raise
    if trust_level:
        trust_data = manifest.trust.model_dump(exclude_none=True)
        trust_data["level"] = trust_level
        manifest.trust = TrustInfo(**trust_data)
    allowlist = route_allowlist or DEFAULT_GLOBAL_ROUTE_ALLOWLIST
    _enforce_route_allowlist(manifest, allowlist)
    return manifest


def _enforce_route_allowlist(
    manifest: ExtensionManifest,
    allowlist: Mapping[str, Sequence[str]],
) -> None:
    trust = manifest.trust.level
    allowed_prefixes = tuple(allowlist.get(trust, ()))
    for route in manifest.routes:
        if route.expose != "global":
            continue
        if not allowed_prefixes:
            raise ManifestError(
                f"global route '{route.path}' not allowed for trust level '{trust}'"
            )
        path = route.path
        if not path.startswith("/"):
            path = f"/{path}"
        if not any(path.startswith(prefix) for prefix in allowed_prefixes):
            raise ManifestError(
                f"global route '{route.path}' is outside the allowlist for trust level '{trust}'"
            )
