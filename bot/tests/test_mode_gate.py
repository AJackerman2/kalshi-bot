from __future__ import annotations

import pytest

from kalshi_maker_bot.config import Mode, Settings
from kalshi_maker_bot.kalshi_client import KalshiClient, SimModeRefused


def _sim_settings(tmp_path) -> Settings:
    return Settings(
        mode=Mode.SIM,
        kalshi_api_key_id="x",
        kalshi_private_key_path=tmp_path / "k.pem",
        db_path=tmp_path / "db.sqlite",
        event_log_path=tmp_path / "events.jsonl",
        google_credentials_path=tmp_path / "missing.json",
        sheets_enabled=False,
    )


def test_place_order_refuses_in_sim(tmp_path):
    settings = _sim_settings(tmp_path)
    client = KalshiClient(settings)
    with pytest.raises(SimModeRefused):
        client.place_order(
            ticker="TEST", side="yes", action="buy",
            price_cents=90, count=1, client_order_id="c1",
        )


def test_cancel_order_refuses_in_sim(tmp_path):
    settings = _sim_settings(tmp_path)
    client = KalshiClient(settings)
    with pytest.raises(SimModeRefused):
        client.cancel_order("some-order-id")


def test_order_manager_refuses_live(tmp_path, monkeypatch):
    from kalshi_maker_bot.db import Database
    from kalshi_maker_bot.events import EventBus
    from kalshi_maker_bot.order_manager import OrderManager
    from kalshi_maker_bot.scanner import Candidate
    from kalshi_maker_bot.sheets import EventSink
    from kalshi_maker_bot.simulator import Simulator

    settings = _sim_settings(tmp_path).model_copy(update={"mode": Mode.LIVE})
    db = Database(settings.db_path)
    sink = EventSink(settings)
    events = EventBus(db, sink)
    client = KalshiClient(settings)
    sim = Simulator(settings, db, client, events)
    mgr = OrderManager(settings, db, client, sim)
    cand = Candidate(
        ticker="T", title="t", ask_cents=95, close_time=None, volume=100, open_interest=2000,
        event_ticker=None,
    )
    with pytest.raises(NotImplementedError):
        mgr.consider_candidate(cand)


def test_simulator_refuses_in_live_mode(tmp_path):
    from kalshi_maker_bot.db import Database
    from kalshi_maker_bot.events import EventBus
    from kalshi_maker_bot.sheets import EventSink
    from kalshi_maker_bot.simulator import Simulator
    from kalshi_maker_bot.strategy import BidPlan

    settings = _sim_settings(tmp_path).model_copy(update={"mode": Mode.LIVE})
    db = Database(settings.db_path)
    events = EventBus(db, EventSink(settings))
    client = KalshiClient(settings)
    sim = Simulator(settings, db, client, events)
    plan = BidPlan(ticker="T", bid_cents=94, quantity=10, rationale="r")
    with pytest.raises(RuntimeError):
        sim.place_sim_order(plan, ask_cents=95)
