#!/usr/bin/env python3
"""Permission engine.

Rules live in one table instead of scattered `if` statements. Every action type
has a risk level; every risk level has a default decision; single action types
and trusted counterparties can override it. The engine answers ALLOW / DENY /
REQUIRE_APPROVAL and nothing else — it never executes anything.
"""
import json
from dataclasses import dataclass
from enum import Enum

from . import db
from .config import config


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


# Risk per action type. Unknown types are treated as HIGH on purpose.
ACTION_RISK = {
    "create.note": RiskLevel.LOW,
    "create.task": RiskLevel.LOW,
    "create.memory": RiskLevel.LOW,
    "notification.send": RiskLevel.LOW,
    "send.telegram.message": RiskLevel.MEDIUM,
    "edit.telegram.message": RiskLevel.MEDIUM,
    "delete.telegram.message": RiskLevel.MEDIUM,
    "send.email": RiskLevel.MEDIUM,
    "create.calendar.event": RiskLevel.MEDIUM,
    "call.taxi": RiskLevel.HIGH,
    "purchase.ozon": RiskLevel.HIGH,
    "bank.transfer": RiskLevel.CRITICAL,
}

DEFAULT_POLICY = {
    RiskLevel.LOW: Decision.ALLOW,
    RiskLevel.MEDIUM: Decision.REQUIRE_APPROVAL,
    RiskLevel.HIGH: Decision.REQUIRE_APPROVAL,
    RiskLevel.CRITICAL: Decision.REQUIRE_APPROVAL,
}

POLICY_KEY = "permission_policy"


@dataclass
class PermissionResult:
    decision: Decision
    risk: RiskLevel
    reason: str

    @property
    def allowed(self):
        return self.decision is Decision.ALLOW

    def as_dict(self):
        return {"decision": self.decision.value, "risk": self.risk.value,
                "reason": self.reason}


class PermissionEngine:
    def __init__(self, risk_map=None, policy=None, trusted_peers=None):
        self.risk_map = dict(risk_map or ACTION_RISK)
        self.policy = dict(policy or DEFAULT_POLICY)
        self.trusted_peers = set(str(p) for p in (trusted_peers or config.trusted_peers))
        self.overrides = self._load_overrides()

    # -- policy storage -------------------------------------------------
    def _load_overrides(self):
        try:
            raw = db.setting(POLICY_KEY)
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def set_override(self, action_type, decision):
        self.overrides[action_type] = Decision(decision).value
        db.set_setting(POLICY_KEY, json.dumps(self.overrides, ensure_ascii=False))

    def clear_override(self, action_type):
        self.overrides.pop(action_type, None)
        db.set_setting(POLICY_KEY, json.dumps(self.overrides, ensure_ascii=False))

    # -- decisions ------------------------------------------------------
    def risk_of(self, action_type):
        return self.risk_map.get(action_type, RiskLevel.HIGH)

    def check(self, action, context=None):
        """context may carry `user_confirmed` (the owner pressed a button)."""
        context = context or {}
        risk = self.risk_of(action.type)

        if action.type in self.overrides:
            decision = Decision(self.overrides[action.type])
            return PermissionResult(decision, risk, "policy override")

        if context.get("user_confirmed"):
            # The owner explicitly triggered this exact action in the interface.
            if risk is RiskLevel.CRITICAL:
                return PermissionResult(Decision.REQUIRE_APPROVAL, risk,
                                        "критичное действие подтверждается отдельно")
            return PermissionResult(Decision.ALLOW, risk, "подтверждено пользователем")

        peer = str((action.parameters or {}).get("peer_id")
                   or (action.parameters or {}).get("chat_id") or "")
        if action.type == "send.telegram.message" and peer and peer in self.trusted_peers:
            return PermissionResult(Decision.ALLOW, risk, "доверенный получатель")

        return PermissionResult(self.policy.get(risk, Decision.REQUIRE_APPROVAL), risk,
                                f"политика по уровню риска {risk.value}")

    def describe(self):
        return {"risk_levels": {k: v.value for k, v in self.risk_map.items()},
                "defaults": {k.value: v.value for k, v in self.policy.items()},
                "overrides": self.overrides,
                "trusted_peers": sorted(self.trusted_peers)}
