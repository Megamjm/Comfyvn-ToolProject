from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
)

import httpx

if TYPE_CHECKING:  # pragma: no cover - typing imports only
    from comfyvn.bridge.comfy import RenderResult

LOGGER = logging.getLogger(__name__)


def _timestamp() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _coerce_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        images = value.get("images")
        if isinstance(images, list):
            return images
    return []


def _candidate_key(node_id: Any, entry: Dict[str, Any]) -> str:
    filename = entry.get("filename") or entry.get("name") or ""
    subfolder = entry.get("subfolder") or entry.get("folder") or ""
    typ = entry.get("type") or entry.get("category") or "output"
    return f"{node_id}:{subfolder}:{filename}:{typ}"


@dataclass(slots=True)
class PreviewCollector:
    """Capture progressive previews from ComfyUI history polling."""

    base_dir: Path
    notifier: Optional[Callable[[Dict[str, Any]], Optional[Awaitable[None]]]] = None
    include_types: Iterable[str] = field(
        default_factory=lambda: ("preview", "output", "temp")
    )
    max_items: int = 48
    _seen: Set[str] = field(default_factory=set, init=False, repr=False)
    _manifest: List[Dict[str, Any]] = field(
        default_factory=list, init=False, repr=False
    )
    _events_path: Path = field(init=False, repr=False)
    _manifest_path: Path = field(init=False, repr=False)
    _lock: asyncio.Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.base_dir = self.base_dir.expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self.base_dir / "events.jsonl"
        self._manifest_path = self.base_dir / "manifest.json"
        self._lock = asyncio.Lock()

    async def collect(
        self,
        client: httpx.AsyncClient,
        record: Dict[str, Any],
        *,
        prompt_id: str,
        base_url: str,
    ) -> None:
        """Inspect history record and download unseen preview artifacts."""
        outputs = record.get("outputs") or {}
        candidates: List[Tuple[str, Dict[str, Any]]] = []

        async with self._lock:
            for node_id, node_outputs in outputs.items():
                entries = _coerce_list(node_outputs)
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    filename = entry.get("filename")
                    if not filename:
                        continue
                    key = _candidate_key(node_id, entry)
                    if key in self._seen:
                        continue
                    entry_type = str(entry.get("type") or entry.get("category") or "")
                    if self.include_types and entry_type:
                        lowered = entry_type.lower()
                        if lowered not in {typ.lower() for typ in self.include_types}:
                            continue
                    self._seen.add(key)
                    candidates.append((str(node_id), dict(entry)))

        for node_id, entry in candidates:
            await self._save_preview(
                client,
                node_id=node_id,
                entry=entry,
                prompt_id=prompt_id,
                base_url=base_url,
            )

    async def _save_preview(
        self,
        client: httpx.AsyncClient,
        *,
        node_id: str,
        entry: Dict[str, Any],
        prompt_id: str,
        base_url: str,
    ) -> None:
        filename = str(entry.get("filename") or "")
        if not filename:
            return
        params = {
            "filename": filename,
            "subfolder": entry.get("subfolder") or "",
            "type": entry.get("type") or entry.get("category") or "output",
        }
        try:
            response = await client.get(f"{base_url}/view", params=params)
            if response.status_code != 200:
                LOGGER.debug(
                    "Preview fetch skipped for %s (status %s)",
                    filename,
                    response.status_code,
                )
                return
        except Exception as exc:  # pragma: no cover - network dependent
            LOGGER.debug("Preview fetch failed for %s: %s", filename, exc)
            return

        safe_name = filename.replace("/", "_").replace("\\", "_")
        async with self._lock:
            index = len(self._manifest)
        target_path = self.base_dir / f"{index:04d}_{safe_name}"
        try:
            target_path.write_bytes(response.content)
        except Exception as exc:  # pragma: no cover - filesystem dependent
            LOGGER.warning("Failed to persist preview %s: %s", target_path, exc)
            return

        meta = {
            "ts": _timestamp(),
            "prompt_id": prompt_id,
            "node_id": node_id,
            "filename": filename,
            "local_path": str(target_path),
            "type": params["type"],
            "subfolder": params["subfolder"],
            "metadata": entry.get("metadata") or {},
        }

        manifest_snapshot: List[Dict[str, Any]]
        async with self._lock:
            self._manifest.append(meta)
            if self.max_items and len(self._manifest) > self.max_items:
                self._manifest = self._manifest[-self.max_items :]
            manifest_snapshot = list(self._manifest)

        self._append_event(meta)
        self._persist_manifest(manifest_snapshot)

        if self.notifier:
            try:
                maybe = self.notifier(meta)
                if asyncio.iscoroutine(maybe):
                    await maybe
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("Preview notifier raised", exc_info=True)

    def _append_event(self, meta: Dict[str, Any]) -> None:
        try:
            with self._events_path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(meta, ensure_ascii=False) + "\n")
        except Exception:  # pragma: no cover - filesystem dependent
            LOGGER.debug("Failed to append preview event", exc_info=True)

    def _persist_manifest(self, manifest: List[Dict[str, Any]]) -> None:
        payload = {"updated_at": _timestamp(), "previews": manifest}
        try:
            self._manifest_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:  # pragma: no cover - filesystem dependent
            LOGGER.debug("Failed to persist preview manifest", exc_info=True)

    def finalize(self, result: Optional["RenderResult"] = None) -> None:
        """Write final manifest snapshot including the resolved result metadata."""
        payload = {"updated_at": _timestamp(), "previews": list(self._manifest)}
        if result is not None:
            try:
                payload["result"] = result.to_dict()
            except Exception:  # pragma: no cover - defensive
                payload["result"] = {"prompt_id": result.job.prompt_id}
        try:
            self._manifest_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:  # pragma: no cover - filesystem dependent
            LOGGER.debug("Failed to finalize manifest", exc_info=True)


__all__ = ["PreviewCollector"]
