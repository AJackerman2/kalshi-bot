"""
Postgres mirror for the Vercel dashboard.  Bot's source of truth remains
the local SQLite DB; this module fans every state change to a hosted
Postgres (currently Neon).

Best-effort by design: a Postgres write failure logs a warning and lets
the bot keep running.  Mirror rows are id-keyed upserts, so a transient
failure self-heals on the next state change.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Settings
from .logging_setup import get_logger

log = get_logger(__name__)


class _NullPgMirror:
    enabled = False

    def upsert_market(self, *_: Any, **__: Any) -> None: ...
    def upsert_sim_order(self, *_: Any, **__: Any) -> None: ...
    def emit_event(self, *_: Any, **__: Any) -> None: ...
    def close(self) -> None: ...


class PgMirror:
    """
    Lazy psycopg connection.  Reconnects on transient failures via tenacity.
    Methods catch on top-level errors; they never raise into the bot.
    """

    enabled = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._conn = None  # psycopg.Connection

    def _ensure_conn(self):
        if self._conn is None or self._conn.closed:
            import psycopg

            self._conn = psycopg.connect(
                self._settings.pg_database_url,
                autocommit=True,
                connect_timeout=10,
            )
        return self._conn

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            with contextlib.suppress(Exception):
                self._conn.close()
        self._conn = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def _execute(self, sql: str, params: tuple) -> None:
        conn = self._ensure_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params)

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
        sql = """
            INSERT INTO kalshi.markets (
                ticker, event_ticker, title, close_time, expected_expiry,
                last_seen_at, last_ask_cents, last_bid_cents,
                last_volume, last_open_interest
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (ticker) DO UPDATE SET
                event_ticker = EXCLUDED.event_ticker,
                title = EXCLUDED.title,
                close_time = EXCLUDED.close_time,
                expected_expiry = EXCLUDED.expected_expiry,
                last_seen_at = EXCLUDED.last_seen_at,
                last_ask_cents = EXCLUDED.last_ask_cents,
                last_bid_cents = EXCLUDED.last_bid_cents,
                last_volume = EXCLUDED.last_volume,
                last_open_interest = EXCLUDED.last_open_interest
        """
        params = (
            ticker, event_ticker, title, close_time, expected_expiry,
            datetime.now(UTC), ask_cents, bid_cents, volume, open_interest,
        )
        try:
            self._execute(sql, params)
        except Exception as exc:
            log.warning("pg_market_upsert_failed", ticker=ticker, error=str(exc))

    def upsert_sim_order(self, row: sqlite3.Row | dict[str, Any]) -> None:
        d = dict(row) if not isinstance(row, dict) else row
        sql = """
            INSERT INTO kalshi.sim_orders (
                id, ticker, side, action, bid_cents, quantity, placed_at,
                status, fill_price_cents, filled_at, cancelled_at,
                cancel_reason, pnl_cents, resolved_at, notes, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                ticker = EXCLUDED.ticker,
                side = EXCLUDED.side,
                action = EXCLUDED.action,
                bid_cents = EXCLUDED.bid_cents,
                quantity = EXCLUDED.quantity,
                placed_at = EXCLUDED.placed_at,
                status = EXCLUDED.status,
                fill_price_cents = EXCLUDED.fill_price_cents,
                filled_at = EXCLUDED.filled_at,
                cancelled_at = EXCLUDED.cancelled_at,
                cancel_reason = EXCLUDED.cancel_reason,
                pnl_cents = EXCLUDED.pnl_cents,
                resolved_at = EXCLUDED.resolved_at,
                notes = EXCLUDED.notes,
                updated_at = EXCLUDED.updated_at
        """
        params = (
            int(d["id"]), d["ticker"], d.get("side", "yes"), d.get("action", "buy"),
            int(d["bid_cents"]), int(d["quantity"]), d["placed_at"], d["status"],
            d.get("fill_price_cents"), d.get("filled_at"), d.get("cancelled_at"),
            d.get("cancel_reason"), d.get("pnl_cents"), d.get("resolved_at"),
            d.get("notes"), datetime.now(UTC),
        )
        try:
            self._execute(sql, params)
        except Exception as exc:
            log.warning("pg_order_upsert_failed", id=int(d["id"]), error=str(exc))

    def emit_event(
        self,
        event_id: int,
        ts: str,
        kind: str,
        ticker: str | None,
        order_id: int | None,
        payload: dict[str, Any],
    ) -> None:
        sql = """
            INSERT INTO kalshi.events (id, ts, kind, ticker, order_id, payload)
            VALUES (%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (id) DO NOTHING
        """
        params = (event_id, ts, kind, ticker, order_id, json.dumps(payload, default=str))
        try:
            self._execute(sql, params)
        except Exception as exc:
            log.warning("pg_event_emit_failed", kind=kind, error=str(exc))


def make_mirror(settings: Settings):
    if not settings.pg_mirror_enabled:
        return _NullPgMirror()
    if not settings.pg_database_url:
        log.warning("pg_mirror_disabled_missing_dsn")
        return _NullPgMirror()
    return PgMirror(settings)
