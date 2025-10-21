"""Utility entrypoint that keeps local integrations in sync.

Currently this script focuses on the SillyTavern bridge extension.  It loads
the optional extension sync helper defensively so missing optional assets do
not cause the entire install process to fail.
"""

from __future__ import annotations

import importlib
import logging
import sys
from typing import Any, Sequence

LOGGER = logging.getLogger(__name__)
EXTENSION_SYNC_MODULE = "comfyvn.modules.st_bridge.extension_sync"


def _load_extension_sync() -> tuple[Any | None, str | None]:
    """Attempt to import the SillyTavern extension sync helper."""
    try:
        module = importlib.import_module(EXTENSION_SYNC_MODULE)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing.startswith("comfyvn.modules.st_bridge"):
            return None, (
                "SillyTavern bridge assets are not bundled with this build. "
                "Pull the optional 'SillyTavern Extension' directory to enable sync."
            )
        raise
    return module, None


def run_extension_sync(argv: Sequence[str]) -> dict[str, object]:
    module, warning = _load_extension_sync()
    if module is None:
        message = warning or "SillyTavern bridge module unavailable."
        print(f"[WARN] {message}")
        return {"ok": False, "message": message}

    main = getattr(module, "main", None)
    if not callable(main):
        message = "SillyTavern bridge module is missing a callable main() entrypoint."
        print(f"[WARN] {message}")
        return {"ok": False, "message": message}

    try:
        summary = main(argv)
    except NotImplementedError as exc:
        message = f"SillyTavern bridge extension sync not implemented: {exc}"
        print(f"[WARN] {message}")
        return {"ok": False, "message": message}

    return {"ok": True, "summary": summary}


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if argv is None:
        argv = sys.argv[1:]

    result = run_extension_sync(argv)
    if result.get("ok"):
        summary = result.get("summary")
        if isinstance(summary, dict):
            created = summary.get("created", 0)
            updated = summary.get("updated", 0)
            skipped = summary.get("skipped", 0)
            destination = summary.get("destination", "")
            print(
                "Copy summary → "
                f"created={created}, updated={updated}, skipped={skipped}, "
                f"dest={destination}"
            )
        return 0

    print("Install manager completed with warnings; see messages above.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

