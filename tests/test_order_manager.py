from __future__ import annotations

from unittest.mock import MagicMock

from kalshi_maker_bot.config import Mode, Settings
from kalshi_maker_bot.db import Database
from kalshi_maker_bot.events import EventBus
from kalshi_maker_bot.order_manager import OrderManager
from kalshi_maker_bot.scanner import Candidate
from kalshi_maker_bot.sheets import EventSink
from kalshi_maker_bot.simulator import Simulator


def _s(tmp_path) -> Settings:
    return Settings(
        mode=Mode.SIM,
        kalshi_api_key_id="x",
        kalshi_private_key_path=tmp_path / "k.pem",
        db_path=tmp_path / "db.sqlite",
        event_log_path=tmp_path / "events.jsonl",
        google_credentials_path=tmp_path / "missing.json",
        sheets_enabled=False,
        bid_offset_cents=1,
        dollars_per_market=25.0,
    )


def test_sim_path_places_order(tmp_path):
    s = _s(tmp_path)
    db = Database(s.db_path)
    events = EventBus(db, EventSink(s))
    client = MagicMock()
    sim = Simulator(s, db, client, events)
    mgr = OrderManager(s, db, client, sim)
    out = mgr.consider_candidate(
        Candidate(ticker="MKT", title="t", ask_cents=95, close_time=None, volume=200, open_interest=2000)
    )
    assert out == "placed_sim"


def test_skips_when_open_order_exists(tmp_path):
    s = _s(tmp_path)
    db = Database(s.db_path)
    events = EventBus(db, EventSink(s))
    client = MagicMock()
    sim = Simulator(s, db, client, events)
    mgr = OrderManager(s, db, client, sim)

    cand = Candidate(ticker="MKT", title="t", ask_cents=95, close_time=None, volume=200, open_interest=2000)
    assert mgr.consider_candidate(cand) == "placed_sim"
    assert mgr.consider_candidate(cand) == "skip_existing_open"
