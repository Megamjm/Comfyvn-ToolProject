from PySide6.QtGui import QAction


# comfyvn/core/extension_runtime.py (autofixed)
class ExtensionRuntime:
    def __init__(self):
        self.loaded = []

    def discover(self):
        return []

    def load_all(self, ctx=None):
        return []

    def unload_all(self, ctx=None):
        return []


runtime = ExtensionRuntime()
