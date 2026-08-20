from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://contentforge:contentforge@localhost:5432/contentforge"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    token_encryption_key: str = ""
    media_root: str = "./data/media"
    jwt_secret: str = "dev-insecure-change-me-not-for-production"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 604800
    public_api_url: str = "http://localhost:8000"
    public_web_url: str = "http://localhost:5173"
    telegram_https_proxy: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
