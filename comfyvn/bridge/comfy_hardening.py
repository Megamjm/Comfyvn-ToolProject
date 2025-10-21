from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, MutableMapping, Optional, Sequence

from comfyvn.bridge.comfy import ComfyBridgeError
from comfyvn.core.comfy_bridge import ComfyBridge

LOGGER = logging.getLogger(__name__)


class HardenedBridgeError(RuntimeError):
    """Base error raised by the hardened bridge helper."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class HardenedBridgeUnavailable(HardenedBridgeError):
    """Raised when the ComfyUI backend cannot be reached."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503)


@dataclass(frozen=True)
class LoRAEntry:
    path: str
    weight: float = 1.0
    clip: Optional[float] = None
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"path": self.path, "weight": self.weight}
        if self.clip is not None:
            payload["clip"] = self.clip
        if self.source:
            payload["source"] = self.source
        return payload


class CharacterLoRARegistry:
    """Loads per-character LoRA descriptors from ``data/characters/<id>/lora.json``."""

    def __init__(self, base_dir: Path | str = Path("data/characters")) -> None:
        self._base_dir = Path(base_dir)

    def load(self, character_id: str) -> List[LoRAEntry]:
        """Return the LoRA entries for a character, handling legacy layouts."""
        safe_id = (character_id or "").strip()
        if not safe_id:
            return []

        candidates = [
            self._base_dir / safe_id / "lora.json",
            self._base_dir / f"{safe_id}.lora.json",
        ]

        entries: List[LoRAEntry] = []
        for path in candidates:
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("LoRA registry unreadable for %s (%s)", safe_id, exc)
                continue
            payloads: Sequence[dict] = []
            if isinstance(data, MutableMapping):
                maybe_list = data.get("loras")
                if isinstance(maybe_list, list):
                    payloads = [item for item in maybe_list if isinstance(item, dict)]
            elif isinstance(data, list):
                payloads = [item for item in data if isinstance(item, dict)]
            for raw in payloads:
                entry = _coerce_lora(raw, source=safe_id)
                if entry:
                    entries.append(entry)
            if entries:
                break
        return entries


PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_.:-]+)\s*\}\}")


def _coerce_lora(
    payload: Dict[str, Any], *, source: Optional[str] = None
) -> Optional[LoRAEntry]:
    path = str(payload.get("path") or payload.get("name") or "").strip()
    if not path:
        return None
    weight = payload.get("weight", payload.get("strength", 1.0))
    clip_val = payload.get("clip")
    try:
        weight_f = float(weight)
    except (TypeError, ValueError):
        weight_f = 1.0
    clip: Optional[float]
    try:
        clip = float(clip_val) if clip_val is not None else None
    except (TypeError, ValueError):
        clip = None
    return LoRAEntry(path=path, weight=weight_f, clip=clip, source=source)


def _dedupe_loras(entries: Iterable[LoRAEntry]) -> List[LoRAEntry]:
    seen: Dict[str, LoRAEntry] = {}
    ordered: List[LoRAEntry] = []
    for entry in entries:
        if entry.path in seen:
            continue
        seen[entry.path] = entry
        ordered.append(entry)
    return ordered


