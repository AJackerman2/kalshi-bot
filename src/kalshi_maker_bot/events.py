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
from .pg_mirror import PgMirror, _NullPgMirror
from .sheets import EventSink

log = get_logger(__name__)


class EventBus:
    def __init__(
        self,
        db: Database,
        sink: EventSink,
        mirror: PgMirror | _NullPgMirror | None = None,
    ) -> None:
        self._db = db
        self._sink = sink
        self._mirror = mirror or _NullPgMirror()

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
            self._mirror.emit_event(
                event_id=event_id, ts=ts, kind=kind, ticker=ticker,
                order_id=order_id, payload=payload,
            )
        except Exception as exc:
            log.warning("pg_event_failed", kind=kind, error=str(exc))
        return event_id
