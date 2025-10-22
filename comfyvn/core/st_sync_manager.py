import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
# comfyvn/modules/st_sync_manager.py
# ⚙️ 3. Server Core Production Chat — SillyTavern Generic Sync Manager

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from comfyvn.config import feature_flags
from comfyvn.integrations.sillytavern_bridge import (
    SillyTavernBridge,
    SillyTavernBridgeError,
)

SYNC_DIR = "./data/st_sync"
ARCHIVE_DIR = os.path.join(SYNC_DIR, "archive")
META_FILE = os.path.join(SYNC_DIR, "meta.json")

# Ensure directories exist
os.makedirs(SYNC_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)


def _compute_hash(obj: Any) -> str:
    """Compute stable hash of JSON-serializable object."""
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _load_meta() -> Dict[str, Any]:
    if not os.path.exists(META_FILE):
        return {}
    with open(META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_meta(meta: Dict[str, Any]):
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


class STSyncManager:
    """
    Handles pulling / comparing / archiving of SillyTavern assets:
    worlds, lorebooks, characters, personas, chats.
    """

    def __init__(self, base_url: str, *, user_id: Optional[str] = None):
        """
        base_url: base endpoint for ST REST export API, e.g. "http://127.0.0.1:8000"
        Assumes endpoints like /api/world/export, /api/character/export, etc.
        """
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.meta = (
            _load_meta()
        )  # e.g. {"worlds": {key: hash,...}, "characters": {...}}
        self.bridge: SillyTavernBridge | None = None
        self._bridge_available = False
        self._bridge_checked = False
        self._fallback_warned = False
        self._disabled_reason = ""
        self._feature_enabled = False
        self._refresh_feature_flag()

    def _pull_asset(
        self, asset_type: str, key: str, endpoint_suffix: str
    ) -> Dict[str, Any]:
        """
        Pull JSON from ST for a given asset.
        endpoint_suffix is like "world/export" or "character/export".
        """
        self._refresh_feature_flag()
        if not self._feature_enabled:
            return {"status": "disabled", "error": self._disabled_reason}
        if self._bridge_available:
            if not self._bridge_checked:
                try:
                    self.bridge.health()
                except SillyTavernBridgeError as exc:
                    logger.warning("SillyTavern plugin health check failed: %s", exc)
                    self._bridge_available = False
                finally:
                    self._bridge_checked = True

        if self._bridge_available:
            try:
                if asset_type == "worlds":
                    data = self.bridge.get_world(key, user_id=self.user_id)
                elif asset_type == "characters":
                    data = self.bridge.get_character(key, user_id=self.user_id)
                elif asset_type == "personas":
                    data = self.bridge.get_persona(key, user_id=self.user_id)
                else:
                    # fall back for unsupported asset types
                    raise SillyTavernBridgeError("unsupported asset type")
                return {"status": "ok", "data": data}
            except SillyTavernBridgeError as exc:
                if not self._fallback_warned:
                    logger.warning(
                        "Falling back to legacy SillyTavern endpoints: %s", exc
                    )
                    self._fallback_warned = True
                self._bridge_available = False

        # Legacy fallback: expect old export endpoints.
        url = f"{self.base_url}/api/{endpoint_suffix}"
        payload = {"key": key}
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            return {"status": "ok", "data": resp.json()}
        except Exception as e:
            return {"status": "fail", "error": str(e)}

    def sync_asset(
        self, asset_type: str, key: str, endpoint_suffix: str
    ) -> Dict[str, Any]:
        """
        Sync a single asset: compare, archive, update meta.
        Returns dict with keys: status: ("unchanged","updated","new","error"), details.
        """
        pull = self._pull_asset(asset_type, key, endpoint_suffix)
        status = pull.get("status")
        if status == "disabled":
            return {"status": "error", "error": pull.get("error")}
        if status != "ok":
            return {"status": "error", "error": pull.get("error")}

        data = pull["data"]
        new_hash = _compute_hash(data)

        # Prepare meta structure
        if asset_type not in self.meta:
            self.meta[asset_type] = {}

        prev_hash = self.meta[asset_type].get(key)

        # if no previous record
        if prev_hash is None:
            # first time
            self._archive_blob(asset_type, key, data)
            self.meta[asset_type][key] = new_hash
            _save_meta(self.meta)
            return {"status": "new", "hash": new_hash}

        if prev_hash == new_hash:
            return {"status": "unchanged", "hash": new_hash}

        # else changed: archive old + save new
        self._archive_blob(asset_type, key, data)
        self.meta[asset_type][key] = new_hash
        _save_meta(self.meta)
        return {"status": "updated", "hash": new_hash}

    def _archive_blob(self, asset_type: str, key: str, data: Any):
        """
        Save a backup file of the blob, with timestamp.
        Path: archive/{asset_type}_{key}_{ts}.json
        """
        ts = time.strftime("%Y%m%d_%H%M%S")
        safe_key = key.replace("/", "_").replace(" ", "_")
        fname = f"{asset_type}_{safe_key}_{ts}.json"
        path = os.path.join(ARCHIVE_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def query_asset(self, asset_type: str, key: str) -> Dict[str, Any]:
        """
        Return the last pulled blob and metadata (hash, maybe last updated).
        """
        rec = self.meta.get(asset_type, {}).get(key)
        blob = None
        # try load latest archive
        # scanning archive files for matching asset_type & key, newest first
        candidates = [
            f
            for f in os.listdir(ARCHIVE_DIR)
            if f.startswith(f"{asset_type}_{key}_") and f.endswith(".json")
        ]
        if candidates:
            candidates.sort(reverse=True)
            with open(
                os.path.join(ARCHIVE_DIR, candidates[0]), "r", encoding="utf-8"
            ) as f:
                blob = json.load(f)
        return {"key": key, "asset_type": asset_type, "hash": rec, "blob": blob}

    def sync_many(
        self, asset_type: str, keys: List[str], endpoint_suffix: str
    ) -> Dict[str, Any]:
        results = {}
        for k in keys:
            results[k] = self.sync_asset(asset_type, k, endpoint_suffix)
        return results

    def _refresh_feature_flag(self) -> None:
        enabled = feature_flags.is_enabled("enable_sillytavern_bridge")
        if enabled and not self._feature_enabled:
            try:
                self.bridge = SillyTavernBridge(
                    base_url=self.base_url, user_id=self.user_id
                )
                self._feature_enabled = True
                self._bridge_available = True
                self._bridge_checked = False
                self._disabled_reason = ""
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("SillyTavern bridge unavailable: %s", exc)
                self.bridge = None
                self._feature_enabled = False
                self._bridge_available = False
                self._bridge_checked = True
                self._disabled_reason = f"SillyTavern bridge unavailable: {exc}"
        elif not enabled and self._feature_enabled:
            self._feature_enabled = False
            self._bridge_available = False
            self._bridge_checked = True
            self.bridge = None
            self._disabled_reason = "SillyTavern bridge disabled via feature flag."
