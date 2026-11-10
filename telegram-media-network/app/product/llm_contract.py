"""LLM adapters. local never opens a socket in R10. Source text is data, not instructions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.product.editorial import write_format

_INJECTION = re.compile(
    r"ignore previous|system prompt|you are now|publish:\s*true|срочно опубликуй|"
    r"destination\s*=|GLOBAL_KILL_SWITCH|SPONSORED_ENABLED|allowed_actions",
    re.I,
)

ROLES = ("researcher", "skeptic", "editor", "stylist", "qa")
MODES = ("mock", "manual", "local")


@dataclass
class LLMResult:
    ok: bool
    payload: dict
    role: str
    mode: str
    error: str = ""
    sanitized: bool = False


def sanitize_source(text: str) -> tuple[str, bool]:
    cleaned = _INJECTION.sub("", text or "")
    return cleaned.strip(), cleaned != (text or "")


def generate(
    *,
    mode: str,
    role: str,
    channel_id: str,
    format_id: str,
    title: str,
    fact: str,
    url: str,
    preprint: bool = False,
    raw_json: str = "",
) -> LLMResult:
    if mode not in MODES:
        return LLMResult(False, {}, role, mode, error="mode_not_allowed")
    if role not in ROLES:
        return LLMResult(False, {}, role, mode, error="unknown_role")
    if mode == "local":
        return LLMResult(False, {}, role, mode, error="local_provider_disabled")
    if mode == "manual":
        return LLMResult(True, {"manual": True, "requires_review": True, "title": title, "body": ""}, role, mode)
    clean, changed = sanitize_source(fact)
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if not isinstance(parsed, dict) or "title" not in parsed or "body" not in parsed:
                return LLMResult(False, {"requires_review": True}, role, mode, error="invalid_model_json")
        except json.JSONDecodeError:
            return LLMResult(False, {"requires_review": True}, role, mode, error="invalid_model_json")
    payload = write_format(channel_id, format_id, title, clean, url, preprint=preprint)
    payload["agent_role"] = role
    payload["llm_mode"] = "mock"
    payload["requires_review"] = True
    if role == "skeptic":
        payload["body"] = ("Сомнение: источник может ошибаться. " + payload["body"])[:900]
    if role == "qa":
        payload["body"] = (payload["body"] + " QA: DEMO, отправка запрещена.")[:900]
    return LLMResult(True, payload, role, mode, sanitized=changed)
