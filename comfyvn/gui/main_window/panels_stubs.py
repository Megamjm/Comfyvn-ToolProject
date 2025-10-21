from PySide6.QtGui import QAction


class PanelsStubsMixin:
    """Safe fallbacks for missing panels; avoids crashes during development."""

    def __getattr__(self, name):
        if name.startswith("open_") or name.startswith("toggle_"):

            def _noop(*args, **kwargs):
                print(f"[PanelsStub] âš ï¸ Called undefined panel: {name}")

            return _noop
        raise AttributeError(name)
