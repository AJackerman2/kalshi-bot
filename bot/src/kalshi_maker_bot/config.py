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

    min_ask_cents: Annotated[int, Field(ge=1, le=99)] = 82
    max_ask_cents: Annotated[int, Field(ge=1, le=99)] = 97
    bid_offset_cents: Annotated[int, Field(ge=1, le=2)] = 1
    dollars_per_market: Annotated[float, Field(gt=0)] = 25.0
    # Max concurrent open orders sharing one event_ticker.  Kalshi events
    # like bracketed auctions (e.g. KXBNB-26MAY1717-B*) generate dozens of
    # mutually-exclusive sub-markets; bidding YES on multiple at the same
    # price guarantees losses on all but at most one.  Defaults to 1 -- one
    # bid per event at a time.
    max_orders_per_event: Annotated[int, Field(ge=1)] = 1
    min_hours_to_close: Annotated[float, Field(ge=0)] = 0.5
    # Kalshi's /markets list response currently reports open_interest = 0 and
    # volume_24h = 0 across the entire near-term universe (~17k markets); the
    # individual /markets/{ticker} endpoint may have real numbers but we
    # don't fetch it for filtering.  These gates therefore default to 0 --
    # the YES-ask-in-band check carries the liquidity signal.  Override via
    # env if Kalshi fixes the list endpoint and we want a real floor.
    min_open_interest: Annotated[int, Field(ge=0)] = 0
    min_recent_volume: Annotated[int, Field(ge=0)] = 0
    cancel_drift_cents: Annotated[int, Field(ge=1)] = 2
    close_buffer_min: Annotated[int, Field(ge=0)] = 0
    refresh_interval_min: Annotated[int, Field(ge=1)] = 5
    catalyst_buffer_min: Annotated[int, Field(ge=0)] = 30
    # Server-side cap on how far out market close_time can be when fetching
    # the open-market list.  Kalshi's catalog includes hundreds of thousands
    # of long-dated election micro-markets with no trading; filtering by
    # close window shrinks the dataset to actually-tradeable markets.
    scan_close_window_days: Annotated[int, Field(ge=1)] = 30

    scan_interval_sec: Annotated[int, Field(ge=10)] = 300
    monitor_interval_sec: Annotated[int, Field(ge=5)] = 60

    db_path: Path = Path("/var/lib/kalshi-maker-bot/state.db")
    event_log_path: Path = Path("/var/log/kalshi-maker-bot/events.jsonl")

    google_credentials_path: Path = Path("/etc/kalshi-maker-bot/google-credentials.json")
    sheets_spreadsheet_id: str = ""
    sheets_tab_name: str = "events"
    sheets_enabled: bool = True

    pg_database_url: str = ""
    pg_mirror_enabled: bool = True

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
