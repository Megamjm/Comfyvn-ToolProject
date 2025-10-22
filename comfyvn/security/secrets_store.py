from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
)

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError as exc:  # pragma: no cover - enforced via requirements
    raise RuntimeError(
        "cryptography>=41 is required for comfyvn.security.secrets_store"
    ) from exc

LOGGER = logging.getLogger(__name__)
AUDIT_LOGGER = logging.getLogger("comfyvn.security.secrets")

DEFAULT_SECRET_PATHS: Tuple[Path, ...] = (
    Path("config/comfyvn.secrets.json"),
    Path("comfyvn.secrets.json"),
)
DEFAULT_KEY_PATHS: Tuple[Path, ...] = (
    Path("config/comfyvn.secrets.key"),
    Path("comfyvn.secrets.key"),
)
DEFAULT_ENV_PREFIX = "COMFYVN_SECRET_"
DEFAULT_KEY_ENV = "COMFYVN_SECRETS_KEY"
DEFAULT_SECRET_KEYS: Tuple[str, ...] = ("api_key", "token", "key", "secret")

_MODDER_EVENT_MAP = {
    "secrets.read": "on_security_secret_read",
    "secrets.key.rotated": "on_security_key_rotated",
}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _key_fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


class SecretStoreError(RuntimeError):
    """Raised when the secrets store cannot satisfy a request."""


def _emit_modder_event(event: str, payload: Dict[str, Any]) -> None:
    hook = _MODDER_EVENT_MAP.get(event)
    if not hook:
        return
    sanitized = {key: value for key, value in payload.items() if key not in {"event"}}
    sanitized.setdefault("timestamp", payload.get("timestamp"))
    try:
        from comfyvn.core import modder_hooks
    except Exception:
        return
    try:
        modder_hooks.emit(hook, sanitized)
    except Exception:
        LOGGER.debug("Failed to emit modder hook %s", hook, exc_info=True)


