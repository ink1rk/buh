from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    environment: str = Field(default="development", alias="ENVIRONMENT")
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    publish_enabled: bool = Field(default=False, alias="PUBLISH_ENABLED")
    global_kill_switch: bool = Field(default=True, alias="GLOBAL_KILL_SWITCH")
    sponsored_enabled: bool = Field(default=False, alias="SPONSORED_ENABLED")
    app_bind_host: str = Field(default="127.0.0.1", alias="APP_BIND_HOST")
    app_bind_port: int = Field(default=8787, alias="APP_BIND_PORT")
    app_timezone: str = Field(default="Europe/Moscow", alias="APP_TIMEZONE")
    database_url: str = Field(
        default="postgresql+psycopg://tmn:tmn_test_only@127.0.0.1:5432/tmn_test",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="", alias="REDIS_URL")
    session_secret: str = Field(default="dev-only-not-a-production-secret", alias="SESSION_SECRET")
    github_read_token: str = Field(default="", alias="GITHUB_READ_TOKEN")
    hf_read_token: str = Field(default="", alias="HF_READ_TOKEN")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_test_chat_id: str = Field(default="", alias="TELEGRAM_TEST_CHAT_ID")
    llm_mode: str = Field(default="mock", alias="LLM_MODE")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_model: str = Field(default="", alias="LLM_MODEL")
    media_remote_screenshot_enabled: bool = Field(default=False, alias="MEDIA_REMOTE_SCREENSHOT_ENABLED")
    source_mode: str = Field(default="offline", alias="SOURCE_MODE")
    session_idle_minutes: int = 30
    session_absolute_hours: int = 8
    pilot_manual_approval: bool = True
    auto_approve_enabled: bool = False
    config_dir: Path = ROOT / "configs"
    schema_dir: Path = ROOT / "schemas"
    media_dir: Path = ROOT / "var" / "media"
    backup_dir: Path = ROOT / "var" / "backups"
    login_limit: int = 5
    login_window_seconds: int = 900


def assert_can_boot(settings: Settings) -> None:
    """Production boot is a separate approval. This build refuses it."""
    if settings.environment.strip().lower() == "production":
        raise RuntimeError(
            "ENVIRONMENT=production is refused. DEV_READY does not mean PRODUCTION_APPROVED."
        )
    if settings.llm_mode not in {"mock", "manual", "local"}:
        raise RuntimeError("LLM_MODE must be mock, manual, or local")
    if settings.llm_mode == "local" and not settings.llm_base_url:
        raise RuntimeError("local LLM mode requires an explicitly configured endpoint")
