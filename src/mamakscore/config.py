# Validated environment configuration.
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Shipped as package data so the engine works when pip-installed, not only
# from a source checkout.
DEFAULT_RUBRIC = Path(__file__).parent / "data/mamakscore-v3.yaml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAMAKSCORE_", env_file=".env", extra="ignore")
    mode: Literal["offline", "hosted"] = "offline"
    rubric_path: Path = DEFAULT_RUBRIC
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    vision_model: str | None = None
    expose_provisional_confidence: bool = False
    confidential_processing_authorized: bool = False
    cache_enabled: bool = False
    cache_path: Path = Path(".cache/replay.sqlite3")
    max_concurrency: int = 2
    queue_wait_seconds: float = 0.25
    provider_timeout_seconds: float = 45.0
    request_timeout_seconds: float = 55.0
    max_pdf_bytes: int = 20 * 1024 * 1024
    max_xlsx_bytes: int = 10 * 1024 * 1024
    max_total_bytes: int = 30 * 1024 * 1024

    @model_validator(mode="after")
    def validate_hosted(self) -> "Settings":
        if self.mode == "hosted" and not all((self.llm_base_url, self.llm_api_key, self.llm_model)):
            raise ValueError("hosted mode requires LLM base URL, API key and model")
        if (
            self.max_concurrency < 1
            or self.queue_wait_seconds < 0
            or self.request_timeout_seconds <= 0
        ):
            raise ValueError("capacity and timeout settings must be positive")
        return self
