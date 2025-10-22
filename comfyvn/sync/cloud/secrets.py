from __future__ import annotations

"""
Encrypted secrets vault used by cloud sync providers.

Secrets are stored inside ``config/comfyvn.secrets.json`` in an encrypted
envelope.  The payload is encrypted with AES-GCM using a key derived from a
user-supplied passphrase via PBKDF2-HMAC-SHA256.
"""

import base64
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, MutableMapping, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class SecretsVaultError(RuntimeError):
    """Raised when the secrets vault cannot be accessed or unlocked."""


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(slots=True)
class VaultEnvelope:
    version: int
    kdf: Dict[str, Any]
    cipher: Dict[str, Any]
    updated_at: str
    backups: list[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "kdf": self.kdf,
            "cipher": self.cipher,
            "updated_at": self.updated_at,
            "backups": self.backups,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "VaultEnvelope":
        return cls(
            version=int(data.get("version", 1)),
            kdf=dict(data.get("kdf", {})),  # type: ignore[arg-type]
            cipher=dict(data.get("cipher", {})),  # type: ignore[arg-type]
            updated_at=str(data.get("updated_at", "")),
            backups=list(data.get("backups", [])),  # type: ignore[arg-type]
        )


class SecretsVault:
    """
    Lightweight encrypted secrets store.

    Parameters
    ----------
    path:
        Location on disk for the encrypted vault.
    env_var:
        Environment variable that supplies the passphrase when API callers do
        not provide one explicitly.
    max_backups:
        Number of historical encrypted payloads to retain inside the envelope.
    """

    def __init__(
        self,
        path: str | os.PathLike[str] = "config/comfyvn.secrets.json",
        *,
        env_var: str = "COMFYVN_SECRETS_KEY",
        max_backups: int = 5,
        iterations: int = 390_000,
    ) -> None:
        self.path = Path(path)
        self.env_var = env_var
        self.max_backups = max_backups
        self.iterations = iterations

    # -- Public API -----------------------------------------------------------------

    def unlock(self, *, passphrase: str | None = None) -> Dict[str, Any]:
        envelope = self._read_envelope()
        if envelope is None:
            raise SecretsVaultError("vault not initialised - call store() first")

        key = self._derive_key(passphrase)
        plaintext = self._decrypt(envelope, key)
        try:
            payload = json.loads(plaintext.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SecretsVaultError(f"invalid payload in vault: {exc}") from exc
        if not isinstance(payload, dict):
            raise SecretsVaultError("vault payload must be a JSON object")
        logger.info(
            "Secrets vault unlocked",
            extra={"secrets_path": str(self.path), "updated_at": envelope.updated_at},
        )
        return payload

    def store(
        self, payload: Mapping[str, Any], *, passphrase: str | None = None
    ) -> None:
        data = json.dumps(payload, indent=2, default=str).encode("utf-8")
        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = self._derive_key(passphrase, salt=salt)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)

        kdf: Dict[str, Any] = {
            "name": "pbkdf2-hmac-sha256",
            "iterations": self.iterations,
            "salt": _b64encode(salt),
        }
        cipher: Dict[str, Any] = {
            "name": "aes-gcm",
            "nonce": _b64encode(nonce),
            "ciphertext": _b64encode(ciphertext),
        }

        previous = self._read_envelope()
        backups: list[Dict[str, Any]] = []
        if previous is not None:
            trimmed = dict(previous.to_dict())
            trimmed.pop("backups", None)
            trimmed["archived_at"] = _now_iso()
            backups.append(trimmed)
            backups.extend(previous.backups)
        if len(backups) > self.max_backups:
            backups = backups[: self.max_backups]

        envelope = VaultEnvelope(
            version=1,
            kdf=kdf,
            cipher=cipher,
            updated_at=_now_iso(),
            backups=backups,
        )
        self._write_envelope(envelope)
        logger.info(
            "Secrets vault updated",
            extra={
                "secrets_path": str(self.path),
                "backups_retained": len(envelope.backups),
            },
        )

    def get(
        self, key: str, *, passphrase: str | None = None, default: Any | None = None
    ) -> Any:
        payload = self.unlock(passphrase=passphrase)
        return payload.get(key, default)

    def set(self, key: str, value: Any, *, passphrase: str | None = None) -> None:
        payload = self.unlock(passphrase=passphrase)
        payload[key] = value
        self.store(payload, passphrase=passphrase)

    # -- Internals ------------------------------------------------------------------

    def _derive_key(
        self, passphrase: str | None, *, salt: bytes | None = None
    ) -> bytes:
        actual_passphrase = passphrase or os.getenv(self.env_var)
        if not actual_passphrase:
            raise SecretsVaultError(
                f"secrets key not provided (passphrase argument or ${self.env_var})"
            )

        envelope = self._read_envelope()
        if salt is None:
            if envelope is None:
                raise SecretsVaultError("cannot derive key without existing salt")
            salt_b64 = envelope.kdf.get("salt")
            if not isinstance(salt_b64, str):
                raise SecretsVaultError("salt missing from secrets envelope")
            salt = _b64decode(salt_b64)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.iterations,
        )
        key = kdf.derive(actual_passphrase.encode("utf-8"))
        return key

    def _read_envelope(self) -> VaultEnvelope | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SecretsVaultError(f"invalid secrets envelope: {exc}") from exc
        if not isinstance(data, Mapping):
            raise SecretsVaultError("secrets envelope must be a JSON object")
        return VaultEnvelope.from_mapping(data)

    def _write_envelope(self, envelope: VaultEnvelope) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(envelope.to_dict(), indent=2), encoding="utf-8")
        tmp_path.replace(self.path)

    def _decrypt(self, envelope: VaultEnvelope, key: bytes) -> bytes:
        nonce_raw = envelope.cipher.get("nonce")
        ciphertext_raw = envelope.cipher.get("ciphertext")
        if not isinstance(nonce_raw, str) or not isinstance(ciphertext_raw, str):
            raise SecretsVaultError("ciphertext missing from vault envelope")

        nonce = _b64decode(nonce_raw)
        ciphertext = _b64decode(ciphertext_raw)
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as exc:  # pragma: no cover - cryptography raises generic
            raise SecretsVaultError("could not decrypt secrets vault") from exc
        return plaintext


__all__ = ["SecretsVault", "SecretsVaultError"]
