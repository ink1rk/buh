import os
from dataclasses import dataclass

from .policy import normalize_timezone


@dataclass(frozen=True)
class Settings:
    database_url: str
    telegram_token: str
    owners: frozenset[int]
    timezone: str
    polling: bool
    llm_enabled: bool = False
    bridge_url: str = ''
    bridge_token: str = ''
    litellm_url: str = ''
    litellm_key: str = ''
    calendar_provider: str = ''
    calendar_providers: tuple = ('google', 'yandex')
    email_provider: str = ''
    launcher_enabled: bool = False
    app_image: str = ''
    local_transcriber: str = ''

    @classmethod
    def from_env(cls):
        timezone = normalize_timezone(os.getenv('OWNER_TIMEZONE', ''))
        selected = tuple(item.strip() for item in os.getenv('CALENDAR_PROVIDERS', 'google,yandex').split(',') if item.strip())
        if any(item not in ('google', 'yandex') for item in selected):
            raise ValueError('CALENDAR_PROVIDERS must be google and/or yandex')
        owners = frozenset(int(x) for x in os.getenv('ALLOWED_USER_IDS', '').split(',') if x.strip())
        if not owners:
            raise ValueError('ALLOWED_USER_IDS must not be empty')
        token = os.getenv('TELEGRAM_TOKEN', '')
        polling = os.getenv('POLLING_ENABLED', 'false').lower() == 'true'
        if polling and not token:
            raise ValueError('Polling requires TELEGRAM_TOKEN')
        llm = os.getenv('LLM_ENABLED', 'false').lower() == 'true'
        bridge_url = os.getenv('CURSOR_BRIDGE_URL', '')
        bridge_token = os.getenv('CURSOR_BRIDGE_TOKEN', '')
        if llm and (not bridge_url or not bridge_token):
            raise ValueError('LLM requires an authenticated internal bridge')
        launcher = os.getenv('LAUNCHER_ENABLED', 'false').lower() == 'true'
        app_image = os.getenv('APP_IMAGE', '')
        if launcher and '@sha256:' not in app_image:
            raise ValueError('Launcher requires a pinned APP_IMAGE')
        return cls(os.environ['DATABASE_URL'], token, owners, timezone, polling, llm, bridge_url, bridge_token,
                   os.getenv('LITELLM_URL', ''), os.getenv('LITELLM_MASTER_KEY', ''),
                   os.getenv('CALENDAR_PROVIDER', ''), selected or ('google', 'yandex'), os.getenv('EMAIL_PROVIDER', ''),
                   launcher, app_image, os.getenv('LOCAL_TRANSCRIBER', ''))

