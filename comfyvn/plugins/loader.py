from __future__ import annotations

import importlib.util
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from comfyvn.core.event_bus import emit as event_emit  # noqa: F401
from comfyvn.core.event_bus import subscribe as event_subscribe
from comfyvn.core.event_bus import unsubscribe as event_unsubscribe
from comfyvn.market.manifest import (
    ExtensionManifest,
    validate_manifest_payload,
)
from comfyvn.market.manifest import (
    ManifestError as MarketManifestError,
)

LOGGER = logging.getLogger(__name__)


class PluginManifestError(RuntimeError):
    """Raised when a plugin manifest is invalid."""


@dataclass
class RouteContribution:
    path: str
    methods: List[str]
    handler: Callable[..., Any]
    expose: str = "extension"
    name: Optional[str] = None
    summary: Optional[str] = None
    status_code: Optional[int] = None
    tags: Optional[List[str]] = None


@dataclass
class EventContribution:
    topic: str
    handler: Callable[[Any], None]
    once: bool = False


@dataclass
class PanelContribution:
    slot: str
    label: str
    path: str
    icon: Optional[str] = None
    plugin_id: str = ""


@dataclass
class PluginDefinition:
    id: str
    name: str
    version: str
    description: str
    summary: str
    trust_level: str
    permissions: List[str]
    hooks: List[str]
    path: Path
    manifest_path: Path
    manifest: Dict[str, Any]
    manifest_model: ExtensionManifest | None
    enabled_by_default: bool
    enabled: bool
    routes: List[RouteContribution] = field(default_factory=list)
    events: List[EventContribution] = field(default_factory=list)
    panels: List[PanelContribution] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class PluginLoader:
    """
    Discover and manage extension plugins under the ``extensions`` directory.

    The loader validates each manifest, keeps track of enablement, registers
    event hooks, and exposes contributions (routes, UI panels) to callers.
    """

    def __init__(
        self, root: str | Path = "extensions", state_path: str | Path | None = None
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = (
            Path(state_path) if state_path is not None else self.root / "state.json"
        )
        self._state: Dict[str, Dict[str, Any]] = {}
        self._plugins: Dict[str, PluginDefinition] = {}
        self._active_events: Dict[str, List[Tuple[str, Callable[[Any], None]]]] = {}
        self._module_cache: Dict[Tuple[str, Path], Any] = {}
        self._load_state()

    # ------------------------------------------------------------------ State
    def _load_state(self) -> None:
        if not self.state_path.exists():
            self._state = {}
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                self._state = {
                    str(k): v for k, v in payload.items() if isinstance(v, dict)
                }
            else:
                self._state = {}
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to read plugin state %s: %s", self.state_path, exc)
            self._state = {}

    def _save_state(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(
                json.dumps(self._state, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning(
                "Failed to persist plugin state %s: %s", self.state_path, exc
            )

    # ---------------------------------------------------------------- Discovery
    def refresh(self) -> None:
        """Reload manifests, re-validate, and re-register event handlers."""
        self._unregister_all_events()
        self._module_cache.clear()
        self._plugins = {}
        for manifest_path in self._iter_manifests():
            plugin = self._build_plugin(manifest_path)
            if plugin:
                self._plugins[plugin.id] = plugin
        # Drop stale state entries
        self._state = {
            key: value for key, value in self._state.items() if key in self._plugins
        }
        # Apply state -> enabled flag
        for plugin in self._plugins.values():
            state_enabled = self._state.get(plugin.id, {}).get("enabled")
            plugin.enabled = bool(
                plugin.enabled_by_default if state_enabled is None else state_enabled
            )
            if plugin.errors:
                plugin.enabled = False
            self._state.setdefault(plugin.id, {})["enabled"] = plugin.enabled
            if plugin.enabled and not plugin.errors:
                self._register_events(plugin)
        self._save_state()

    def _iter_manifests(self) -> Iterable[Path]:
        if not self.root.exists():
            return []
        for entry in sorted(self.root.iterdir(), key=lambda p: p.name.lower()):
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            manifest = entry / "manifest.json"
            if manifest.is_file():
                yield manifest

    def _build_plugin(self, manifest_path: Path) -> Optional[PluginDefinition]:
        manifest_dir = manifest_path.parent
        errors: List[str] = []
        warnings: List[str] = []
        payload = self._read_manifest(manifest_path, errors)
        if payload is None:
            return None

        manifest_obj: ExtensionManifest | None = None
        manifest_payload = payload
        try:
            manifest_obj = validate_manifest_payload(payload)
            manifest_payload = manifest_obj.to_loader_payload()
        except MarketManifestError as exc:
            errors.append(f"manifest validation failed: {exc}")

        plugin_id = str(manifest_payload.get("id") or manifest_dir.name)
        name = str(manifest_payload.get("name") or plugin_id)
        version = str(manifest_payload.get("version") or "0.0.0")
        description = str(manifest_payload.get("description") or "")
        summary = str(
            manifest_payload.get("summary")
            or description
            or manifest_payload.get("name")
            or plugin_id
        )
        enabled_by_default = bool(manifest_payload.get("enabled", True))
        if manifest_obj is not None:
            trust_level = manifest_obj.trust.level
        else:
            raw_trust = manifest_payload.get("trust")
            if isinstance(raw_trust, dict):
                trust_level = str(raw_trust.get("level", "unverified"))
            else:
                trust_level = str(raw_trust or "unverified")
        trust_level = trust_level.lower() or "unverified"
        if manifest_obj is not None:
            permissions = [perm.scope for perm in manifest_obj.permissions]
            hooks_declared = list(manifest_obj.hooks)
        else:
            permissions = []
            for item in manifest_payload.get("permissions", []) or []:
                scope = item.get("scope") if isinstance(item, dict) else item
                if scope:
                    permissions.append(str(scope))
            hooks_declared = []
            for hook in manifest_payload.get("hooks", []) or []:
                if isinstance(hook, str) and hook:
                    hooks_declared.append(hook)

        plugin = PluginDefinition(
            id=plugin_id,
            name=name,
            version=version,
            description=description,
            summary=summary,
            trust_level=trust_level,
            permissions=permissions,
            hooks=hooks_declared,
            path=manifest_dir,
            manifest_path=manifest_path,
            manifest=manifest_payload,
            manifest_model=manifest_obj,
            enabled_by_default=enabled_by_default,
            enabled=False,
            errors=errors,
            warnings=warnings,
        )

        if plugin_id in self._plugins:
            plugin.errors.append("duplicate plugin identifier")
            return plugin

        self._load_routes(plugin, payload.get("routes"))
        self._load_events(plugin, payload.get("events"))
        self._load_ui(plugin, payload.get("ui"))
        return plugin

    def _read_manifest(self, manifest_path: Path, errors: List[str]) -> Optional[dict]:
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"manifest unreadable: {exc}")
            return None
        if not isinstance(raw, dict):
            errors.append("manifest must be a JSON object")
            return None
        return raw

    # -------------------------------------------------------------- Load parts
    def _load_routes(self, plugin: PluginDefinition, routes_payload: Any) -> None:
        if not routes_payload:
            return
        if not isinstance(routes_payload, list):
            plugin.errors.append("routes must be an array")
            return
        for idx, spec in enumerate(routes_payload):
            if not isinstance(spec, dict):
                plugin.errors.append(f"route[{idx}] must be an object")
                continue
            entry_name = str(spec.get("entry") or "")
            callable_name = str(spec.get("callable") or "")
            path_value = str(spec.get("path") or "")
            if not entry_name or not callable_name or not path_value:
                plugin.errors.append(f"route[{idx}] requires entry, callable, and path")
                continue
            methods_value = spec.get("methods") or ["GET"]
            methods: List[str] = []
            if isinstance(methods_value, list):
                for method in methods_value:
                    if isinstance(method, str) and method:
                        methods.append(method.upper())
            if not methods:
                methods = ["GET"]

            expose = str(spec.get("expose") or "extension")
            if expose not in {"extension", "global"}:
                plugin.warnings.append(
                    f"route[{idx}] has unknown expose value '{expose}', defaulting to 'extension'"
                )
                expose = "extension"

            try:
                module = self._load_module(plugin, entry_name)
                handler = self._resolve_callable(module, callable_name)
            except PluginManifestError as exc:
                plugin.errors.append(f"route[{idx}] {exc}")
                continue

            contribution = RouteContribution(
                path=path_value,
                methods=methods,
                handler=handler,
                expose=expose,
                name=str(spec.get("name") or "") or None,
                summary=str(spec.get("summary") or "") or None,
                status_code=spec.get("status_code"),
                tags=[str(tag) for tag in spec.get("tags", []) if tag],
            )
            plugin.routes.append(contribution)

    def _load_events(self, plugin: PluginDefinition, events_payload: Any) -> None:
        if not events_payload:
            return
        if not isinstance(events_payload, list):
            plugin.errors.append("events must be an array")
            return
        for idx, spec in enumerate(events_payload):
            if not isinstance(spec, dict):
                plugin.errors.append(f"event[{idx}] must be an object")
                continue
            entry_name = str(spec.get("entry") or "")
            callable_name = str(spec.get("callable") or "")
            topic = str(spec.get("topic") or "")
            if not entry_name or not callable_name or not topic:
                plugin.errors.append(
                    f"event[{idx}] requires entry, callable, and topic"
                )
                continue
            try:
                module = self._load_module(plugin, entry_name)
                handler = self._resolve_callable(module, callable_name)
            except PluginManifestError as exc:
                plugin.errors.append(f"event[{idx}] {exc}")
                continue
            contribution = EventContribution(
                topic=topic,
                handler=handler,  # type: ignore[arg-type]
                once=bool(spec.get("once", False)),
            )
            plugin.events.append(contribution)

    def _load_ui(self, plugin: PluginDefinition, ui_payload: Any) -> None:
        if not ui_payload or not isinstance(ui_payload, dict):
            return
        panels_payload = ui_payload.get("panels")
        if not panels_payload:
            return
        if not isinstance(panels_payload, list):
            plugin.errors.append("ui.panels must be an array")
            return
        for idx, spec in enumerate(panels_payload):
            if not isinstance(spec, dict):
                plugin.errors.append(f"ui.panels[{idx}] must be an object")
                continue
            slot = str(spec.get("slot") or "")
            label = str(spec.get("label") or "")
            asset_path = str(spec.get("path") or "")
            if not slot or not label or not asset_path:
                plugin.errors.append(f"ui.panels[{idx}] requires slot, label, and path")
                continue
            if ".." in Path(asset_path).parts:
                plugin.errors.append(
                    f"ui.panels[{idx}] path may not traverse directories"
                )
                continue
            panel = PanelContribution(
                slot=slot,
                label=label,
                path=asset_path,
                icon=str(spec.get("icon") or "") or None,
                plugin_id=plugin.id,
            )
            plugin.panels.append(panel)

    # ------------------------------------------------------------ Module utils
    def _load_module(self, plugin: PluginDefinition, entry_name: str):
        entry_path = Path(entry_name)
        if entry_path.is_absolute() or ".." in entry_path.parts:
            raise PluginManifestError("entry path must be relative and within plugin")
        resolved = (plugin.path / entry_path).resolve()
        try:
            resolved.relative_to(plugin.path.resolve())
        except ValueError:
            raise PluginManifestError("entry path escapes plugin directory") from None
        if not resolved.exists():
            raise PluginManifestError(f"entry '{entry_name}' not found")
        if resolved.suffix != ".py":
            raise PluginManifestError("entry must reference a Python file (.py)")

        cache_key = (plugin.id, resolved)
        cached = self._module_cache.get(cache_key)
        if cached is not None:
            return cached

        module_name = self._module_name(plugin.id, entry_path)
        spec = importlib.util.spec_from_file_location(module_name, resolved)
        if spec is None or spec.loader is None:
            raise PluginManifestError(f"unable to load entry '{entry_name}'")
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)  # type: ignore[arg-type]
        except Exception as exc:
            self._module_cache.pop(cache_key, None)
            raise PluginManifestError(f"error importing entry '{entry_name}': {exc}")
        self._module_cache[cache_key] = module
        return module

    def _module_name(self, plugin_id: str, entry_path: Path) -> str:
        base = entry_path.with_suffix("")
        parts = [plugin_id] + [p for p in base.parts if p not in {".", ""}]

        def _sanitize(token: str) -> str:
            return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in token)

        suffix = "_".join(_sanitize(part) for part in parts if part)
        return f"comfyvn_ext_{suffix}"

    def _resolve_callable(self, module: Any, attr: str) -> Callable[..., Any]:
        target = module
        for chunk in attr.split("."):
            if not chunk:
                raise PluginManifestError("callable contains empty attribute segment")
            if not hasattr(target, chunk):
                raise PluginManifestError(f"callable '{attr}' not found")
            target = getattr(target, chunk)
        if not callable(target):
            raise PluginManifestError(f"callable '{attr}' is not callable")
        return target

    # ------------------------------------------------------------ Event hooks
    def _register_events(self, plugin: PluginDefinition) -> None:
        if not plugin.events:
            return
        holders: List[Tuple[str, Callable[[Any], None]]] = []
        for spec in plugin.events:
            if spec.once:
                handler = self._wrap_once_handler(plugin.id, spec.topic, spec.handler)
            else:
                handler = spec.handler
            event_subscribe(spec.topic, handler)
            holders.append((spec.topic, handler))
        self._active_events[plugin.id] = holders

    def _wrap_once_handler(
        self, plugin_id: str, topic: str, handler: Callable[[Any], None]
    ) -> Callable[[Any], None]:
        def _wrapper(payload: Any) -> None:
            try:
                handler(payload)
            finally:
                self._unregister_handler(plugin_id, topic, _wrapper)

        return _wrapper

    def _unregister_handler(
        self, plugin_id: str, topic: str, handler: Callable[[Any], None]
    ) -> None:
        try:
            event_unsubscribe(topic, handler)
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug(
                "Failed to unsubscribe handler for plugin %s topic %s",
                plugin_id,
                topic,
            )
        entries = self._active_events.get(plugin_id)
        if not entries:
            return
        self._active_events[plugin_id] = [
            entry for entry in entries if entry != (topic, handler)
        ]
        if not self._active_events[plugin_id]:
            self._active_events.pop(plugin_id, None)

    def _unregister_all_events(self) -> None:
        for plugin_id, entries in list(self._active_events.items()):
            for topic, handler in entries:
                self._unregister_handler(plugin_id, topic, handler)
        self._active_events.clear()

    # ------------------------------------------------------------ Public API
    @property
    def plugins(self) -> Dict[str, PluginDefinition]:
        return self._plugins

    def list_plugins(self) -> List[PluginDefinition]:
        return list(self._plugins.values())

    def get(self, plugin_id: str) -> PluginDefinition:
        if plugin_id not in self._plugins:
            raise KeyError(plugin_id)
        return self._plugins[plugin_id]

    def enabled_plugins(self) -> List[PluginDefinition]:
        return [p for p in self._plugins.values() if p.enabled and not p.errors]

    def enable(self, plugin_id: str) -> PluginDefinition:
        plugin = self.get(plugin_id)
        if plugin.errors:
            raise PluginManifestError(
                f"plugin '{plugin_id}' cannot be enabled: {plugin.errors[0]}"
            )
        if plugin.enabled:
            return plugin
        plugin.enabled = True
        self._state.setdefault(plugin_id, {})["enabled"] = True
        self._save_state()
        self._register_events(plugin)
        return plugin

    def disable(self, plugin_id: str) -> PluginDefinition:
        plugin = self.get(plugin_id)
        if not plugin.enabled:
            return plugin
        plugin.enabled = False
        self._state.setdefault(plugin_id, {})["enabled"] = False
        self._save_state()
        entries = self._active_events.pop(plugin_id, [])
        for topic, handler in entries:
            self._unregister_handler(plugin_id, topic, handler)
        return plugin

    def panels_for_enabled(self) -> List[PanelContribution]:
        panels: List[PanelContribution] = []
        for plugin in self.enabled_plugins():
            panels.extend(plugin.panels)
        return panels

    def resolve_panel_asset(self, plugin_id: str, rel_path: str) -> Path:
        plugin = self.get(plugin_id)
        if not plugin.enabled or plugin.errors:
            raise FileNotFoundError(rel_path)
        candidate = Path(rel_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise FileNotFoundError(rel_path)
        resolved = (plugin.path / candidate).resolve()
        try:
            resolved.relative_to(plugin.path.resolve())
        except ValueError:
            raise FileNotFoundError(rel_path) from None
        if not resolved.is_file():
            raise FileNotFoundError(rel_path)
        return resolved
