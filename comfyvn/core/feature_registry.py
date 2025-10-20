from PySide6.QtGui import QAction
# comfyvn/core/feature_registry.py
# [COMFYVN Architect | v0.8.3s2 | this chat]
from comfyvn.core.log_bus import log
FEATURES = {"core": [], "extension": []}
def register_feature(defn: dict):
    cat = defn.get("category", "extension")
    FEATURES.setdefault(cat, []).append(defn)
    log.debug(f"Feature registered: {defn.get('id')} ({cat})")
def list_features(): return FEATURES