"""Pilot modes A–E. Only offline_replay is activated in this build."""

from __future__ import annotations

MODES = {
    "offline_replay": {
        "code": "A",
        "active": True,
        "label": "офлайн-повтор кассет и лаборатории",
        "needs": [],
    },
    "shadow_live_read": {
        "code": "B",
        "active": False,
        "label": "теневое чтение живых источников",
        "needs": ["owner_approval", "source_allowlist", "no_telegram"],
    },
    "local_llm_pilot": {
        "code": "C",
        "active": False,
        "label": "локальная модель на разрешённом loopback",
        "needs": ["owner_approval", "llm_base_url", "injected_or_approved_client"],
    },
    "telegram_sandbox": {
        "code": "D",
        "active": False,
        "label": "песочница Telegram",
        "needs": ["owner_approval", "sandbox_bot", "test_chat", "kill_switch_off"],
    },
    "production": {
        "code": "E",
        "active": False,
        "label": "продакшен",
        "needs": ["separate_approval", "ENVIRONMENT=production refused by boot"],
    },
}

ACTIVE = "offline_replay"


def status() -> dict:
    return {
        "active": ACTIVE,
        "modes": MODES,
        "publish_enabled": False,
        "telegram_send": 0,
        "live_data": False,
        "real_revenue": "unknown",
        "production_ready": False,
    }


def blocked(mode: str) -> dict:
    row = MODES.get(mode) or {"code": "?", "active": False, "label": mode, "needs": ["unknown_mode"]}
    if row.get("active"):
        return {"blocked": False, "mode": mode, **row}
    return {
        "blocked": True,
        "mode": mode,
        "reason": "blocked_by_policy",
        "attempted": False,
        **row,
    }
