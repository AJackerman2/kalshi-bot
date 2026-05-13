"""
P&L math for a filled YES buy held to resolution.

Kalshi per-contract trading fee (current public schedule, applied on both buy
and sell legs; we hold to resolution so resolution side is implicit and pays
zero fee):

    fee_cents_per_contract = ceil(0.07 * P * (1 - P) * 100)

where P is the fill price as a fraction (price_cents / 100).  We do NOT model
the maker-rebate program here -- if Kalshi credits maker rebates on these
contracts, real P&L will be slightly better than what we log.  Document any
assumption change before turning MODE=live.
"""

from __future__ import annotations

import math


def per_contract_fee_cents(price_cents: int) -> int:
    p = price_cents / 100.0
    return math.ceil(0.07 * p * (1.0 - p) * 100.0)


def per_contract_pnl_cents(fill_cents: int, outcome: str) -> int:
    """
    Net cents per contract, fee included, given the fill price and the
    resolution outcome ('yes' or 'no').
    """
    fee = per_contract_fee_cents(fill_cents)
    if outcome == "yes":
        gross = 100 - fill_cents
    elif outcome == "no":
        gross = -fill_cents
    else:
        raise ValueError(f"Unknown outcome: {outcome!r}")
    return gross - fee


def order_pnl_cents(fill_cents: int, quantity: int, outcome: str) -> int:
    return per_contract_pnl_cents(fill_cents, outcome) * quantity
