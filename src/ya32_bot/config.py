"""Environment-driven settings (pydantic-settings).

Read lazily through :func:`get_settings` so tests can build their own instance
without touching the environment.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    version: str = "1.1.0"

    bot_token: SecretStr = SecretStr("")
    # Telegram ids that are always owners (comma-separated in the env).
    owner_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    database_url: str = "sqlite+aiosqlite:///./data/ya32.db"
    tz: str = "Europe/Kyiv"
    log_level: str = "INFO"
    # Touched every minute by the scheduler; the Docker healthcheck reads its age. Empty = off.
    heartbeat_file: str = ""

    # Bot API 10.1 Rich Messages; falls back to classic HTML automatically when refused.
    rich_messages: bool = True

    # schedule.kpi.ua → api.campus.kpi.ua
    kpi_api_url: str = "https://api.campus.kpi.ua"
    kpi_group_id: str = "3655"
    kpi_autosync: bool = True
    kpi_sync_hour: int = 6

    @field_validator("owner_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.replace(";", ",").split(",") if part.strip()]
        if isinstance(value, int):
            return [value]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
