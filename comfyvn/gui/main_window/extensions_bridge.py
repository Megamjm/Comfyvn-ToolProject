from PySide6.QtGui import QAction

# comfyvn/gui/main_window/extensions_bridge.py  [OptionA-088]
import importlib, pkgutil

class ExtensionsBridgeMixin:
    def _init_extensions_bridge(self):
        self.extensions = []
        base = "comfyvn.extensions"
        try:
            pkg = importlib.import_module(base)
            for m in pkgutil.iter_modules(pkg.__path__, prefix=base + "."):
                try:
                    mod = importlib.import_module(m.name)
                    if hasattr(mod, "load_extension"):
                        mod.load_extension(self)
                        self.extensions.append(m.name)
                except Exception as e:
                    print(f"[Extensions] {m.name}: {e}")
        except Exception as e:
            print(f"[Extensions] {e}")