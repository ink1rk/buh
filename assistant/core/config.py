#!/usr/bin/env python3
"""Typed configuration for the whole core.

One place reads the environment; everything else asks this module. Secrets stay
in /etc/*.env files loaded by systemd — never in the repository.
"""
import os
import zoneinfo
from dataclasses import dataclass, field


def _bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _list(name, default=()):
    raw = os.environ.get(name, "")
    return tuple(x.strip() for x in raw.split(",") if x.strip()) or tuple(default)


@dataclass(frozen=True)
class LLMConfig:
    local_url: str = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    local_model: str = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    gateway_url: str = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8791/v1")
    gateway_key: str = os.environ.get("GATEWAY_KEY", "")
    gateway_model: str = os.environ.get("GATEWAY_MODEL", "cursor-grok-4.6-high-fast")
    default_provider: str = os.environ.get("LLM_DEFAULT_PROVIDER", "local")
    # Anything touching personal data must stay on the local provider.
    private_provider: str = os.environ.get("LLM_PRIVATE_PROVIDER", "local")
    timeout: int = _int("LLM_TIMEOUT", 300)


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str = os.environ.get("TG_TOKEN", "")
    owner_id: int = _int("TG_ALLOWED_ID", 0)
    proxy: str = os.environ.get("TG_PROXY", "http://172.20.20.231:8080")
    user_service_url: str = os.environ.get("TG_USER_URL", "http://127.0.0.1:8810")


@dataclass(frozen=True)
class ActionConfig:
    approval_ttl: int = _int("ACTION_APPROVAL_TTL", 600)        # seconds
    max_attempts: int = _int("ACTION_MAX_ATTEMPTS", 3)
    retry_backoff: float = float(os.environ.get("ACTION_RETRY_BACKOFF", "2.0"))


@dataclass(frozen=True)
class NotificationConfig:
    quiet_from: int = _int("NOTIFY_QUIET_FROM", 23)             # hour, local
    quiet_to: int = _int("NOTIFY_QUIET_TO", 8)
    min_interval: int = _int("NOTIFY_MIN_INTERVAL", 30)         # per source, seconds
    digest_severities: tuple = ("low",)


@dataclass(frozen=True)
class MemoryConfig:
    min_confidence: float = float(os.environ.get("MEMORY_MIN_CONFIDENCE", "0.45"))
    inference_confidence_cap: float = float(
        os.environ.get("MEMORY_INFERENCE_CAP", "0.6"))
    dedupe_threshold: float = float(os.environ.get("MEMORY_DEDUPE_THRESHOLD", "0.62"))
    retrieval_limit: int = _int("MEMORY_RETRIEVAL_LIMIT", 8)


@dataclass(frozen=True)
class Config:
    db_path: str = os.environ.get("ASSISTANT_DB", "/opt/assistant/assistant.db")
    finance_api: str = os.environ.get("FINANCE_API", "http://127.0.0.1/api/v1")
    tz: zoneinfo.ZoneInfo = zoneinfo.ZoneInfo(os.environ.get("TZ_NAME", "Europe/Moscow"))
    owner_name: str = os.environ.get("OWNER_NAME", "").strip()
    owner_gender: str = os.environ.get("OWNER_GENDER", "male")
    assistant_name: str = os.environ.get("ASSISTANT_NAME", "Джарвис")
    event_retention_days: int = _int("EVENT_RETENTION_DAYS", 30)
    response_mode: str = os.environ.get("RESPONSE_MODE", "SUGGEST_ONLY")
    # Пусто — доступ как раньше, только предупреждение в /api/health.
    web_token: str = os.environ.get("ASSISTANT_WEB_TOKEN", "").strip()
    trusted_peers: tuple = field(default_factory=lambda: _list("TRUSTED_PEERS"))
    llm: LLMConfig = field(default_factory=LLMConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    actions: ActionConfig = field(default_factory=ActionConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)


config = Config()
