"""Application settings configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment and config files."""

    # Database
    database_url: str = "postgresql+asyncpg://cocas:cocas@localhost:55432/cocas"
    database_echo: bool = False

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_workers: int = 1  # ⭐ CRITICAL: Single worker only

    # Logging
    log_level: str = "INFO"
    log_dir: str = "./logs"

    # OCR
    ocr_models_dir: str = "./resources/ocr-models"

    # Security
    local_token_secret: str = "dev-secret-change-in-production"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
