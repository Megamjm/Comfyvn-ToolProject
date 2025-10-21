from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from comfyvn.core.comfyui_client import ComfyUIClient

LOGGER = logging.getLogger("comfyvn.audio.comfyui")


class ComfyUIWorkflowError(RuntimeError):
    """Raised when a ComfyUI workflow fails or cannot complete."""


@dataclass
class ComfyUIWorkflowConfig:
    base_url: str
    workflow_path: Path
    output_dir: Path
    timeout: float = 120.0
    poll_interval: float = 1.5

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ComfyUIWorkflowConfig":
        base = str(data.get("base_url") or "http://127.0.0.1:8188")
        workflow = Path(data.get("workflow") or "")
        output = Path(data.get("output_dir") or "")
        timeout = float(data.get("timeout", 120.0))
        poll = float(data.get("poll_interval", 1.5))
        return cls(
            base_url=base.rstrip("/"),
            workflow_path=workflow.expanduser(),
            output_dir=output.expanduser(),
            timeout=timeout,
            poll_interval=poll,
        )


class ComfyUIAudioRunner:
    """Submits templated audio workflows to ComfyUI and resolves emitted files."""

    def __init__(self, config: ComfyUIWorkflowConfig) -> None:
        self.config = config
        self.client = ComfyUIClient(config.base_url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def is_ready(self, health_timeout: float = 0.6) -> Tuple[bool, Optional[str]]:
        if not self.config.workflow_path.exists():
            return False, f"workflow missing: {self.config.workflow_path}"
        if not self.config.output_dir.exists():
            return False, f"output directory missing: {self.config.output_dir}"
        if not self.client.health(timeout=health_timeout):
            return False, f"comfyui unreachable at {self.config.base_url}"
        return True, None

    def run(
        self,
        *,
        context: Dict[str, Any],
        output_types: Iterable[str] = ("audio",),
    ) -> Tuple[List[Path], Dict[str, Any]]:
        ready, reason = self.is_ready()
        if not ready:
            raise ComfyUIWorkflowError(reason or "comfyui unavailable")

        workflow = self._prepare_workflow(context)

        prompt_response = self.client.queue_prompt(workflow)
        prompt_id = prompt_response.get("prompt_id")
        if not prompt_id:
            raise ComfyUIWorkflowError("comfyui did not return a prompt_id")

        history_record = self._wait_for_prompt(prompt_id)
        outputs = self._collect_outputs(history_record, set(output_types))
        if not outputs:
            raise ComfyUIWorkflowError("comfyui workflow produced no audio outputs")

        resolved_files: List[Path] = []
        for entry in outputs:
            filename = entry.get("filename")
            if not filename:
                continue
            subfolder = entry.get("subfolder") or ""
            src = (self.config.output_dir / subfolder).joinpath(filename).expanduser()
            if src.exists():
                resolved_files.append(src)
            else:
                LOGGER.warning("ComfyUI output missing on disk: %s", src)

        if not resolved_files:
            raise ComfyUIWorkflowError(
                "comfyui outputs missing from configured output directory"
            )

        return resolved_files, {
            "prompt_id": prompt_id,
            "workflow": str(self.config.workflow_path),
            "base_url": self.config.base_url,
            "raw": history_record,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _prepare_workflow(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            payload = json.loads(self.config.workflow_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            raise ComfyUIWorkflowError(f"failed to load workflow: {exc}") from exc

        replacements = self._context_to_replacements(context)
        return self._apply_replacements(payload, replacements)

    def _context_to_replacements(self, context: Dict[str, Any]) -> Dict[str, str]:
        replacements: Dict[str, str] = {}
        for key, value in context.items():
            if isinstance(value, (list, tuple, set)):
                replacements[key] = ", ".join(str(v) for v in value if v or v == 0)
            elif value is None:
                replacements[key] = ""
            else:
                replacements[key] = str(value)
        return replacements

    def _apply_replacements(self, payload: Any, replacements: Dict[str, str]) -> Any:
        if isinstance(payload, dict):
            return {
                k: self._apply_replacements(v, replacements) for k, v in payload.items()
            }
        if isinstance(payload, list):
            return [self._apply_replacements(item, replacements) for item in payload]
        if isinstance(payload, str):
            result = payload
            for token, value in replacements.items():
                result = result.replace(f"{{{{{token}}}}}", value)
            return result
        return payload

    def _wait_for_prompt(self, prompt_id: str) -> Dict[str, Any]:
        deadline = time.monotonic() + self.config.timeout
        last_status: Optional[str] = None
        while time.monotonic() < deadline:
            history = self.client.get_history(prompt_id)
            history_data = history.get("history") or {}
            record = history_data.get(prompt_id)
            if record is None:
                # Some installations return record at top-level
                record = history.get(prompt_id) if isinstance(history, dict) else None
            if record:
                status = (record.get("status") or "").lower()
                if status in {"completed", "success", "finished"}:
                    return record
                if status in {"failed", "error", "canceled"}:
                    raise ComfyUIWorkflowError(
                        f"workflow failed: {record.get('status')}"
                    )
                last_status = status
            time.sleep(self.config.poll_interval)
        raise ComfyUIWorkflowError(
            f"workflow timeout after {self.config.timeout}s (last status={last_status})"
        )

    def _collect_outputs(
        self, record: Dict[str, Any], kinds: Iterable[str]
    ) -> List[Dict[str, Any]]:
        desired = {kind.lower() for kind in kinds}
        outputs = record.get("outputs") or {}
        matches: List[Dict[str, Any]] = []
        for node_outputs in outputs.values():
            if not isinstance(node_outputs, list):
                continue
            for entry in node_outputs:
                output_type = str(entry.get("type") or "").lower()
                if output_type in desired:
                    matches.append(entry)
        return matches


__all__ = ["ComfyUIAudioRunner", "ComfyUIWorkflowConfig", "ComfyUIWorkflowError"]
