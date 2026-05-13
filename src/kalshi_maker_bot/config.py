from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(StrEnum):
    SIM = "sim"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mode: Mode = Mode.SIM

    kalshi_api_key_id: str = ""
    kalshi_private_key_path: Path = Path("/etc/kalshi-maker-bot/kalshi_private_key.pem")
    kalshi_base_url: str = "https://api.elections.kalshi.com/trade-api/v2"

    min_ask_cents: Annotated[int, Field(ge=1, le=99)] = 90
    max_ask_cents: Annotated[int, Field(ge=1, le=99)] = 97
    bid_offset_cents: Annotated[int, Field(ge=1, le=2)] = 1
    dollars_per_market: Annotated[float, Field(gt=0)] = 25.0
    min_hours_to_close: Annotated[float, Field(ge=0)] = 24.0
    min_open_interest: Annotated[int, Field(ge=0)] = 1000
    min_recent_volume: Annotated[int, Field(ge=0)] = 100
    cancel_drift_cents: Annotated[int, Field(ge=1)] = 2
    close_buffer_min: Annotated[int, Field(ge=1)] = 10
    refresh_interval_min: Annotated[int, Field(ge=1)] = 5
    catalyst_buffer_min: Annotated[int, Field(ge=0)] = 30

    scan_interval_sec: Annotated[int, Field(ge=10)] = 300
    monitor_interval_sec: Annotated[int, Field(ge=5)] = 60

    db_path: Path = Path("/var/lib/kalshi-maker-bot/state.db")
    event_log_path: Path = Path("/var/log/kalshi-maker-bot/events.jsonl")

    google_credentials_path: Path = Path("/etc/kalshi-maker-bot/google-credentials.json")
    sheets_spreadsheet_id: str = ""
    sheets_tab_name: str = "events"
    sheets_enabled: bool = True

    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_enabled: bool = True

    sim_starting_bankroll_cents: Annotated[int, Field(ge=0)] = 100_000  # $1000

    log_level: str = "INFO"

    @field_validator("max_ask_cents")
    @classmethod
    def _max_above_min(cls, v: int, info) -> int:
        min_v = info.data.get("min_ask_cents")
        if min_v is not None and v < min_v:
            raise ValueError("max_ask_cents must be >= min_ask_cents")
        return v

    @property
    def is_live(self) -> bool:
        return self.mode is Mode.LIVE

    @property
    def is_sim(self) -> bool:
        return self.mode is Mode.SIM


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_for_tests() -> None:
    global _settings
    _settings = None
