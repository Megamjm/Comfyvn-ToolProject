"""
Expose VN pack import routes through the modules auto-loader.
"""

from __future__ import annotations

from comfyvn.server.routes.import_vnpack import router

__all__ = ["router"]
