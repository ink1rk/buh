from __future__ import annotations

import re
from typing import Any

SECRET_FIELD = re.compile(r"(token|password|secret|authorization|cookie|api[_-]?key|session)", re.I)
TELEGRAM_TOKEN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
GITHUB_TOKEN = re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")
GENERIC_KEY = re.compile(r"\bsk-[A-Za-z0-9]{10,}\b")
BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]+")
URL_PASSWORD = re.compile(r"://([^:/\s]+):([^@/\s]+)@")
ASSIGNMENT = re.compile(
    r"(?i)\b(telegram_bot_token|github_read_token|hf_read_token|session_secret|password|token)\b\s*[=:]\s*\S+"
)


def redact(text: str) -> str:
    if not text:
        return text
    cleaned = URL_PASSWORD.sub(r"://\1:***@", text)
    cleaned = ASSIGNMENT.sub(lambda m: f"{m.group(1)}=***", cleaned)
    cleaned = BEARER.sub("Bearer [REDACTED]", cleaned)
    cleaned = TELEGRAM_TOKEN.sub("[REDACTED_TELEGRAM]", cleaned)
    cleaned = GITHUB_TOKEN.sub("[REDACTED_GITHUB]", cleaned)
    cleaned = GENERIC_KEY.sub("[REDACTED_KEY]", cleaned)
    return cleaned


def redact_obj(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_FIELD.search(str(key)):
                cleaned[str(key)] = "***"
            else:
                cleaned[str(key)] = redact_obj(item)
        return cleaned
    if isinstance(value, list):
        return [redact_obj(item) for item in value]
    if isinstance(value, tuple):
        return [redact_obj(item) for item in value]
    return value
