from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Personal Finance AI"
    app_version: str = "1.0.0"
    debug: bool = True
    api_prefix: str = "/api/v1"

    # Paths — on Ubuntu/Docker set DATA_DIR=/app/database
    data_dir: Path = Path(__file__).resolve().parents[3] / "database"
    database_url: str = ""
    chroma_path: Path | None = None

    # Security
    secret_key: str = "change-me-in-production-use-openssl-rand"
    encryption_key: str = ""
    # Пустой токен выключает точку MCP целиком: среди её инструментов есть
    # пишущие, а другой защиты у этого приложения нет.
    mcp_token: str = ""

    # AI
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    vision_model: str = "gpt-4o-mini"

    # Показательный набор данных на пустой базе. По умолчанию выключен:
    # приложение о собственных деньгах не должно начинаться с чужих.
    seed_demo: bool = False

    # User defaults
    default_user_name: str = "Кирилл"
    default_currency: str = "RUB"
    timezone: str = "Europe/Moscow"

    # CORS — in production nginx same-origin, * is fine behind proxy
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost",
        "http://127.0.0.1",
    ]

    def model_post_init(self, __context: object) -> None:
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.database_url:
            db_path = self.data_dir / "finance.db"
            # 4 slashes for absolute path on Linux
            self.database_url = f"sqlite+aiosqlite:///{db_path}"
        if self.chroma_path is None:
            self.chroma_path = self.data_dir / "chroma"
        else:
            self.chroma_path = Path(self.chroma_path)
        self.chroma_path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
