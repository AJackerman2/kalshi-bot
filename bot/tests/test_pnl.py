from __future__ import annotations

from kalshi_maker_bot.pnl import (
    order_pnl_cents,
    per_contract_fee_cents,
    per_contract_pnl_cents,
)


def test_fee_curve_is_symmetric_around_half():
    assert per_contract_fee_cents(50) == per_contract_fee_cents(50)
    assert per_contract_fee_cents(10) == per_contract_fee_cents(90)


def test_fee_zero_at_extremes():
    assert per_contract_fee_cents(0) == 0
    assert per_contract_fee_cents(100) == 0


def test_yes_outcome_pnl_includes_fee():
    fee = per_contract_fee_cents(94)
    assert per_contract_pnl_cents(94, "yes") == (100 - 94) - fee


def test_no_outcome_pnl_is_negative_bid_minus_fee():
    fee = per_contract_fee_cents(94)
    assert per_contract_pnl_cents(94, "no") == -94 - fee


def test_order_pnl_scales_with_quantity():
    per = per_contract_pnl_cents(94, "yes")
    assert order_pnl_cents(94, 10, "yes") == per * 10
