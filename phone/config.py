#!/usr/bin/env python3
"""Конфигурация моста с телефоном.

Отдельный сервис — отдельное окружение и отдельная база. Мост не должен
падать оттого, что у ядра не настроена почта, а ядро — оттого, что телефон
второй день не синхронизировался.
"""
import os
import zoneinfo
from dataclasses import dataclass, field


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _list(name, default=()):
    raw = os.environ.get(name, "")
    return tuple(x.strip() for x in raw.split(",") if x.strip()) or tuple(default)


@dataclass(frozen=True)
class Config:
    db_path: str = os.environ.get("PHONE_DB", "/opt/assistant/phone.db")
    host: str = os.environ.get("PHONE_HOST", "127.0.0.1")
    port: int = _int("PHONE_PORT", 8820)
    tz: zoneinfo.ZoneInfo = zoneinfo.ZoneInfo(os.environ.get("TZ_NAME", "Europe/Moscow"))

    # Токен постановки устройства на учёт: без него никто не заведёт себе
    # «iPhone» и не начнёт присылать чужие данные.
    enroll_token: str = os.environ.get("PHONE_ENROLL_TOKEN", "").strip()
    # Токен для MCP-клиентов (ядро, Cursor, шлюз). С 127.0.0.1 не спрашивается.
    mcp_token: str = os.environ.get("PHONE_MCP_TOKEN", "").strip()
    allowed_origins: tuple = field(default_factory=lambda: _list("PHONE_ALLOWED_ORIGINS"))

    # Приватность: по умолчанию хранятся только метаданные переписки.
    # Текст сообщений — самое чувствительное, что есть в телефоне, и для
    # «кто ждёт ответа» он не нужен.
    store_text: bool = _bool("PHONE_STORE_TEXT", False)
    preview_chars: int = _int("PHONE_PREVIEW_CHARS", 160)
    # Ноль — хранить всё. Выгрузка Здоровья приезжает за все годы, и срок
    # в год молча съел бы её на первой же уборке.
    retention_days: int = _int("PHONE_RETENTION_DAYS", 0)

    # Сколько часов молчания считать поломкой моста, а не тихим днём.
    silence_hours: int = _int("PHONE_SILENCE_HOURS", 6)
    # По скольким дням считать норму, с которой сравнивается сегодняшний день.
    baseline_days: int = _int("PHONE_BASELINE_DAYS", 14)
    # Через сколько минут молчания входящее считается оставленным без ответа.
    reply_grace_minutes: int = _int("PHONE_REPLY_GRACE_MINUTES", 90)


config = Config()
