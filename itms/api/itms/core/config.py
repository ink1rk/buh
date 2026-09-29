from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация приложения. Все значения переопределяются переменными окружения."""

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="ITMS_", extra="ignore", case_sensitive=False
    )

    app_name: str = "ITMS"
    env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://itms:itms@localhost:5432/itms"
    database_pool_size: int = 10
    database_max_overflow: int = 10
    database_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    # Сессии и безопасность
    session_cookie: str = "itms_session"
    csrf_cookie: str = "itms_csrf"
    csrf_header: str = "X-CSRF-Token"
    session_ttl_hours: int = 12
    session_idle_timeout_minutes: int = 240
    cookie_secure: bool = False
    cookie_domain: str | None = None
    login_rate_limit: int = 10
    login_rate_window_seconds: int = 300
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Первичная установка: владелец системы
    bootstrap_owner_email: str = "owner@itms.local"
    bootstrap_owner_password: str | None = None
    bootstrap_owner_name: str = "Владелец системы"

    # Хранилище файлов
    storage_backend: Literal["s3", "local"] = "s3"
    s3_endpoint: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "itms"
    s3_access_key: str = "itms"
    s3_secret_key: str = "itms-secret"
    s3_use_ssl: bool = False
    local_storage_path: str = "./var/files"
    upload_max_bytes: int = 100 * 1024 * 1024

    # Локализация
    default_locale: Literal["ru", "en"] = "ru"

    # Значения по умолчанию для электрической модели (настраиваются в справочнике)
    power_voltage_single_v: float = 230.0
    power_voltage_three_v: float = 400.0
    power_factor_default: float = 0.95
    power_derating_default: float = 0.8
    power_reserve_target_pct: float = 20.0
    power_measurement_ttl_days: int = 180
    power_phase_disbalance_limit_pct: float = 15.0

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "+psycopg2")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
