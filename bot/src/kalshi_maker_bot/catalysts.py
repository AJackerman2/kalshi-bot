from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Kalshi returns "2026-05-13T20:30:00Z" style.
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_within_catalyst_buffer(
    market: dict[str, Any], now: datetime, buffer_min: int
) -> tuple[bool, str | None]:
    """
    A market is in the catalyst buffer if `now` falls within `buffer_min`
    minutes (either side) of a known scheduled event time.

    Kalshi market metadata fields we treat as catalyst anchors:
      - `expected_expiration_time`: when the market expects to resolve
        (e.g. game start for sports, release time for economic prints)
      - any explicit `event_time` if present in metadata
    The market close time is handled separately by the close-buffer rule.
    """
    if buffer_min <= 0:
        return False, None
    delta = timedelta(minutes=buffer_min)
    candidates = [
        ("expected_expiration_time", parse_iso(market.get("expected_expiration_time"))),
        ("event_time", parse_iso(market.get("event_time"))),
    ]
    for label, ts in candidates:
        if ts is None:
            continue
        if abs(ts - now) <= delta:
            return True, f"{label}@{ts.isoformat()}"
    return False, None


def hours_until_close(market: dict[str, Any], now: datetime) -> float | None:
    close = parse_iso(market.get("close_time"))
    if close is None:
        return None
    return (close - now).total_seconds() / 3600.0


def minutes_until_close(market: dict[str, Any], now: datetime) -> float | None:
    h = hours_until_close(market, now)
    return None if h is None else h * 60.0
