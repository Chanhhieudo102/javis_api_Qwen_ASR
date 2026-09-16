"""Application settings configuration."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parents[3]
RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_env: str = os.getenv("APP_ENV", "dev")
    debug: bool = os.getenv("DEBUG", "true").lower() == "true"

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/app_db"
    )

    # JWT
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "your-secret-key")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    refresh_token_expire_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # Locale
    default_locale: str = "en"
    supported_locales: list[str] = ["en", "ja", "vi"]
    error_dir: str = str(RESOURCE_DIR / "errors")
    validation_dir: str = str(RESOURCE_DIR / "validations")

    class Config:
        """Pydantic settings configuration."""

        env_file = BASE_DIR / ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
