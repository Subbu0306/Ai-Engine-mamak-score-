"""Configuration loader and system environment settings."""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    mode: str = Field(default_factory=lambda: os.getenv("MAMAK_MODE", "offline"))
    provider: str = Field(default_factory=lambda: os.getenv("MAMAK_AI_PROVIDER", "offline"))
    openai_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_model: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"))
    cache_enabled: bool = Field(default_factory=lambda: os.getenv("MAMAK_CACHE_ENABLED", "true").lower() in ("true", "1"))
    cache_db_path: Path = Field(default_factory=lambda: Path(os.getenv("MAMAK_CACHE_DB", ".cache/mamakscore.sqlite")))
    max_concurrency: int = Field(default_factory=lambda: int(os.getenv("MAMAK_MAX_CONCURRENCY", "4")))
    expose_confidence: bool = Field(default_factory=lambda: os.getenv("MAMAK_EXPOSE_CONFIDENCE", "true").lower() in ("true", "1"))


def get_settings() -> Settings:
    return Settings()