"""FastAPI router package for ComfyVN server modules.

The package intentionally avoids importing optional GUI dependencies at
import time so that API-only environments do not fail when these modules
are missing.  Individual routers import their own requirements lazily.
"""

__all__ = []
