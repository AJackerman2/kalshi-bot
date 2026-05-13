from __future__ import annotations

from unittest.mock import MagicMock

from kalshi_maker_bot.config import Mode, Settings
from kalshi_maker_bot.pg_mirror import PgMirror, _NullPgMirror, make_mirror


def _s(tmp_path, **overrides) -> Settings:
    base = dict(
        mode=Mode.SIM,
        kalshi_api_key_id="x",
        kalshi_private_key_path=tmp_path / "k.pem",
        db_path=tmp_path / "db.sqlite",
        event_log_path=tmp_path / "events.jsonl",
        google_credentials_path=tmp_path / "creds.json",
        sheets_enabled=False,
        pg_mirror_enabled=True,
        pg_database_url="postgresql://user:pw@localhost:5432/db",
    )
    base.update(overrides)
    return Settings(**base)


def test_make_mirror_null_when_disabled(tmp_path):
    s = _s(tmp_path, pg_mirror_enabled=False)
    assert isinstance(make_mirror(s), _NullPgMirror)


def test_make_mirror_null_when_dsn_missing(tmp_path):
    s = _s(tmp_path, pg_database_url="")
    assert isinstance(make_mirror(s), _NullPgMirror)


def test_make_mirror_real_when_configured(tmp_path):
    s = _s(tmp_path)
    assert isinstance(make_mirror(s), PgMirror)


def test_event_emit_swallows_errors(tmp_path):
    s = _s(tmp_path)
    m = PgMirror(s)
    conn = MagicMock()
    conn.closed = False
    conn.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError("boom")
    m._conn = conn
    # Must not raise even though the cursor.execute chain throws.
    m.emit_event(
        event_id=1, ts="2026-05-13T00:00:00Z", kind="t",
        ticker=None, order_id=None, payload={},
    )


def test_order_upsert_swallows_errors(tmp_path):
    s = _s(tmp_path)
    m = PgMirror(s)
    conn = MagicMock()
    conn.closed = False
    conn.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError("boom")
    m._conn = conn
    m.upsert_sim_order({
        "id": 1, "ticker": "T", "bid_cents": 90, "quantity": 10,
        "placed_at": "2026-05-13T00:00:00Z", "status": "open",
    })


def test_market_upsert_swallows_errors(tmp_path):
    s = _s(tmp_path)
    m = PgMirror(s)
    conn = MagicMock()
    conn.closed = False
    conn.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError("boom")
    m._conn = conn
    m.upsert_market(
        ticker="T", event_ticker=None, title=None, close_time=None,
        expected_expiry=None, ask_cents=None, bid_cents=None,
        volume=None, open_interest=None,
    )
