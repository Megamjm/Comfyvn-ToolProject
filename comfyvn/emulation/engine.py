"""
Character emulation engine with SillyCompatOffload feature flag support.

The engine keeps lightweight persona memory, style guide notes, and safety
preferences and uses the shared LLM adapter registry to emit responses when the
feature flag is enabled.  When disabled the engine behaves as a no-op so that
SillyTavern installs remain unaffected by default.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

from comfyvn.core.settings_manager import SettingsManager
from comfyvn.models import get_registry, resolve_provider
from comfyvn.models.adapters import AdapterError, ChatResult, adapter_from_config
from comfyvn.models.registry import ModelEntry, ProviderConfig

LOGGER = logging.getLogger(__name__)
FEATURE_FLAG = "SillyCompatOffload"
_MAX_HISTORY_PAIRS = 20


def _coerce_history(messages: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        role = str(message.get("role") or "").strip() or "user"
        content = message.get("content")
        if isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
            text = "\n".join(str(item) for item in content)
        else:
            text = "" if content is None else str(content)
        history.append({"role": role, "content": text})
    return history


def _coerce_list(items: Iterable[Any] | None) -> list[str]:
    if not items:
        return []
    coerced: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            coerced.append(text)
    return coerced


def _merge_dict(
    base: Mapping[str, Any] | None, updates: Mapping[str, Any] | None
) -> dict:
    merged: dict[str, Any] = dict(base or {})
    for key, value in (updates or {}).items():
        merged[key] = value
    return merged


def _bool_from_env(env_value: str) -> bool:
    lowered = env_value.strip().lower()
    return lowered not in {"0", "false", "off", "no"}


@dataclass(slots=True)
class PersonaState:
    persona_id: str
    memory: list[dict[str, Any]] = field(default_factory=list)
    style_guides: list[str] = field(default_factory=list)
    safety: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "memory": list(self.memory),
            "style_guides": list(self.style_guides),
            "safety": dict(self.safety),
            "metadata": dict(self.metadata),
        }


class CharacterEmulationEngine:
    """Feature-flagged persona emulation helper."""

    def __init__(self, settings: SettingsManager | None = None) -> None:
        self._settings = settings or SettingsManager()
        self._lock = RLock()
        self._personas: dict[str, PersonaState] = {}

    # --------------------------------------------------------------------- #
    # Feature flag helpers
    # --------------------------------------------------------------------- #
    @property
    def enabled(self) -> bool:
        env_override = os.getenv("COMFYVN_SILLY_COMPAT_OFFLOAD")
        if isinstance(env_override, str) and env_override.strip():
            return _bool_from_env(env_override)
        try:
            settings = self._settings.load()
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Failed to load settings for emulation flag: %s", exc)
            return False
        features = settings.get("features")
        if isinstance(features, Mapping):
            value = features.get("silly_compat_offload")
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return _bool_from_env(value)
        return False

    def set_enabled(self, enabled: bool) -> bool:
        with self._lock:
            settings = self._settings.load()
            features = settings.setdefault("features", {})
            if not isinstance(features, MutableMapping):
                features = {}
                settings["features"] = features
            if bool(features.get("silly_compat_offload")) != bool(enabled):
                features["silly_compat_offload"] = bool(enabled)
                try:
                    self._settings.save(settings)
                except Exception as exc:  # pragma: no cover - filesystem
                    LOGGER.warning("Failed to persist emulation flag: %s", exc)
            return bool(enabled)

    # --------------------------------------------------------------------- #
    # Persona state management
    # --------------------------------------------------------------------- #
    def _persona(self, persona_id: str) -> PersonaState:
        key = persona_id.strip() or "default"
        with self._lock:
            state = self._personas.get(key)
            if state is None:
                state = PersonaState(persona_id=key)
                self._personas[key] = state
            return state

    def configure_persona(
        self,
        persona_id: str,
        *,
        memory: Iterable[Mapping[str, Any]] | None = None,
        style_guides: Iterable[str] | None = None,
        safety: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> PersonaState:
        state = self._persona(persona_id)
        with self._lock:
            if memory is not None:
                state.memory = _coerce_history(memory)
            if style_guides is not None:
                state.style_guides = _coerce_list(style_guides)
            if safety is not None:
                state.safety = _merge_dict(state.safety, safety)
            if metadata is not None:
                state.metadata = _merge_dict(state.metadata, metadata)
        return state

    def append_history(
        self, persona_id: str, messages: Iterable[Mapping[str, Any]], reply: str
    ) -> None:
        history = _coerce_history(messages)
        if reply:
            history.append({"role": "assistant", "content": reply})
        state = self._persona(persona_id)
        with self._lock:
            state.memory.extend(history[-2:])
            if len(state.memory) > (_MAX_HISTORY_PAIRS * 2):
                state.memory = state.memory[-(_MAX_HISTORY_PAIRS * 2) :]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "feature_flag": FEATURE_FLAG,
                "enabled": self.enabled,
                "persona_count": len(self._personas),
                "personas": [state.snapshot() for state in self._personas.values()],
            }

    # --------------------------------------------------------------------- #
    # LLM dispatch helpers
    # --------------------------------------------------------------------- #
    def _module_defaults(
        self,
        module: str | None,
    ) -> tuple[str | None, str | None, dict[str, Any]]:
        registry = get_registry()
        defaults = registry.get("defaults") if isinstance(registry, Mapping) else {}
        if not isinstance(defaults, Mapping):
            defaults = {}

        modules = defaults.get("modules")
        module_defaults: Mapping[str, Any] | None = None
        if module and isinstance(modules, Mapping):
            target = module.strip().lower()
            for key, config in modules.items():
                if str(key).strip().lower() == target and isinstance(config, Mapping):
                    module_defaults = config
                    break

        provider = None
        model = None
        options: dict[str, Any] = {}

        if isinstance(defaults.get("options"), Mapping):
            options.update({k: v for k, v in defaults["options"].items()})
        if isinstance(module_defaults, Mapping):
            provider = module_defaults.get("provider") or provider
            model = module_defaults.get("model") or model
            module_opts = module_defaults.get("options")
            if isinstance(module_opts, Mapping):
                options.update({k: v for k, v in module_opts.items()})

        provider = provider or defaults.get("provider")
        model = model or defaults.get("model")

        provider_id = str(provider).strip() if provider else None
        model_id = str(model).strip() if model else None

        return provider_id or None, model_id or None, options

    def _resolve_adapter(
        self,
        module: str | None,
        provider_hint: str | None,
        model_hint: str | None,
    ) -> tuple[ProviderConfig, ModelEntry, dict[str, Any]]:
        default_provider, default_model, default_options = self._module_defaults(module)

        provider_id = (provider_hint or default_provider or "").strip()
        if not provider_id:
            raise AdapterError("No provider configured for character emulation")

        provider = resolve_provider(provider_id)
        if provider is None:
            raise AdapterError(f"Provider '{provider_id}' not found in registry")

        model_id = (model_hint or default_model or "").strip()
        model_entry: ModelEntry | None = None
        if model_id:
            model_entry = provider.find_model(model_id)
        if model_entry is None:
            if provider.models:
                model_entry = provider.models[0]
                LOGGER.debug(
                    "Falling back to provider %s default model %s",
                    provider.name,
                    model_entry.id,
                )
            else:
                raise AdapterError(
                    f"Provider '{provider.name}' has no models configured"
                )

        return provider, model_entry, dict(default_options)

    def plan_dispatch(
        self,
        *,
        module: str | None,
        provider: str | None,
        model: str | None,
    ) -> tuple[ProviderConfig, ModelEntry, dict[str, Any]]:
        """Resolve the provider/model/options that would be used for a chat call."""
        return self._resolve_adapter(module, provider, model)

    def chat(
        self,
        persona_id: str,
        messages: Iterable[Mapping[str, Any]],
        *,
        module: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> ChatResult:
        if not self.enabled:
            raise AdapterError("SillyCompatOffload feature flag is disabled")

        provider_cfg, model_entry, default_options = self.plan_dispatch(
            module=module,
            provider=provider,
            model=model,
        )

        adapter = adapter_from_config(provider_cfg)

        dispatch_options = dict(default_options)
        if isinstance(options, Mapping):
            dispatch_options.update({k: v for k, v in options.items() if v is not None})

        history = list(messages)
        if not history:
            raise AdapterError("Messages array cannot be empty")

        LOGGER.debug(
            "Emulation request: persona=%s module=%s provider=%s model=%s",
            persona_id,
            module,
            provider_cfg.name,
            model_entry.id,
        )

        result = adapter.chat(model_entry.id, history, **dispatch_options)
        self.append_history(persona_id, history, result.reply)
        return result


# Singleton instance used by routes and callers that prefer module-level access.
engine = CharacterEmulationEngine()

__all__ = ["CharacterEmulationEngine", "engine", "FEATURE_FLAG"]
