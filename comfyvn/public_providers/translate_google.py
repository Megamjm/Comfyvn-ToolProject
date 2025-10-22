from __future__ import annotations

"""
Google Translate adapter stub.

When API credentials are missing we simply echo the input so toolchains can
exercise data flows without invoking the external service.
"""

from typing import Iterable, List, Mapping

from . import provider_secrets


def translate(
    texts: Iterable[str],
    source: str,
    target: str,
    cfg: Mapping[str, object] | None = None,
) -> List[str]:
    """
    Return translated strings.  Without credentials this is a dry-run that
    echoes the original texts.
    """

    config = dict(provider_secrets("google_translate"))
    if cfg:
        config.update(dict(cfg))
    api_key = str(config.get("api_key") or "").strip()

    # TODO: wire actual Translate API when keys are available.
    if not api_key:
        return list(texts)

    return list(texts)


__all__ = ["translate"]
