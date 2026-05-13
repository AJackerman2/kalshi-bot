from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from kalshi_maker_bot.config import Mode, Settings
from kalshi_maker_bot.db import Database
from kalshi_maker_bot.events import EventBus
from kalshi_maker_bot.sheets import EventSink


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    return Settings(
        mode=Mode.SIM,
        kalshi_api_key_id="test-key",
        kalshi_private_key_path=tmp_path / "missing.pem",
        kalshi_base_url="https://example.invalid/trade-api/v2",
        db_path=tmp_path / "state.db",
        event_log_path=tmp_path / "events.jsonl",
        google_credentials_path=tmp_path / "missing-creds.json",
        sheets_spreadsheet_id="",
        sheets_enabled=False,
        log_level="WARNING",
    )


@pytest.fixture
def db(tmp_settings: Settings) -> Database:
    return Database(tmp_settings.db_path)


@pytest.fixture
def events(tmp_settings: Settings, db: Database) -> EventBus:
    sink = EventSink(tmp_settings)
    return EventBus(db, sink)


@pytest.fixture
def market_factory(now_utc):
    def _make(**overrides: Any) -> dict[str, Any]:
        close = (now_utc + timedelta(hours=48)).isoformat().replace("+00:00", "Z")
        base = {
            "ticker": "TEST-MKT-1",
            "event_ticker": "TEST",
            "title": "Test market",
            "close_time": close,
            "expected_expiration_time": close,
            "volume_24h": 500,
            "open_interest": 2000,
            "status": "open",
        }
        base.update(overrides)
        return base

    return _make
