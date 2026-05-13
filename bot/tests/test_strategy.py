from __future__ import annotations

from kalshi_maker_bot.config import Mode, Settings
from kalshi_maker_bot.strategy import build_bid_plan, compute_bid_cents, quantity_for_bid


def _s(**kw) -> Settings:
    return Settings(mode=Mode.SIM, **kw)


def test_bid_is_offset_below_ask():
    s = _s(bid_offset_cents=1, dollars_per_market=10.0)
    assert compute_bid_cents(95, s) == 94
    s2 = _s(bid_offset_cents=2, dollars_per_market=10.0)
    assert compute_bid_cents(95, s2) == 93


def test_bid_clamped_to_legal_range():
    s = _s(bid_offset_cents=2, dollars_per_market=10.0)
    assert compute_bid_cents(2, s) == 1   # never below 1c
    assert compute_bid_cents(99, s) == 97


def test_quantity_from_fixed_dollars():
    s = _s(dollars_per_market=25.0)
    # at 94c, 25 / 0.94 = 26.59 -> 26
    assert quantity_for_bid(94, s) == 26


def test_build_bid_plan_assembles_fields():
    s = _s(bid_offset_cents=1, dollars_per_market=25.0)
    plan = build_bid_plan("TEST", 95, s)
    assert plan.ticker == "TEST"
    assert plan.bid_cents == 94
    assert plan.quantity == 26
    assert "ask=95c" in plan.rationale
