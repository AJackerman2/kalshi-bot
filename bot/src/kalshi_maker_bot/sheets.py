"""
Google Sheets event sink.

Wraps the Sheets `values.append` call so callers can `sheets.append_event(...)`
without thinking about retries or batch flushing.  Falls back to a no-op
writer when `SHEETS_ENABLED=0` or credentials are unavailable -- the SQLite
event log remains the source of truth either way.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Settings
from .logging_setup import get_logger

log = get_logger(__name__)


HEADERS: list[str] = [
    "ts", "kind", "ticker", "order_id", "mode", "details_json",
]


class _NullSheetsSink:
    def ensure_header(self) -> None:
        pass

    def append_event(self, ts: str, kind: str, ticker: str | None, order_id: int | None, mode: str, details: dict[str, Any]) -> None:
        pass


class SheetsSink:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._service = None
        self._range = f"{settings.sheets_tab_name}!A:F"

    def _get_service(self):
        if self._service is not None:
            return self._service
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_service_account_file(
            str(self._settings.google_credentials_path),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return self._service

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=10), reraise=True)
    def ensure_header(self) -> None:
        svc = self._get_service()
        sheet = svc.spreadsheets()
        result = (
            sheet.values()
            .get(spreadsheetId=self._settings.sheets_spreadsheet_id, range=self._range)
            .execute()
        )
        values = result.get("values") or []
        if values and values[0][: len(HEADERS)] == HEADERS:
            return
        sheet.values().update(
            spreadsheetId=self._settings.sheets_spreadsheet_id,
            range=f"{self._settings.sheets_tab_name}!A1:F1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ).execute()

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=10), reraise=True)
    def append_event(
        self,
        ts: str,
        kind: str,
        ticker: str | None,
        order_id: int | None,
        mode: str,
        details: dict[str, Any],
    ) -> None:
        svc = self._get_service()
        body = {
            "values": [[
                ts, kind, ticker or "", order_id if order_id is not None else "",
                mode, json.dumps(details, default=str),
            ]]
        }
        svc.spreadsheets().values().append(
            spreadsheetId=self._settings.sheets_spreadsheet_id,
            range=self._range,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()


def make_sink(settings: Settings):
    if not settings.sheets_enabled:
        log.info("sheets_disabled_by_env")
        return _NullSheetsSink()
    if not settings.sheets_spreadsheet_id:
        log.warning("sheets_disabled_missing_spreadsheet_id")
        return _NullSheetsSink()
    if not Path(settings.google_credentials_path).exists():
        log.warning(
            "sheets_disabled_missing_credentials",
            path=str(settings.google_credentials_path),
        )
        return _NullSheetsSink()
    return SheetsSink(settings)


class EventSink:
    """Fans an event out to JSONL (always) and Sheets (if configured)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jsonl_path = Path(settings.event_log_path)
        self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._sheets = make_sink(settings)
        try:
            self._sheets.ensure_header()
        except Exception as exc:
            log.warning("sheets_header_failed", error=str(exc))

    def emit(
        self,
        kind: str,
        payload: dict[str, Any],
        ticker: str | None = None,
        order_id: int | None = None,
    ) -> None:
        ts = datetime.now(UTC).isoformat()
        record = {
            "ts": ts,
            "kind": kind,
            "ticker": ticker,
            "order_id": order_id,
            "mode": self._settings.mode.value,
            "payload": payload,
        }
        try:
            with self._jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except OSError as exc:
            log.warning("jsonl_write_failed", error=str(exc))
        try:
            self._sheets.append_event(
                ts=ts,
                kind=kind,
                ticker=ticker,
                order_id=order_id,
                mode=self._settings.mode.value,
                details=payload,
            )
        except Exception as exc:
            log.warning("sheets_append_failed", error=str(exc), kind=kind)
