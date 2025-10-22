from __future__ import annotations

"""
Helpers for public provider adapters.

These adapters intentionally stay minimal and safe by default: when required
API keys are missing we return dry-run payloads so Studio features can probe
request shapes without sending traffic to third-party services.  Secrets resolve
through :mod:`comfyvn.security.secrets_store`, which keeps credentials encrypted
at rest and records audit events on read.
"""

from typing import Any, Dict, Iterable, Sequence

from comfyvn.security.secrets_store import (
    load_secrets as _load_secrets,
)
from comfyvn.security.secrets_store import (
    provider_secrets as _provider_secrets,
)
from comfyvn.security.secrets_store import (
    resolve_credential as _resolve_credential,
)


def load_secrets() -> Dict[str, Any]:
    """
    Return the merged secrets dictionary (including environment overrides).
    """

    return _load_secrets()


def provider_secrets(provider: str) -> Dict[str, Any]:
    """
    Fetch secrets for *provider* (case-insensitive).  Missing providers return
    an empty mapping.
    """

    return _provider_secrets(provider)


def resolve_credential(
    provider: str,
    *,
    env_keys: Sequence[str] | Iterable[str],
    secret_keys: Sequence[str] | Iterable[str] | None = None,
) -> str:
    """
    Return the first non-empty credential discovered across the supplied
    environment variables or provider-specific secrets.
    """

    return _resolve_credential(provider, env_keys=env_keys, secret_keys=secret_keys)


__all__ = ["load_secrets", "provider_secrets", "resolve_credential"]
