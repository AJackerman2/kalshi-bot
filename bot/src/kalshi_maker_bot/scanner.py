from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .catalysts import hours_until_close, is_within_catalyst_buffer
from .config import Settings


@dataclass(frozen=True)
class Candidate:
    ticker: str
    title: str
    ask_cents: int
    close_time: str | None
    volume: int
    open_interest: int
    event_ticker: str | None


@dataclass(frozen=True)
class Rejection:
    ticker: str
    reason: str


def filter_candidates(
    markets: Iterable[dict[str, Any]],
    ask_lookup: dict[str, int | None],
    settings: Settings,
    now: datetime,
) -> tuple[list[Candidate], list[Rejection]]:
    """
    Apply candidate filters.  `ask_lookup` maps ticker -> derived YES ask cents
    (from `KalshiClient.get_orderbook`).  Rejections are returned for logging.
    """
    cands: list[Candidate] = []
    rejs: list[Rejection] = []
    for m in markets:
        ticker = m.get("ticker")
        if not ticker:
            continue
        ask = ask_lookup.get(ticker)
        if ask is None:
            rejs.append(Rejection(ticker, "no_ask_in_orderbook"))
            continue
        if not (settings.min_ask_cents <= ask <= settings.max_ask_cents):
            rejs.append(Rejection(ticker, f"ask_out_of_band:{ask}"))
            continue
        hrs = hours_until_close(m, now)
        if hrs is None:
            rejs.append(Rejection(ticker, "no_close_time"))
            continue
        if hrs < settings.min_hours_to_close:
            rejs.append(Rejection(ticker, f"close_too_soon:{hrs:.1f}h"))
            continue
        oi = int(m.get("open_interest") or 0)
        if oi < settings.min_open_interest:
            rejs.append(Rejection(ticker, f"oi_low:{oi}"))
            continue
        vol = int(m.get("volume_24h") or m.get("volume") or 0)
        if vol < settings.min_recent_volume:
            rejs.append(Rejection(ticker, f"vol_low:{vol}"))
            continue
        in_buf, label = is_within_catalyst_buffer(m, now, settings.catalyst_buffer_min)
        if in_buf:
            rejs.append(Rejection(ticker, f"catalyst:{label}"))
            continue
        cands.append(
            Candidate(
                ticker=ticker,
                title=str(m.get("title") or ""),
                ask_cents=ask,
                close_time=m.get("close_time"),
                volume=vol,
                open_interest=oi,
                event_ticker=m.get("event_ticker"),
            )
        )
    return cands, rejs