def _load_json_candidates(paths: Iterable[Path]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for path in paths:
        if not path or not Path(path).exists():
            continue
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            merged.update(data)
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Skipping config candidate %s", path)
    return merged


def _apply_overrides(obj: Any, overrides: Dict[str, Any]) -> Any:
    if isinstance(obj, dict):
        return {key: _apply_overrides(value, overrides) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_apply_overrides(item, overrides) for item in obj]
    if isinstance(obj, str):
        match = PLACEHOLDER.fullmatch(obj)
        if match:
            key = match.group(1)
            if key in overrides:
                return _coerce_override(overrides[key])
            return obj

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in overrides:
                return match.group(0)
            value = overrides[key]
            if isinstance(value, (dict, list)):
                return json.dumps(value)
            return str(value)

        return PLACEHOLDER.sub(repl, obj)
    return obj


def _coerce_override(value: Any) -> Any:
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


class HardenedComfyBridge:
    """High-level helper that hardens ComfyUI submissions with overrides and LoRA support."""

    DEFAULT_CONFIG_PATHS = (
        Path("comfyvn.json"),
        Path("config/comfyvn.json"),
    )
    DEFAULT_OUTPUT_DIR = Path("ComfyUI/output")

    def __init__(
        self,
        core_bridge: Optional[ComfyBridge] = None,
        *,
        config_paths: Optional[Iterable[Path | str]] = None,
        lora_registry: Optional[CharacterLoRARegistry] = None,
    ) -> None:
        self._core = core_bridge or ComfyBridge()
        self._config_paths = tuple(
            Path(path) if not isinstance(path, Path) else path
            for path in (config_paths or self.DEFAULT_CONFIG_PATHS)
        )
        self._registry = lora_registry or CharacterLoRARegistry()
        self._config: Dict[str, Any] = {}
        self._feature_enabled = False
        self._output_dir = self.DEFAULT_OUTPUT_DIR
        self.reload()

    def reload(self) -> None:
        """Reload configuration from disk."""
        self._config = _load_json_candidates(self._config_paths)
        features = self._config.get("features") or {}
        self._feature_enabled = bool(
            features.get("enable_comfy_bridge_hardening", False)
        )
        integrations = self._config.get("integrations") or {}
        output_dir = integrations.get("comfyui_output_dir")
        if output_dir:
            try:
                self._output_dir = Path(output_dir).expanduser()
            except Exception:  # pragma: no cover - defensive
                self._output_dir = self.DEFAULT_OUTPUT_DIR
        else:
            self._output_dir = self.DEFAULT_OUTPUT_DIR

    @property
    def enabled(self) -> bool:
        return self._feature_enabled

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a workflow with overrides applied, returning the hardened payload."""
        self.reload()
        if not self.enabled:
            raise HardenedBridgeError(
                "Hardened bridge feature is disabled; enable enable_comfy_bridge_hardening"
            )

        workflow_spec = self._resolve_workflow(payload)
        overrides = self._collect_overrides(payload)
        workflow = _apply_overrides(workflow_spec, overrides)

        bridge_payload = self._build_bridge_payload(payload, workflow, overrides)
        try:
            result = self._core.submit(bridge_payload)
        except ComfyBridgeError as exc:
            LOGGER.error("ComfyUI submission failed: %s", exc)
            raise HardenedBridgeUnavailable(str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("ComfyUI bridge crashed: %s", exc)
            raise HardenedBridgeError(f"Comfy bridge error: {exc}") from exc

        if not isinstance(result, dict):
            raise HardenedBridgeError("Comfy bridge returned an invalid payload")
        if not result.get("ok"):
            message = str(result.get("error") or "ComfyUI bridge unavailable")
            raise HardenedBridgeUnavailable(message)

        return self._format_response(result, overrides)

    # ------------------------------------------------------------------ internals ------------------------------------------------------------------
    def _resolve_workflow(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raw = payload.get("workflow")
        if isinstance(raw, dict):
            return deepcopy(raw)

        workflow_path = (
            payload.get("workflow_path")
            or payload.get("graph_path")
            or self._default_workflow_path()
        )
        if not workflow_path:
            raise HardenedBridgeError("workflow or workflow_path is required")

        candidates = self._workflow_candidates(str(workflow_path))
        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception as exc:
                raise HardenedBridgeError(
                    f"Workflow {candidate} is not valid JSON"
                ) from exc
            if not isinstance(data, dict):
                raise HardenedBridgeError(f"Workflow {candidate} must be a JSON object")
            return data

        raise HardenedBridgeError(f"Workflow not found: {workflow_path}")

    def _default_workflow_path(self) -> Optional[str]:
        integrations = self._config.get("integrations") or {}
        default_workflow = integrations.get("comfyui_workflow")
        return default_workflow

    def _workflow_candidates(self, hint: str) -> List[Path]:
        root = Path(hint)
        name = root.name
        search = [
            root,
            Path("config") / hint,
            Path("config") / name,
            Path("data/workflows") / hint,
            Path("data/workflows") / name,
            Path("comfyvn/workflows") / hint,
            Path("comfyvn/workflows") / name,
        ]
        deduped: List[Path] = []
        seen: set[Path] = set()
        for path in search:
            try:
                resolved = path if path.is_absolute() else path
            except Exception:  # pragma: no cover - defensive
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            deduped.append(resolved)
        return deduped

    def _collect_overrides(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        overrides: Dict[str, Any] = {}
        raw_overrides = payload.get("overrides")
        if isinstance(raw_overrides, dict):
            overrides.update(raw_overrides)

        for key in ("prompt", "negative_prompt", "seed", "loras"):
            if key in payload and key not in overrides:
                overrides[key] = payload[key]

        loras = overrides.get("loras")
        entries = self._normalise_loras(loras)
        characters = self._extract_character_ids(payload)
        for character_id in characters:
            entries.extend(self._registry.load(character_id))
        overrides["loras"] = [entry.to_dict() for entry in _dedupe_loras(entries)]
        overrides.setdefault("characters", characters)
        return overrides

    def _normalise_loras(self, payload: Any) -> List[LoRAEntry]:
        if payload is None:
            return []
        loras: List[LoRAEntry] = []
        if isinstance(payload, dict):
            payload = payload.get("loras")
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    entry = _coerce_lora(item)
                    if entry:
                        loras.append(entry)
        return loras

    @staticmethod
    def _extract_character_ids(payload: Dict[str, Any]) -> List[str]:
        ids: List[str] = []
        for key in ("character", "character_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                ids.append(value.strip())
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                ids.extend(str(item).strip() for item in value if str(item).strip())
        characters = payload.get("characters")
        if isinstance(characters, Sequence) and not isinstance(
            characters, (str, bytes)
        ):
            ids.extend(str(item).strip() for item in characters if str(item).strip())

        inputs = payload.get("inputs")
        if isinstance(inputs, dict):
            for key in ("character", "character_id"):
                value = inputs.get(key)
                if isinstance(value, str) and value.strip():
                    ids.append(value.strip())
        unique: List[str] = []
        seen: set[str] = set()
        for cid in ids:
            if cid in seen:
                continue
            seen.add(cid)
            unique.append(cid)
        return unique

    def _build_bridge_payload(
        self,
        original: Dict[str, Any],
        workflow: Dict[str, Any],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "workflow": workflow,
            "workflow_id": original.get("workflow_id")
            or workflow.get("workflow_id")
            or original.get("id")
            or "comfyvn.workflow",
            "inputs": dict(original.get("inputs") or {}),
            "packs": dict(original.get("packs") or {}),
            "pins": dict(original.get("pins") or {}),
            "metadata": dict(original.get("metadata") or {}),
            "seeds": dict(original.get("seeds") or {}),
            "tags": dict(original.get("tags") or {}),
        }

        if "timeout" in original:
            payload["timeout"] = original["timeout"]
        if "poll_interval" in original:
            payload["poll_interval"] = original["poll_interval"]
        if "download_dir" in original:
            payload["download_dir"] = original["download_dir"]

        prompt = overrides.get("prompt")
        if isinstance(prompt, str):
            payload["inputs"].setdefault("prompt", prompt)

        seed = overrides.get("seed")
        try:
            seed_int = int(seed) if seed is not None else None
        except (TypeError, ValueError):
            seed_int = None
        if seed_int is not None:
            payload["seeds"].setdefault("primary", seed_int)

        loras = overrides.get("loras") or []
        metadata = payload["metadata"]
        metadata.setdefault("overrides", {})
        if isinstance(metadata["overrides"], dict):
            metadata["overrides"].update(
                {k: v for k, v in overrides.items() if k != "loras"}
            )
        metadata["loras"] = loras
        if overrides.get("characters"):
            metadata["characters"] = overrides["characters"]

        return payload

    def _format_response(
        self, result: Dict[str, Any], overrides: Dict[str, Any]
    ) -> Dict[str, Any]:
        artifacts = result.get("artifacts") or []
        primary = _select_primary_artifact(artifacts)
        sidecar = _select_sidecar_artifact(artifacts)
        primary_payload = _augment_artifact(primary, self._output_dir)
        sidecar_payload = _augment_artifact(sidecar, self._output_dir)
        sidecar_content = (
            _read_sidecar(sidecar_payload["path"]) if sidecar_payload else None
        )

        enriched = {
            "ok": True,
            "prompt_id": result.get("prompt_id"),
            "workflow_id": result.get("workflow_id"),
            "history": result.get("history"),
            "artifacts": artifacts,
            "primary_artifact": primary_payload,
            "sidecar": sidecar_payload,
            "sidecar_content": sidecar_content,
            "overrides": overrides,
            "context": result.get("context"),
        }
        return {k: v for k, v in enriched.items() if v is not None}


def _select_primary_artifact(
    artifacts: Sequence[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    if not artifacts:
        return None
    for candidate in artifacts:
        kind = str(candidate.get("type") or "").lower()
        if kind in {"image", "video", "output"}:
            return candidate
        filename = str(candidate.get("filename") or "")
        if filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".mp4")):
            return candidate
    return artifacts[0]


def _select_sidecar_artifact(
    artifacts: Sequence[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    for candidate in artifacts:
        kind = str(candidate.get("type") or "").lower()
        if kind in {"json", "text", "metadata"}:
            return candidate
        filename = str(candidate.get("filename") or "")
        if filename.lower().endswith((".json", ".txt", ".log")):
            return candidate
    return None


def _augment_artifact(
    artifact: Optional[Dict[str, Any]], output_dir: Path
) -> Optional[Dict[str, Any]]:
    if not artifact:
        return None
    filename = artifact.get("filename")
    if not filename:
        return dict(artifact)
    subfolder = str(artifact.get("subfolder") or "").strip().strip("/")
    parts = [filename]
    if subfolder:
        parts.insert(0, subfolder)
    path = output_dir.joinpath(*parts).expanduser()
    payload = dict(artifact)
    payload["path"] = str(path)
    return payload


def _read_sidecar(path: Optional[str]) -> Optional[Any]:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        if file_path.suffix.lower() == ".json":
            return json.loads(file_path.read_text(encoding="utf-8"))
        return file_path.read_text(encoding="utf-8")
    except Exception:  # pragma: no cover - defensive
        return None


__all__ = [
    "CharacterLoRARegistry",
    "HardenedBridgeError",
    "HardenedBridgeUnavailable",
    "HardenedComfyBridge",
    "LoRAEntry",
]
