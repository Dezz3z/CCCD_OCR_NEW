"""Application settings configuration."""
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


def _data_dir() -> Path:
    """`%LOCALAPPDATA%\\COCAS\\data` — the read-write half of §11's layout."""
    return Path(os.environ.get("LOCALAPPDATA", ".")) / "COCAS" / "data"


def _default_dpapi_key_path() -> str:
    """`%LOCALAPPDATA%\\COCAS\\data\\keys\\master.key.dpapi` (§10.3.1, §4.8.1)."""
    return str(_data_dir() / "keys" / "master.key.dpapi")


def _default_vault_dir() -> str:
    """`…\\data\\vault` — every encrypted file the system stores (§12.13)."""
    return str(_data_dir() / "vault")


def _default_templates_dir() -> str:
    """`…\\data\\templates` — the Template Store.

    ⚠️ A **sibling** of the Vault, not inside it (§11). `template_version.
    file_path` is relative to this directory, and the files here are stored
    in the clear: `DocxRenderer` opens them by path, and they contain no
    customer data — only `{{placeholders}}`.
    """
    return str(_data_dir() / "templates")


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

    # Storage (§11 app-data layout, §12.13)
    vault_dir: str = Field(default_factory=_default_vault_dir)
    templates_dir: str = Field(default_factory=_default_templates_dir)

    # Security
    local_token_secret: str = "dev-secret-change-in-production"
    dpapi_key_path: str = Field(default_factory=_default_dpapi_key_path)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
