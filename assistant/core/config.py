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


# Чтобы в окружении хранились только логин и пароль, а не порты провайдера.
MAIL_PRESETS = {
    "yandex": ("imap.yandex.ru", 993, "smtp.yandex.ru", 465),
    "gmail": ("imap.gmail.com", 993, "smtp.gmail.com", 465),
    "mailru": ("imap.mail.ru", 993, "smtp.mail.ru", 465),
    "icloud": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587),
}


@dataclass(frozen=True)
class MailAccount:
    name: str
    user: str
    password: str
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    from_name: str = ""
    # Порт не говорит о режиме: 465 обычно implicit TLS, 587 — STARTTLS, но
    # на своём сервере бывает любой. Угадывание молча вешало отправку.
    smtp_ssl: bool = True

    @property
    def address(self):
        return self.user.lower()


def _mail_accounts():
    """MAIL_ACCOUNTS=yandex,work → MAIL_YANDEX_USER, MAIL_WORK_USER и так далее."""
    accounts = []
    for name in _list("MAIL_ACCOUNTS"):
        key = name.upper().replace("-", "_")
        user = os.environ.get(f"MAIL_{key}_USER", "").strip()
        password = os.environ.get(f"MAIL_{key}_PASSWORD", "")
        if not (user and password):
            continue                      # настроен наполовину — значит не настроен
        preset = MAIL_PRESETS.get(name.lower(), ("", 993, "", 465))
        smtp_port = _int(f"MAIL_{key}_SMTP_PORT", preset[3])
        accounts.append(MailAccount(
            name=name.lower(),
            user=user,
            password=password,
            imap_host=os.environ.get(f"MAIL_{key}_IMAP_HOST", preset[0]).strip(),
            imap_port=_int(f"MAIL_{key}_IMAP_PORT", preset[1]),
            smtp_host=os.environ.get(f"MAIL_{key}_SMTP_HOST", preset[2]).strip(),
            smtp_port=smtp_port,
            smtp_ssl=_bool(f"MAIL_{key}_SMTP_SSL", smtp_port != 587),
            from_name=os.environ.get(f"MAIL_{key}_FROM_NAME", "").strip()))
    return tuple(a for a in accounts if a.imap_host and a.smtp_host)


@dataclass(frozen=True)
class EmailConfig:
    accounts: tuple = field(default_factory=_mail_accounts)
    folder: str = os.environ.get("MAIL_FOLDER", "INBOX")
    poll_seconds: int = _int("MAIL_POLL_SECONDS", 120)
    max_per_poll: int = _int("MAIL_MAX_PER_POLL", 10)
    # Письмо длиннее всё равно не поместится в подсказку осмысленно.
    max_body_chars: int = _int("MAIL_MAX_BODY_CHARS", 4000)
    # Ящик со старыми непрочитанными письмами не должен при первом запуске
    # превратиться в сотню подсказок на давно неактуальное.
    max_age_hours: int = _int("MAIL_MAX_AGE_HOURS", 72)
    ignore_senders: tuple = field(default_factory=lambda: _list("MAIL_IGNORE_SENDERS"))

    @property
    def enabled(self):
        return bool(self.accounts)

    def account(self, name_or_address):
        needle = (name_or_address or "").lower()
        for item in self.accounts:
            if needle in (item.name, item.address):
                return item
        return self.accounts[0] if self.accounts else None


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


CALDAV_PRESETS = {
    "yandex": "https://caldav.yandex.ru",
    "mailru": "https://calendar.mail.ru/principals",
    "icloud": "https://caldav.icloud.com",
    "google": "https://apidata.googleusercontent.com/caldav/v2",
}


@dataclass(frozen=True)
class CalDAVAccount:
    name: str
    user: str
    password: str
    url: str

    @property
    def address(self):
        return self.user.lower()


def _caldav_accounts():
    """CALDAV_ACCOUNTS=yandex → CALDAV_YANDEX_USER, CALDAV_YANDEX_PASSWORD."""
    accounts = []
    for name in _list("CALDAV_ACCOUNTS"):
        key = name.upper().replace("-", "_")
        user = os.environ.get(f"CALDAV_{key}_USER", "").strip()
        password = os.environ.get(f"CALDAV_{key}_PASSWORD", "")
        url = os.environ.get(f"CALDAV_{key}_URL",
                             CALDAV_PRESETS.get(name.lower(), "")).strip()
        if user and password and url:
            accounts.append(CalDAVAccount(name=name.lower(), user=user,
                                          password=password, url=url.rstrip("/")))
    return tuple(accounts)


@dataclass(frozen=True)
class CalendarConfig:
    accounts: tuple = field(default_factory=_caldav_accounts)
    # Дальше горизонта ассистент не заглядывает: это уже не «что у меня сегодня».
    horizon_days: int = _int("CALENDAR_HORIZON_DAYS", 14)
    # Сколько ближайших встреч подмешивать в контекст ответа.
    context_events: int = _int("CALENDAR_CONTEXT_EVENTS", 5)
    refresh_seconds: int = _int("CALENDAR_REFRESH_SECONDS", 600)
    # За сколько предупреждать о встрече.
    remind_minutes: tuple = field(
        default_factory=lambda: tuple(sorted(
            {int(x) for x in _list("CALENDAR_REMIND_MINUTES", ("60", "10")) if
             x.isdigit()}, reverse=True)))
    timeout: int = _int("CALDAV_TIMEOUT", 30)

    @property
    def enabled(self):
        return bool(self.accounts)

    def account(self, name_or_address=None):
        needle = (name_or_address or "").lower()
        for item in self.accounts:
            if needle in (item.name, item.address):
                return item
        return self.accounts[0] if self.accounts else None


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
    email: EmailConfig = field(default_factory=EmailConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    actions: ActionConfig = field(default_factory=ActionConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)


config = Config()
