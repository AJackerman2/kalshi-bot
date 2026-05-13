"""
Supabase mirror.  The bot's source of truth remains the local SQLite DB;
this module fans every state change to a Supabase Postgres so the
dashboard has something to read.

Best-effort by design: a Supabase write failure logs a warning and lets
the bot keep running.  The reconciler (`reconcile()`) re-pushes any drift
on the next scan cycle.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Settings
from .logging_setup import get_logger

log = get_logger(__name__)

SCHEMA = "kalshi"


class _NullSupabaseWriter:
    enabled = False

    def upsert_market(self, *_: Any, **__: Any) -> None: ...
    def upsert_sim_order(self, *_: Any, **__: Any) -> None: ...
    def emit_event(self, *_: Any, **__: Any) -> None: ...
    def reconcile(self, *_: Any, **__: Any) -> None: ...


class SupabaseWriter:
    """
    Lazy supabase-py client.  Construction is cheap; the network client is
    only created on first use.  Methods catch and log; never raise.
    """

    enabled = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from supabase import create_client

            self._client = create_client(
                self._settings.supabase_url,
                self._settings.supabase_service_key,
            )
        return self._client

    def _table(self, name: str):
        # `schema()` returns a builder scoped to `kalshi.*`.
        return self._ensure_client().schema(SCHEMA).table(name)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def _upsert(self, table: str, row: dict[str, Any], on_conflict: str = "id") -> None:
        self._table(table).upsert(row, on_conflict=on_conflict).execute()

    def upsert_market(
        self,
        ticker: str,
        event_ticker: str | None,
        title: str | None,
        close_time: str | None,
        expected_expiry: str | None,
        ask_cents: int | None,
        bid_cents: int | None,
        volume: int | None,
        open_interest: int | None,
    ) -> None:
        row = {
            "ticker": ticker,
            "event_ticker": event_ticker,
            "title": title,
            "close_time": close_time,
            "expected_expiry": expected_expiry,
            "last_seen_at": datetime.utcnow().isoformat() + "Z",
            "last_ask_cents": ask_cents,
            "last_bid_cents": bid_cents,
            "last_volume": volume,
            "last_open_interest": open_interest,
        }
        try:
            self._upsert("markets", row, on_conflict="ticker")
        except Exception as exc:
            log.warning("supabase_market_upsert_failed", ticker=ticker, error=str(exc))

    def upsert_sim_order(self, row: sqlite3.Row | dict[str, Any]) -> None:
        d = dict(row) if not isinstance(row, dict) else row
        payload = {
            "id": int(d["id"]),
            "ticker": d["ticker"],
            "side": d.get("side", "yes"),
            "action": d.get("action", "buy"),
            "bid_cents": int(d["bid_cents"]),
            "quantity": int(d["quantity"]),
            "placed_at": d["placed_at"],
            "status": d["status"],
            "fill_price_cents": d.get("fill_price_cents"),
            "filled_at": d.get("filled_at"),
            "cancelled_at": d.get("cancelled_at"),
            "cancel_reason": d.get("cancel_reason"),
            "pnl_cents": d.get("pnl_cents"),
            "resolved_at": d.get("resolved_at"),
            "notes": d.get("notes"),
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        try:
            self._upsert("sim_orders", payload, on_conflict="id")
        except Exception as exc:
            log.warning("supabase_order_upsert_failed", id=payload["id"], error=str(exc))

    def emit_event(
        self,
        event_id: int,
        ts: str,
        kind: str,
        ticker: str | None,
        order_id: int | None,
        payload: dict[str, Any],
    ) -> None:
        row = {
            "id": event_id,
            "ts": ts,
            "kind": kind,
            "ticker": ticker,
            "order_id": order_id,
            "payload": payload,
        }
        try:
            self._upsert("events", row, on_conflict="id")
        except Exception as exc:
            log.warning("supabase_event_emit_failed", kind=kind, error=str(exc))


def make_writer(settings: Settings):
    if not settings.supabase_enabled:
        return _NullSupabaseWriter()
    if not settings.supabase_url or not settings.supabase_service_key:
        log.warning("supabase_disabled_missing_creds")
        return _NullSupabaseWriter()
    return SupabaseWriter(settings)
