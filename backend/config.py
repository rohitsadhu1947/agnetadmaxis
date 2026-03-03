"""
Configuration settings for the ADM Platform backend.
Uses pydantic-settings for environment variable management.

DATABASE_URL priority:
  1. DATABASE_URL env var (set in Railway → points to Neon PostgreSQL)
  2. Fallback: SQLite for local development
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "ADM Platform - Axis Max Life Insurance"
    APP_VERSION: str = "2.7.2"
    DEBUG: bool = True

    # Database — default is SQLite for local dev; Railway overrides via env var
    DATABASE_URL: str = "sqlite:///./adm_platform.db"

    @property
    def is_postgres(self) -> bool:
        """True when using PostgreSQL (Neon DB in production)."""
        return self.DATABASE_URL.startswith("postgresql")

    # Anthropic Claude API
    ANTHROPIC_API_KEY: str = ""

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_URL: str = ""

    # WhatsApp Business API (placeholder)
    WHATSAPP_API_URL: str = ""
    WHATSAPP_API_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080,https://adm-agent.vercel.app"

    # Security
    SECRET_KEY: str = "adm-platform-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Agent Telegram Bot (separate bot for agents)
    AGENT_TELEGRAM_BOT_TOKEN: str = ""

    # Feature Flags
    ENABLE_AI_FEATURES: bool = True
    ENABLE_TELEGRAM_BOT: bool = False
    ENABLE_AGENT_BOT: bool = False
    ENABLE_WHATSAPP: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


settings = Settings()
