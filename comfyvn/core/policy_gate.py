from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional

from comfyvn.core.settings_manager import SettingsManager

LOGGER = logging.getLogger("comfyvn.policy.gate")
DISCLAIMER_LINKS = {
    "policy": "docs/LEGAL_LIABILITY.md",
    "advisory": "docs/ADVISORY_EXPORT.md",
    "scans": "docs/development/advisory_modding.md",
}


@dataclass
class PolicyStatus:
    ack_legal_v1: bool
    ack_timestamp: Optional[float]
    ack_user: Optional[str]
    warn_override_enabled: bool

    @property
    def requires_ack(self) -> bool:
        return not self.ack_legal_v1

    def to_dict(self) -> Dict[str, object]:
        return {
            "ack_legal_v1": self.ack_legal_v1,
            "ack_disclaimer_v1": self.ack_legal_v1,
            "ack_timestamp": self.ack_timestamp,
            "ack_user": self.ack_user,
            "warn_override_enabled": self.warn_override_enabled,
            "requires_ack": self.requires_ack,
        }


class PolicyGate:
    def __init__(self, settings: Optional[SettingsManager] = None) -> None:
        self.settings = settings or SettingsManager()

    def status(self) -> PolicyStatus:
        cfg = self.settings.load()
        policy = dict(cfg.get("policy") or {})
        advisory_ack = dict(cfg.get("advisory_ack") or {})
        ack_flag = bool(cfg.get("ack_disclaimer_v1", policy.get("ack_legal_v1", False)))
        timestamp = advisory_ack.get("timestamp", policy.get("ack_timestamp"))
        user = advisory_ack.get("user", policy.get("ack_user"))
        warn_override = bool(policy.get("warn_override_enabled", True))

        changed = False
        if policy.get("ack_legal_v1") != ack_flag:
            policy["ack_legal_v1"] = ack_flag
            changed = True
        if policy.get("ack_timestamp") != timestamp:
            policy["ack_timestamp"] = timestamp
            changed = True
        if policy.get("ack_user") != user:
            policy["ack_user"] = user
            changed = True
        if changed:
            cfg["policy"] = policy
            self.settings.save(cfg)
        return PolicyStatus(
            ack_legal_v1=ack_flag,
            ack_timestamp=timestamp,
            ack_user=user,
            warn_override_enabled=warn_override,
        )

    def acknowledge(
        self,
        *,
        user: str,
        notes: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> PolicyStatus:
        cfg = self.settings.load()
        policy = dict(cfg.get("policy") or {})
        advisory_ack = dict(cfg.get("advisory_ack") or {})

        ts = float(timestamp or time.time())
        display_user = str(user or "").strip() or None

        cfg["ack_disclaimer_v1"] = True
        policy["ack_legal_v1"] = True
        policy["ack_timestamp"] = ts
        policy["ack_user"] = display_user
        policy.setdefault(
            "warn_override_enabled", policy.get("warn_override_enabled", True)
        )

        note_list = list(advisory_ack.get("notes") or [])
        if notes:
            note_list.append(
                {
                    "note": notes,
                    "user": display_user,
                    "timestamp": ts,
                }
            )
        advisory_ack.update(
            {
                "user": display_user,
                "timestamp": ts,
                "notes": note_list,
                "version": advisory_ack.get("version") or "v1",
            }
        )

        cfg["policy"] = policy
        cfg["advisory_ack"] = advisory_ack
        self.settings.save(cfg)
        LOGGER.info("Advisory disclaimer acknowledged by %s", display_user or "unknown")
        return self.status()

    def reset(self) -> PolicyStatus:
        cfg = self.settings.load()
        policy = dict(cfg.get("policy") or {})
        policy.update(
            {
                "ack_legal_v1": False,
                "ack_timestamp": None,
                "ack_user": None,
                "warn_override_enabled": policy.get("warn_override_enabled", True),
            }
        )
        advisory_ack = dict(cfg.get("advisory_ack") or {})
        advisory_ack.update({"user": None, "timestamp": None})

        cfg["policy"] = policy
        cfg["ack_disclaimer_v1"] = False
        cfg["advisory_ack"] = advisory_ack
        self.settings.save(cfg)
        LOGGER.info("Advisory disclaimer acknowledgement reset")
        return self.status()

    def evaluate_action(
        self,
        action: str,
        *,
        override: bool = False,
    ) -> Dict[str, object]:
        status = self.status()
        warnings: list[str] = []
        action_scope = action.split(":", 1)[0]
        action_root = action_scope.split(".", 1)[0].lower()
        gate_kind = action_root or "general"
        allow = True

        disclaimer = {
            "acknowledged": not status.requires_ack,
            "required": status.requires_ack,
            "version": "v1",
            "links": dict(DISCLAIMER_LINKS),
        }

        if status.requires_ack:
            warnings.append(
                "Review and acknowledge the ComfyVN advisory disclaimer before distributing imports or exports."
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
            "disclaimer": disclaimer,
        }


policy_gate = PolicyGate()
