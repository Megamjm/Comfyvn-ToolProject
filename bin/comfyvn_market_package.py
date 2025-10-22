#!/usr/bin/env python3
"""CLI entrypoint for the ComfyVN extension packager."""

from __future__ import annotations

from comfyvn.market.packaging import main

if __name__ == "__main__":  # pragma: no cover - CLI shim
    raise SystemExit(main())
