# comfyvn/gui/__init__.py
# [🎨 GUI Code Production Chat | Phase 3.2 Meta]
"""
ComfyVN GUI package.

This package contains the PySide6-based GUI surfaces:
- main_window: top-level window and status/polling
- settings_ui: configuration panel
- asset_browser: asset grid, render dispatch, job polling
- playground_ui: scene composer + LM Studio + server planner
- components: reusable widgets (progress overlay, dialogs, task manager dock)
"""

__version__ = "v0.3-dev (Phase 3.2)"
__maintainer__ = "ComfyVN Team"
__license__ = "MIT"

# Export common entry points
from .main_window import MainWindow  # noqa: E402
# Optional: convenience re-exports for frequent components
try:
    from .components.progress_overlay import ProgressOverlay  # noqa: E402
    from .components.dialog_helpers import info, error, confirm  # noqa: E402
except Exception:
    # Components may not be imported during certain tooling steps
    pass


def get_version() -> str:
    """Return GUI package version string."""
    return __version__  # [🎨 GUI Code Production Chat]
# [🎨 GUI Code Production Chat | Phase 3.2 Meta]