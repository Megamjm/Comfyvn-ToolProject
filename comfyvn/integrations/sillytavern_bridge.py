from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx

from comfyvn.core.settings_manager import SettingsManager

LOGGER = logging.getLogger(__name__)


class SillyTavernBridgeError(RuntimeError):
    """Raised when communication with the SillyTavern exporter fails."""


def _normalize_base(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return "http://127.0.0.1:8000"
    return url.rstrip("/")


def _normalize_plugin(path: str) -> str:
    path = (path or "").strip()
    if not path:
        path = "/api/plugins/comfyvn-data-exporter"
    if not path.startswith("/"):
        path = f"/{path}"
    return path.rstrip("/")


class SillyTavernBridge:
    """HTTP helper that talks to the comfyvn-data-exporter SillyTavern plugin."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        plugin_base: Optional[str] = None,
        token: Optional[str] = None,
        user_id: Optional[str] = None,
        settings: Optional[SettingsManager] = None,
        timeout: float = 30.0,
    ) -> None:
        self.settings = settings or SettingsManager()
        self._load_settings_defaults()
        self.base_url = _normalize_base(
            base_url or self._config.get("base_url", "http://127.0.0.1:8000")
        )
        self.plugin_base = _normalize_plugin(
            plugin_base
            or self._config.get("plugin_base", "/api/plugins/comfyvn-data-exporter")
        )
        self.token = token if token is not None else self._config.get("token")
        self.user_id = user_id if user_id is not None else self._config.get("user_id")
        self.timeout = timeout
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=timeout),
            follow_redirects=True,
        )

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    def _load_settings_defaults(self) -> None:
        cfg = self.settings.load()
        integrations = cfg.get("integrations", {})
        self._config = dict(integrations.get("sillytavern", {}))

    def set_endpoint(
        self,
        *,
        base_url: Optional[str] = None,
        plugin_base: Optional[str] = None,
        token: Optional[str] = None,
        user_id: Optional[str] = None,
        persist: bool = False,
    ) -> None:
        if base_url is not None:
            self.base_url = _normalize_base(base_url)
        if plugin_base is not None:
            self.plugin_base = _normalize_plugin(plugin_base)
        if token is not None:
            self.token = token or None
        if user_id is not None:
            self.user_id = user_id or None
        if persist:
            cfg = self.settings.load()
            integrations = dict(cfg.get("integrations", {}))
            current = dict(integrations.get("sillytavern", {}))
            current.update(
                {
                    "base_url": self.base_url,
                    "plugin_base": self.plugin_base,
                    "token": self.token,
                    "user_id": self.user_id,
                }
            )
            integrations["sillytavern"] = current
            cfg["integrations"] = integrations
            self.settings.save(cfg)

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------
    def close(self) -> None:
        if self._client:
            self._client.close()

    def __del__(self) -> None:  # pragma: no cover - defensive
        try:
            self.close()
        except Exception:
            pass

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _params(
        self, extra: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        effective_user = user_id if user_id is not None else self.user_id
        if effective_user:
            params["user_id"] = effective_user
        if extra:
            params.update(extra)
        return params

    def _url(self, suffix: str = "") -> str:
        suffix = (suffix or "").strip("/")
        if suffix:
            return f"{self.base_url}{self.plugin_base}/{suffix}"
        return f"{self.base_url}{self.plugin_base}"

    def _get(
        self,
        suffix: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            response = self._client.get(
                self._url(suffix),
                headers=self._headers(),
                params=self._params(params, user_id=user_id),
            )
            response.raise_for_status()
            if response.content:
                return response.json()
            return {}
        except Exception as exc:
            raise SillyTavernBridgeError(f"GET {suffix} failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def health(self) -> Dict[str, Any]:
        return self._get("health")

    def get_roots(self, *, user_id: Optional[str] = None) -> Dict[str, Any]:
        result = self._get("roots", user_id=user_id)
        return result

    def get_active(self, *, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Return the active SillyTavern session snapshot."""
        return self._get("active", user_id=user_id)

    # --- Worlds -------------------------------------------------------
    def list_worlds(self, *, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        payload = self._get("worlds", user_id=user_id)
        names: Iterable[str] = payload.get("worlds") or []
        roots = self.get_roots(user_id=user_id)
        world_root = roots.get("worlds")
        entries = []
        for name in names:
            entries.append(
                {
                    "name": name,
                    "path": str(Path(world_root) / name) if world_root else None,
                }
            )
        return entries

    def get_world(self, name: str, *, user_id: Optional[str] = None) -> Dict[str, Any]:
        return self._get(f"worlds/{name}", user_id=user_id)

    def fetch_worlds(self, *, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        worlds: List[Dict[str, Any]] = []
        for entry in self.list_worlds(user_id=user_id):
            name = entry["name"]
            data = self.get_world(name, user_id=user_id)
            worlds.append({"id": name, "data": data, "path": entry.get("path")})
        return worlds

    def download_world(
        self, world_id: str, save_path: str | Path, *, user_id: Optional[str] = None
    ) -> Optional[str]:
        try:
            data = self.get_world(world_id, user_id=user_id)
            destination = Path(save_path)
            destination.mkdir(parents=True, exist_ok=True)
            path = destination / world_id
            if not path.name.lower().endswith(".json"):
                path = path.with_suffix(".json")
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            LOGGER.debug("Downloaded SillyTavern world %s → %s", world_id, path)
            return str(path)
        except SillyTavernBridgeError:
            raise
        except Exception as exc:
            raise SillyTavernBridgeError(
                f"Failed to download world {world_id}: {exc}"
            ) from exc

    # --- Characters ---------------------------------------------------
    def list_characters(self, *, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        payload = self._get("characters", user_id=user_id)
        names: Iterable[str] = payload.get("characters") or []
        roots = self.get_roots(user_id=user_id)
        char_root = roots.get("characters")
        return [
            {"name": name, "path": str(Path(char_root) / name) if char_root else None}
            for name in names
        ]

    def get_character(
        self, name: str, *, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._get(f"characters/{name}", user_id=user_id)

    # --- Personas -----------------------------------------------------
    def list_personas(self, *, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        payload = self._get("personas", user_id=user_id)
        names: Iterable[str] = payload.get("personas") or []
        roots = self.get_roots(user_id=user_id)
        persona_root = roots.get("personas")
        return [
            {
                "name": name,
                "path": str(Path(persona_root) / name) if persona_root else None,
            }
            for name in names
        ]

    def get_persona(
        self, name: str, *, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._get(f"personas/{name}", user_id=user_id)

    # --- Active snapshot ----------------------------------------------
    def get_active_snapshot(self, *, user_id: Optional[str] = None) -> Dict[str, Any]:
        return self._get("active", user_id=user_id)


__all__ = ["SillyTavernBridge", "SillyTavernBridgeError"]
