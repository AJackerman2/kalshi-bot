from __future__ import annotations

from datetime import timedelta

from kalshi_maker_bot.config import Mode, Settings
from kalshi_maker_bot.scanner import filter_candidates


def _s(**kw) -> Settings:
    base = dict(
        mode=Mode.SIM,
        min_ask_cents=90,
        max_ask_cents=97,
        min_hours_to_close=24,
        min_open_interest=1000,
        min_recent_volume=100,
        catalyst_buffer_min=30,
    )
    base.update(kw)
    return Settings(**base)


def test_ask_in_band_passes(market_factory, now_utc):
    s = _s()
    m = market_factory(event_ticker="TEST")
    cands, _ = filter_candidates([m], {m["ticker"]: 95}, s, now_utc)
    assert len(cands) == 1
    assert cands[0].ask_cents == 95
    assert cands[0].event_ticker == "TEST"


def test_ask_out_of_band_rejected(market_factory, now_utc):
    s = _s()
    m = market_factory()
    _, rejs = filter_candidates([m], {m["ticker"]: 80}, s, now_utc)
    assert any("ask_out_of_band" in r.reason for r in rejs)


def test_low_liquidity_rejected(market_factory, now_utc):
    s = _s()
    m = market_factory(open_interest=10, volume_24h=10)
    _, rejs = filter_candidates([m], {m["ticker"]: 95}, s, now_utc)
    assert any(r.reason.startswith("oi_low") for r in rejs)


def test_close_too_soon_rejected(market_factory, now_utc):
    s = _s()
    near = (now_utc + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    m = market_factory(close_time=near, expected_expiration_time=near)
    _, rejs = filter_candidates([m], {m["ticker"]: 95}, s, now_utc)
    assert any("close_too_soon" in r.reason for r in rejs)


def test_catalyst_buffer_rejected(market_factory, now_utc):
    s = _s()
    soon = (now_utc + timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
    far_close = (now_utc + timedelta(hours=72)).isoformat().replace("+00:00", "Z")
    m = market_factory(close_time=far_close, expected_expiration_time=soon)
    _, rejs = filter_candidates([m], {m["ticker"]: 95}, s, now_utc)
    assert any(r.reason.startswith("catalyst") for r in rejs)


def test_no_ask_rejected(market_factory, now_utc):
    s = _s()
    m = market_factory()
    _, rejs = filter_candidates([m], {m["ticker"]: None}, s, now_utc)
    assert any(r.reason == "no_ask_in_orderbook" for r in rejs)
