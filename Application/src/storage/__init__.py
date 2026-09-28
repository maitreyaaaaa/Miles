"""Shared persistence configuration for local and PostgreSQL-backed stores."""

from src.config import config


def use_postgres_storage() -> bool:
    """Select PostgreSQL when configured and forbid file storage in production."""
    if config.database_url:
        return True
    if config.app_environment == "production":
        raise RuntimeError("DATABASE_URL is required when APP_ENV=production.")
    return False
