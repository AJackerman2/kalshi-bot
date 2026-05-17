from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from kalshi_maker_bot.config import Mode, Settings
from kalshi_maker_bot.db import Database
from kalshi_maker_bot.events import EventBus
from kalshi_maker_bot.kalshi_client import OrderbookSnapshot
from kalshi_maker_bot.scanner import Candidate
from kalshi_maker_bot.sheets import EventSink
from kalshi_maker_bot.simulator import Simulator, decide_for_open_order
from kalshi_maker_bot.strategy import build_bid_plan


def _settings(tmp_path, **overrides) -> Settings:
    base = dict(
        mode=Mode.SIM,
        kalshi_api_key_id="x",
        kalshi_private_key_path=tmp_path / "k.pem",
        db_path=tmp_path / "db.sqlite",
        event_log_path=tmp_path / "events.jsonl",
        google_credentials_path=tmp_path / "missing.json",
        sheets_enabled=False,
        bid_offset_cents=1,
        dollars_per_market=25.0,
        cancel_drift_cents=2,
        close_buffer_min=10,
        refresh_interval_min=5,
    )
    base.update(overrides)
    return Settings(**base)


def _ob(ticker: str, ask: int | None) -> OrderbookSnapshot:
    return OrderbookSnapshot(
        ticker=ticker,
        yes_bid_cents=None,
        yes_ask_cents=ask,
        yes_book=[],
        no_book=[],
    )


def test_fill_when_ask_drops_to_bid(now_utc, tmp_path):
    s = _settings(tmp_path)
    placed = now_utc - timedelta(minutes=1)
    d = decide_for_open_order(
        order_bid_cents=94, placed_at=placed, ob=_ob("T", 94),
        market={"close_time": (now_utc + timedelta(hours=48)).isoformat()},
        settings=s, now=now_utc,
    )
    assert d.kind == "fill"
    assert d.fill_price_cents == 94


def test_drift_cancel(now_utc, tmp_path):
    s = _settings(tmp_path)
    placed = now_utc - timedelta(minutes=1)
    d = decide_for_open_order(
        order_bid_cents=94, placed_at=placed, ob=_ob("T", 97),
        market={"close_time": (now_utc + timedelta(hours=48)).isoformat()},
        settings=s, now=now_utc,
    )
    assert d.kind == "cancel" and d.reason.startswith("drift")


def test_close_buffer_cancel_takes_priority(now_utc, tmp_path):
    s = _settings(tmp_path)
    placed = now_utc - timedelta(seconds=30)
    market_close_soon = (now_utc + timedelta(minutes=5)).isoformat()
    # ask at our bid would normally fill, but close-buffer comes first
    d = decide_for_open_order(
        order_bid_cents=94, placed_at=placed, ob=_ob("T", 94),
        market={"close_time": market_close_soon},
        settings=s, now=now_utc,
    )
    assert d.kind == "cancel" and d.reason.startswith("close_buffer")


def test_refresh_age_cancel(now_utc, tmp_path):
    s = _settings(tmp_path, refresh_interval_min=5)
    placed = now_utc - timedelta(minutes=6)
    d = decide_for_open_order(
        order_bid_cents=94, placed_at=placed, ob=_ob("T", 95),
        market={"close_time": (now_utc + timedelta(hours=48)).isoformat()},
        settings=s, now=now_utc,
    )
    assert d.kind == "cancel" and d.reason.startswith("refresh")


def test_hold_when_within_drift_and_fresh(now_utc, tmp_path):
    s = _settings(tmp_path)
    placed = now_utc - timedelta(minutes=1)
    d = decide_for_open_order(
        order_bid_cents=94, placed_at=placed, ob=_ob("T", 95),
        market={"close_time": (now_utc + timedelta(hours=48)).isoformat()},
        settings=s, now=now_utc,
    )
    assert d.kind == "hold"


def test_end_to_end_sim_lifecycle(tmp_path, now_utc):
    s = _settings(tmp_path)
    db = Database(s.db_path)
    sink = EventSink(s)
    events = EventBus(db, sink)

    client = MagicMock()
    client.get_orderbook.return_value = _ob("MKT", 94)
    client.get_market.return_value = {
        "market": {"close_time": (now_utc + timedelta(hours=48)).isoformat()}
    }

    sim = Simulator(s, db, client, events)
    cand = Candidate(
        ticker="MKT", title="t", ask_cents=95, close_time=None, volume=200, open_interest=2000,
        event_ticker=None,
    )
    plan = build_bid_plan(cand.ticker, cand.ask_cents, s)
    order_id = sim.place_sim_order(plan, cand.ask_cents)
    assert order_id > 0

    emitted = sim.step_open_orders(now=now_utc + timedelta(seconds=30))
    fills = [e for e in emitted if e["kind"] == "fill"]
    assert len(fills) == 1
    assert fills[0]["fill_price_cents"] == plan.bid_cents

    sim.resolve_market("MKT", "yes")
    settled = db.get_filled_unresolved_orders("MKT")
    assert settled == []
