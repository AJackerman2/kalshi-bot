from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    ticker            TEXT PRIMARY KEY,
    event_ticker      TEXT,
    title             TEXT,
    close_time        TEXT,
    expected_expiry  TEXT,
    last_seen_at      TEXT NOT NULL,
    last_ask_cents    INTEGER,
    last_bid_cents    INTEGER,
    last_volume       INTEGER,
    last_open_interest INTEGER,
    resolved          INTEGER NOT NULL DEFAULT 0,
    outcome           TEXT
);

CREATE TABLE IF NOT EXISTS sim_orders (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker            TEXT NOT NULL,
    side              TEXT NOT NULL,        -- always 'yes' for this strategy
    action            TEXT NOT NULL,        -- always 'buy' for this strategy
    bid_cents         INTEGER NOT NULL,
    quantity          INTEGER NOT NULL,
    placed_at         TEXT NOT NULL,
    status            TEXT NOT NULL,        -- open | filled | cancelled
    fill_price_cents  INTEGER,
    filled_at         TEXT,
    cancelled_at      TEXT,
    cancel_reason     TEXT,
    pnl_cents         INTEGER,
    resolved_at       TEXT,
    notes             TEXT
);

CREATE INDEX IF NOT EXISTS idx_sim_orders_open
    ON sim_orders(status) WHERE status = 'open';

CREATE INDEX IF NOT EXISTS idx_sim_orders_ticker
    ON sim_orders(ticker);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    kind         TEXT NOT NULL,
    ticker       TEXT,
    order_id     INTEGER,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
"""


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # --- markets ------------------------------------------------------------

    def upsert_market_snapshot(
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
        self._conn.execute(
            """
            INSERT INTO markets(
                ticker, event_ticker, title, close_time, expected_expiry,
                last_seen_at, last_ask_cents, last_bid_cents, last_volume,
                last_open_interest
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker) DO UPDATE SET
                event_ticker = excluded.event_ticker,
                title = excluded.title,
                close_time = excluded.close_time,
                expected_expiry = excluded.expected_expiry,
                last_seen_at = excluded.last_seen_at,
                last_ask_cents = excluded.last_ask_cents,
                last_bid_cents = excluded.last_bid_cents,
                last_volume = excluded.last_volume,
                last_open_interest = excluded.last_open_interest
            """,
            (
                ticker, event_ticker, title, close_time, expected_expiry,
                _utcnow_iso(), ask_cents, bid_cents, volume, open_interest,
            ),
        )

    def mark_market_resolved(self, ticker: str, outcome: str) -> None:
        self._conn.execute(
            "UPDATE markets SET resolved=1, outcome=? WHERE ticker=?",
            (outcome, ticker),
        )

    def get_market(self, ticker: str) -> sqlite3.Row | None:
        cur = self._conn.execute("SELECT * FROM markets WHERE ticker=?", (ticker,))
        return cur.fetchone()

    # --- sim orders ---------------------------------------------------------

    def create_sim_order(
        self, ticker: str, bid_cents: int, quantity: int, notes: str | None = None
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO sim_orders(
                ticker, side, action, bid_cents, quantity, placed_at, status, notes
            ) VALUES (?, 'yes', 'buy', ?, ?, ?, 'open', ?)
            """,
            (ticker, bid_cents, quantity, _utcnow_iso(), notes),
        )
        return int(cur.lastrowid)

    def mark_sim_order_filled(self, order_id: int, fill_price_cents: int) -> None:
        self._conn.execute(
            """
            UPDATE sim_orders
               SET status='filled', fill_price_cents=?, filled_at=?
             WHERE id=? AND status='open'
            """,
            (fill_price_cents, _utcnow_iso(), order_id),
        )

    def mark_sim_order_cancelled(self, order_id: int, reason: str) -> None:
        self._conn.execute(
            """
            UPDATE sim_orders
               SET status='cancelled', cancelled_at=?, cancel_reason=?
             WHERE id=? AND status='open'
            """,
            (_utcnow_iso(), reason, order_id),
        )

    def record_resolution_pnl(self, order_id: int, pnl_cents: int) -> None:
        self._conn.execute(
            "UPDATE sim_orders SET pnl_cents=?, resolved_at=? WHERE id=?",
            (pnl_cents, _utcnow_iso(), order_id),
        )

    def get_open_orders(self) -> list[sqlite3.Row]:
        cur = self._conn.execute("SELECT * FROM sim_orders WHERE status='open'")
        return cur.fetchall()

    def get_open_order_for_ticker(self, ticker: str) -> sqlite3.Row | None:
        cur = self._conn.execute(
            "SELECT * FROM sim_orders WHERE ticker=? AND status='open' LIMIT 1",
            (ticker,),
        )
        return cur.fetchone()

    def get_filled_unresolved_orders(self, ticker: str) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM sim_orders WHERE ticker=? AND status='filled' AND pnl_cents IS NULL",
            (ticker,),
        )
        return cur.fetchall()

    # --- events -------------------------------------------------------------

    def record_event(
        self,
        kind: str,
        payload: dict[str, Any],
        ticker: str | None = None,
        order_id: int | None = None,
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO events(ts, kind, ticker, order_id, payload_json)
            VALUES (?,?,?,?,?)
            """,
            (_utcnow_iso(), kind, ticker, order_id, json.dumps(payload, default=str)),
        )
        return int(cur.lastrowid)
