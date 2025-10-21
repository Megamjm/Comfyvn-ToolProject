from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional

from comfyvn.core.settings_manager import SettingsManager

LOGGER = logging.getLogger("comfyvn.policy.gate")


@dataclass
class PolicyStatus:
    ack_legal_v1: bool
    ack_timestamp: Optional[float]
    warn_override_enabled: bool

    @property
    def requires_ack(self) -> bool:
        return not self.ack_legal_v1

    def to_dict(self) -> Dict[str, Optional[float | bool]]:
        return {
            "ack_legal_v1": self.ack_legal_v1,
            "ack_timestamp": self.ack_timestamp,
            "warn_override_enabled": self.warn_override_enabled,
            "requires_ack": self.requires_ack,
        }


class PolicyGate:
    def __init__(self, settings: Optional[SettingsManager] = None) -> None:
        self.settings = settings or SettingsManager()

    def status(self) -> PolicyStatus:
        cfg = self.settings.load()
        policy = cfg.get("policy", {})
        return PolicyStatus(
            ack_legal_v1=bool(policy.get("ack_legal_v1", False)),
            ack_timestamp=policy.get("ack_timestamp"),
            warn_override_enabled=bool(policy.get("warn_override_enabled", True)),
        )

    def acknowledge(self, *, user: str, notes: Optional[str] = None) -> PolicyStatus:
        cfg = self.settings.load()
        policy = cfg.get("policy", {})
        policy["ack_legal_v1"] = True
        policy["ack_timestamp"] = time.time()
        if notes:
            policy.setdefault("ack_notes", []).append(
                {"user": user, "notes": notes, "ts": policy["ack_timestamp"]}
            )
        cfg["policy"] = policy
        self.settings.save(cfg)
        LOGGER.info("Policy acknowledged by %s", user or "unknown")
        return self.status()

    def reset(self) -> PolicyStatus:
        cfg = self.settings.load()
        cfg["policy"] = {
            "ack_legal_v1": False,
            "ack_timestamp": None,
            "warn_override_enabled": cfg.get("policy", {}).get(
                "warn_override_enabled", True
            ),
        }
        self.settings.save(cfg)
        LOGGER.info("Policy acknowledgement reset")
        return self.status()

    def evaluate_action(
        self,
        action: str,
        *,
        override: bool = False,
    ) -> Dict[str, object]:
        status = self.status()
        warnings: list[str] = []
        allow = True
        action_scope = action.split(":", 1)[0]
        action_root = action_scope.split(".", 1)[0].lower()
        gate_kind = action_root or "general"
        requires_block = gate_kind in {"export", "import"}

        if status.requires_ack:
            warnings.append(
                "Legal acknowledgement required before exporting or importing content."
            )
            if requires_block:
                allow = False
                LOGGER.warning(
                    "Policy gate blocked action=%s pending acknowledgement", action
                )
        if override and status.warn_override_enabled:
            LOGGER.warning("Policy override requested for action=%s", action)
            warnings.append("User override requested; ensure legal terms are accepted.")
        return {
            "action": action,
            "requires_ack": status.requires_ack,
            "warnings": warnings,
            "allow": allow,
            "override_requested": override,
            "gate": gate_kind,
        }


policy_gate = PolicyGate()
