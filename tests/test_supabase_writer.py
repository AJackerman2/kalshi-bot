from __future__ import annotations

from unittest.mock import MagicMock

from kalshi_maker_bot.config import Mode, Settings
from kalshi_maker_bot.supabase_writer import (
    SupabaseWriter,
    _NullSupabaseWriter,
    make_writer,
)


def _s(tmp_path, **overrides) -> Settings:
    base = dict(
        mode=Mode.SIM,
        kalshi_api_key_id="x",
        kalshi_private_key_path=tmp_path / "k.pem",
        db_path=tmp_path / "db.sqlite",
        event_log_path=tmp_path / "events.jsonl",
        google_credentials_path=tmp_path / "creds.json",
        sheets_enabled=False,
        supabase_enabled=True,
        supabase_url="https://example.supabase.co",
        supabase_service_key="service-role",
    )
    base.update(overrides)
    return Settings(**base)


def test_make_writer_returns_null_when_disabled(tmp_path):
    s = _s(tmp_path, supabase_enabled=False)
    assert isinstance(make_writer(s), _NullSupabaseWriter)


def test_make_writer_returns_null_when_creds_missing(tmp_path):
    s = _s(tmp_path, supabase_url="", supabase_service_key="")
    assert isinstance(make_writer(s), _NullSupabaseWriter)


def test_make_writer_returns_real_when_configured(tmp_path):
    s = _s(tmp_path)
    w = make_writer(s)
    assert isinstance(w, SupabaseWriter)


def test_event_emit_failure_is_swallowed(tmp_path):
    s = _s(tmp_path)
    w = SupabaseWriter(s)
    fake = MagicMock()
    fake.schema.return_value.table.return_value.upsert.side_effect = RuntimeError("boom")
    w._client = fake
    # Must not raise even though the upsert chain throws.
    w.emit_event(
        event_id=1, ts="2026-05-13T00:00:00Z", kind="t",
        ticker=None, order_id=None, payload={},
    )


def test_order_upsert_failure_is_swallowed(tmp_path):
    s = _s(tmp_path)
    w = SupabaseWriter(s)
    fake = MagicMock()
    fake.schema.return_value.table.return_value.upsert.side_effect = RuntimeError("boom")
    w._client = fake
    w.upsert_sim_order({
        "id": 1, "ticker": "T", "bid_cents": 90, "quantity": 10,
        "placed_at": "2026-05-13T00:00:00Z", "status": "open",
    })
