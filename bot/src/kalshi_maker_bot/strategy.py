from __future__ import annotations

from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class BidPlan:
    ticker: str
    bid_cents: int
    quantity: int
    rationale: str


def compute_bid_cents(ask_cents: int, settings: Settings) -> int:
    """Maker bid sits BID_OFFSET_CENTS below the current ask, clamped to [1, 99]."""
    bid = ask_cents - settings.bid_offset_cents
    return max(1, min(99, bid))


def quantity_for_bid(bid_cents: int, settings: Settings) -> int:
    """Quantity sized for a fixed dollar notional. Each contract costs bid_cents/100."""
    if bid_cents <= 0:
        return 0
    return max(1, int(settings.dollars_per_market // (bid_cents / 100.0)))


def build_bid_plan(ticker: str, ask_cents: int, settings: Settings) -> BidPlan:
    bid = compute_bid_cents(ask_cents, settings)
    qty = quantity_for_bid(bid, settings)
    return BidPlan(
        ticker=ticker,
        bid_cents=bid,
        quantity=qty,
        rationale=f"ask={ask_cents}c offset={settings.bid_offset_cents}c bid={bid}c qty={qty}",
    )
