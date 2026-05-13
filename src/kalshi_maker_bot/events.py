"""
Single event emission point.  Writes to:
  - SQLite `events` table (canonical record)
  - JSONL file (cheap tail-friendly log)
  - Google Sheets (human-readable log, best-effort)
  - Supabase Postgres (dashboard mirror, best-effort)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .db import Database
from .logging_setup import get_logger
from .sheets import EventSink
from .supabase_writer import SupabaseWriter, _NullSupabaseWriter

log = get_logger(__name__)


class EventBus:
    def __init__(
        self,
        db: Database,
        sink: EventSink,
        supabase: SupabaseWriter | _NullSupabaseWriter | None = None,
    ) -> None:
        self._db = db
        self._sink = sink
        self._supabase = supabase or _NullSupabaseWriter()

    def emit(
        self,
        kind: str,
        payload: dict[str, Any],
        ticker: str | None = None,
        order_id: int | None = None,
    ) -> int:
        event_id = self._db.record_event(kind, payload, ticker=ticker, order_id=order_id)
        ts = datetime.now(UTC).isoformat()
        try:
            self._sink.emit(kind, payload, ticker=ticker, order_id=order_id)
        except Exception as exc:
            log.warning("event_sink_failed", kind=kind, error=str(exc))
        try:
            self._supabase.emit_event(
                event_id=event_id, ts=ts, kind=kind, ticker=ticker,
                order_id=order_id, payload=payload,
            )
        except Exception as exc:
            log.warning("supabase_event_failed", kind=kind, error=str(exc))
        return event_id
