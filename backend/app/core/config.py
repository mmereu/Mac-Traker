"""Application configuration."""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database (SQLite for development, PostgreSQL for production)
    database_url: str = "sqlite:///./mactraker.db"

    # SNMP
    snmp_community: str = "public"
    snmp_timeout: int = 5
    snmp_retries: int = 2

    # Discovery
    discovery_interval_minutes: int = 15
    discovery_batch_size: int = 50

    # Data Retention
    history_retention_days: int = 90

    # Telegram
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # Alerts
    alert_new_mac_enabled: bool = True
    alert_mac_move_enabled: bool = True
    alert_mac_disappear_enabled: bool = True
    alert_mac_disappear_hours: int = 24
    alert_port_mac_threshold: int = 10

    # OUI
    oui_database_path: str = "./data/oui.txt"
    oui_update_interval_days: int = 30
    oui_fallback_api_url: str = "https://api.macvendors.com"

    # Security
    secret_key: str = "change-me-in-production"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
