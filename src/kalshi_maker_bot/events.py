"""
Single event emission point.  Writes to:
  - SQLite `events` table (canonical record)
  - JSONL file (cheap tail-friendly log)
  - Google Sheets (human-readable log, best-effort)
"""

from __future__ import annotations

from typing import Any

from .db import Database
from .logging_setup import get_logger
from .sheets import EventSink

log = get_logger(__name__)


class EventBus:
    def __init__(self, db: Database, sink: EventSink) -> None:
        self._db = db
        self._sink = sink

    def emit(
        self,
        kind: str,
        payload: dict[str, Any],
        ticker: str | None = None,
        order_id: int | None = None,
    ) -> int:
        event_id = self._db.record_event(kind, payload, ticker=ticker, order_id=order_id)
        try:
            self._sink.emit(kind, payload, ticker=ticker, order_id=order_id)
        except Exception as exc:
            log.warning("event_sink_failed", kind=kind, error=str(exc))
        return event_id