class SecretStore:
    """
    Encrypted secrets store with environment overrides and key rotation.

    The store keeps secrets encrypted at rest using Fernet (AES128 + HMAC).
    Secrets are persisted in ``config/comfyvn.secrets.json`` (git-ignored) and
    the encryption key resolves from ``COMFYVN_SECRETS_KEY`` or companion
    ``*.secrets.key`` files.  Environment overrides allow modders to inject
    temporary credentials without mutating on-disk secrets.
    """

    def __init__(
        self,
        *,
        data_paths: Sequence[Path | str] | None = None,
        key_paths: Sequence[Path | str] | None = None,
        key_env: str = DEFAULT_KEY_ENV,
        env_prefix: str = DEFAULT_ENV_PREFIX,
        persist_keys: bool = True,
    ) -> None:
        self._data_paths: Tuple[Path, ...] = tuple(
            Path(p) for p in (data_paths or DEFAULT_SECRET_PATHS)
        )
        self._key_paths: Tuple[Path, ...] = tuple(
            Path(p) for p in (key_paths or DEFAULT_KEY_PATHS)
        )
        if not self._data_paths:
            raise ValueError("SecretStore requires at least one data path")
        if not self._key_paths:
            raise ValueError("SecretStore requires at least one key path")
        self.key_env = key_env
        self.env_prefix = env_prefix
        self.persist_keys = persist_keys
        self._cache: Optional[Dict[str, Any]] = None
        self._key: Optional[str] = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ paths
    def _target_path(self) -> Path:
        """Return the path used when persisting encrypted secrets."""
        return self._data_paths[0]

    def _existing_path(self) -> Optional[Path]:
        for candidate in self._data_paths:
            if candidate.exists():
                return candidate
        return None

    def _existing_key_path(self) -> Optional[Path]:
        for candidate in self._key_paths:
            if candidate.exists():
                return candidate
        return None

    # ------------------------------------------------------------------- keys
    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode("utf-8")

    def _write_key(self, key: str) -> None:
        if not self.persist_keys or os.getenv(self.key_env):
            return
        path = self._key_paths[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(key.strip(), encoding="utf-8")

    def _load_key(self, *, ensure: bool = False) -> str:
        if self._key:
            return self._key

        env_value = os.getenv(self.key_env)
        if env_value and env_value.strip():
            self._key = env_value.strip()
            return self._key

        key_path = self._existing_key_path()
        if key_path:
            key = key_path.read_text(encoding="utf-8").strip()
            if key:
                self._key = key
                return self._key

        if ensure:
            key = self.generate_key()
            self._write_key(key)
            self._key = key
            AUDIT_LOGGER.info(
                json.dumps(
                    {
                        "event": "secrets.key.generated",
                        "timestamp": _utc_timestamp(),
                        "fingerprint": _key_fingerprint(key),
                        "destination": str(self._key_paths[0]),
                    }
                )
            )
            return self._key

        raise SecretStoreError(
            "Secrets key not configured. Export COMFYVN_SECRETS_KEY or create "
            "config/comfyvn.secrets.key."
        )

    def rotate_key(self, new_key: Optional[str] = None) -> str:
        with self._lock:
            data = self.load(refresh=True)
            key = (new_key or self.generate_key()).strip()
            if not key:
                raise SecretStoreError("New key cannot be empty")
            self._key = key
            self._write_key(key)
            self._write_encrypted(data, key)
            AUDIT_LOGGER.info(
                json.dumps(
                    {
                        "event": "secrets.key.rotated",
                        "timestamp": _utc_timestamp(),
                        "fingerprint": _key_fingerprint(key),
                        "providers": sorted(data.keys()),
                    }
                )
            )
            return key

    # ------------------------------------------------------------------ audit
    def _audit(self, event: str, **fields: Any) -> None:
        payload = {"event": event, "timestamp": _utc_timestamp()}
        payload.update(fields)
        AUDIT_LOGGER.info(json.dumps(payload))
        _emit_modder_event(event, payload)

    # --------------------------------------------------------------- persistence
    def _fernet(self, key: Optional[str] = None) -> Fernet:
        material = (key or self._load_key()).encode("utf-8")
        return Fernet(material)

    def _write_encrypted(self, payload: Mapping[str, Any], key: Optional[str] = None):
        data = dict(payload)
        ciphertext = self._fernet(key).encrypt(
            json.dumps(data, ensure_ascii=False).encode("utf-8")
        )
        envelope = {
            "version": 1,
            "algorithm": "fernet",
            "ciphertext": ciphertext.decode("utf-8"),
            "updated_at": _utc_timestamp(),
            "fingerprint": _key_fingerprint(self._load_key()),
        }

        target = self._target_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_suffix(target.suffix + ".tmp")
        tmp_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        tmp_path.replace(target)
        self._cache = dict(data)

    def _decrypt_payload(self, envelope: Mapping[str, Any]) -> Dict[str, Any]:
        ciphertext = envelope.get("ciphertext")
        if not isinstance(ciphertext, str) or not ciphertext.strip():
            raise SecretStoreError("Encrypted secrets missing ciphertext")
        try:
            plaintext = self._fernet().decrypt(ciphertext.encode("utf-8"))
        except InvalidToken as exc:
            self._audit("secrets.decrypt.failed", error=str(exc))
            raise SecretStoreError("Failed to decrypt secrets payload") from exc
        try:
            data = json.loads(plaintext.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SecretStoreError("Secrets payload is not valid JSON") from exc
        if not isinstance(data, dict):
            raise SecretStoreError("Secrets payload must be a JSON object")
        return data

    def load(self, *, refresh: bool = False) -> Dict[str, Any]:
        with self._lock:
            if self._cache is not None and not refresh:
                return dict(self._cache)

            path = self._existing_path()
            if path is None:
                self._cache = {}
                return {}

            try:
                raw = path.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                self._cache = {}
                return {}
            if not raw:
                self._cache = {}
                return {}

            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SecretStoreError("Secrets file is not valid JSON") from exc

            if isinstance(parsed, dict) and "ciphertext" in parsed:
                data = self._decrypt_payload(parsed)
                self._cache = dict(data)
                return dict(data)

            if isinstance(parsed, dict):
                # Plain-text secrets detected; upgrade in-place.
                LOGGER.warning(
                    "Plain-text secrets detected at %s; upgrading to encrypted format",
                    path,
                )
                self._write_encrypted(parsed, self._load_key(ensure=True))
                self._audit(
                    "secrets.upgraded",
                    path=str(path),
                    providers=sorted(parsed.keys()),
                )
                return dict(parsed)

            raise SecretStoreError("Secrets file must contain an object payload")

    # ----------------------------------------------------------------- mutation
    def write(self, payload: Mapping[str, Any]) -> None:
        if not isinstance(payload, Mapping):
            raise SecretStoreError("Secrets payload must be a mapping")
        with self._lock:
            data = {
                str(provider): self._normalize_entry(values)
                for provider, values in payload.items()
                if isinstance(values, Mapping)
            }
            self._write_encrypted(data, self._load_key(ensure=True))
            self._audit("secrets.write", providers=sorted(data.keys()))

    def update(self, provider: str, values: Mapping[str, Any]) -> None:
        provider_key = str(provider).strip()
        if not provider_key:
            raise SecretStoreError("Provider name cannot be empty")
        if not isinstance(values, Mapping):
            raise SecretStoreError("Provider secrets must be a mapping")
        with self._lock:
            current = self.load()
            current[provider_key] = self._normalize_entry(values)
            self._write_encrypted(current, self._load_key(ensure=True))
            self._audit("secrets.provider.update", provider=provider_key)

    @staticmethod
    def _normalize_entry(values: Mapping[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in values.items():
            if value is None:
                continue
            normalized[str(key)] = value
        return normalized

    # ------------------------------------------------------------- lookup utils
    def _match_provider(
        self, provider: str, payload: Mapping[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        canonical = provider.strip().lower()
        for key, value in payload.items():
            if isinstance(value, Mapping) and key.lower() == canonical:
                return key, dict(value)
        return provider, {}

    def _env_overrides(self, provider: str) -> Dict[str, str]:
        prefix = f"{self.env_prefix}{provider.strip().upper()}_"
        overrides: Dict[str, str] = {}
        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue
            field = key[len(prefix) :].lower()
            if not field:
                continue
            if value is None:
                continue
            val = str(value).strip()
            if val:
                overrides[field] = val
        return overrides

    # ---------------------------------------------------------------- retrieval
    def get(self, provider: str) -> Dict[str, Any]:
        if not provider or not str(provider).strip():
            return {}
        data = self.load()
        _matched_key, entry = self._match_provider(provider, data)
        overrides = self._env_overrides(provider)
        merged = dict(entry)
        if overrides:
            merged.update(overrides)
        self._audit(
            "secrets.read",
            provider=str(provider),
            keys=sorted(merged.keys()),
            overrides=sorted(overrides.keys()),
            present=bool(merged),
        )
        return merged

    def load_with_overrides(self) -> Dict[str, Any]:
        data = self.load()
        result: Dict[str, Any] = {}
        for provider, values in data.items():
            merged = dict(values) if isinstance(values, Mapping) else {}
            overrides = self._env_overrides(provider)
            if overrides:
                merged.update(overrides)
            result[provider] = merged
        return result

    def describe(self, provider: str) -> Dict[str, Any]:
        if not provider or not str(provider).strip():
            return {
                "provider": "",
                "stored_keys": [],
                "override_keys": [],
                "present": False,
            }
        data = self.load()
        matched_key, entry = self._match_provider(provider, data)
        overrides = self._env_overrides(provider)
        stored_keys = sorted(entry.keys())
        override_keys = sorted(overrides.keys())
        return {
            "provider": matched_key,
            "stored_keys": stored_keys,
            "override_keys": override_keys,
            "present": bool(stored_keys or override_keys),
        }

    def describe_all(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        data = self.load()
        for provider, values in data.items():
            if isinstance(values, Mapping):
                stored_keys = sorted(values.keys())
            else:
                stored_keys = []
            override_keys = sorted(self._env_overrides(provider).keys())
            entries.append(
                {
                    "provider": provider,
                    "stored_keys": stored_keys,
                    "override_keys": override_keys,
                    "present": bool(stored_keys or override_keys),
                }
            )
        return entries

    def resolve(
        self,
        provider: str,
        *,
        env_keys: Sequence[str] | Iterable[str],
        secret_keys: Sequence[str] | Iterable[str] | None = None,
    ) -> str:
        for candidate in env_keys:
            if not candidate:
                continue
            value = os.getenv(str(candidate))
            if value and str(value).strip():
                self._audit(
                    "secrets.resolve",
                    provider=str(provider),
                    source="env",
                    key=str(candidate),
                )
                return str(value).strip()

        secrets = self.get(provider)
        combined_keys = list(secret_keys or []) or [str(k) for k in env_keys]
        for fallback in DEFAULT_SECRET_KEYS:
            if fallback not in combined_keys:
                combined_keys.append(fallback)
        for candidate in combined_keys:
            value = secrets.get(candidate)
            if isinstance(value, str) and value.strip():
                self._audit(
                    "secrets.resolve",
                    provider=str(provider),
                    source="store",
                    key=candidate,
                )
                return value.strip()
        return ""


_DEFAULT_STORE: Optional[SecretStore] = None


def default_store() -> SecretStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = SecretStore()
    return _DEFAULT_STORE


def load_secrets() -> Dict[str, Any]:
    return default_store().load_with_overrides()


def provider_secrets(provider: str) -> Dict[str, Any]:
    return default_store().get(provider)


def resolve_credential(
    provider: str,
    *,
    env_keys: Sequence[str] | Iterable[str],
    secret_keys: Sequence[str] | Iterable[str] | None = None,
) -> str:
    return default_store().resolve(provider, env_keys=env_keys, secret_keys=secret_keys)


__all__ = [
    "SecretStore",
    "SecretStoreError",
    "default_store",
    "load_secrets",
    "provider_secrets",
    "resolve_credential",
]
