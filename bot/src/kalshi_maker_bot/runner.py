"""
Main supervisor loop.

Two interleaved cadences:
  - scan : every `scan_interval_sec`.  Pulls open markets, runs the
           candidate filter, asks OrderManager to place a sim bid for each.
  - monitor : every `monitor_interval_sec`.  Sweeps open sim orders for
              fills, cancels, and refreshes.

A separate periodic check sweeps resolved markets to settle P&L.  All paths
write through the shared `EventBus` so SQLite, JSONL, and Sheets stay in lock-step.
"""

from __future__ import annotations

import signal
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from .catalysts import hours_until_close, is_within_catalyst_buffer
from .config import Settings, get_settings
from .db import Database
from .events import EventBus
from .kalshi_client import KalshiClient
from .logging_setup import configure_logging, get_logger
from .order_manager import OrderManager
from .pg_mirror import make_mirror
from .scanner import filter_candidates
from .sheets import EventSink
from .simulator import Simulator

log = get_logger(__name__)


class Runner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db = Database(settings.db_path)
        self._sink = EventSink(settings)
        self._mirror = make_mirror(settings)
        self._events = EventBus(self._db, self._sink, mirror=self._mirror)
        self._http = httpx.Client(timeout=15.0)
        self._client = KalshiClient(settings, http_client=self._http)
        self._simulator = Simulator(
            settings, self._db, self._client, self._events, mirror=self._mirror
        )
        self._order_mgr = OrderManager(settings, self._db, self._client, self._simulator)
        self._stop = False
        self._last_scan_at = 0.0
        self._last_monitor_at = 0.0
        self._last_resolution_sweep_at = 0.0

    # --- lifecycle ----------------------------------------------------------

    def install_signal_handlers(self) -> None:
        def _on_signal(signum, _frame):
            log.info("shutdown_requested", signal=signum)
            self._stop = True

        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)

    def close(self) -> None:
        try:
            self._client.close()
        finally:
            self._http.close()
            self._mirror.close()
            self._db.close()

    # --- main loop ----------------------------------------------------------

    def run(self) -> None:
        self.install_signal_handlers()
        self._events.emit(
            "service_started",
            {"mode": self._settings.mode.value, "base_url": self._settings.kalshi_base_url},
        )
        try:
            while not self._stop:
                now = time.monotonic()
                if now - self._last_scan_at >= self._settings.scan_interval_sec:
                    self._safe(self._do_scan)
                    self._last_scan_at = now
                if now - self._last_monitor_at >= self._settings.monitor_interval_sec:
                    self._safe(self._do_monitor)
                    self._last_monitor_at = now
                if now - self._last_resolution_sweep_at >= max(
                    self._settings.scan_interval_sec, 60
                ):
                    self._safe(self._do_resolution_sweep)
                    self._last_resolution_sweep_at = now
                time.sleep(1.0)
        finally:
            self._events.emit("service_stopping", {})
            self.close()

    def _safe(self, fn) -> None:
        try:
            fn()
        except Exception as exc:
            log.error("loop_iter_failed", fn=fn.__name__, error=str(exc), exc_info=True)
            self._events.emit("loop_iter_failed", {"fn": fn.__name__, "error": str(exc)})

    # --- scan ---------------------------------------------------------------

    def _do_scan(self) -> None:
        markets = self._fetch_all_open_markets()
        now = datetime.now(UTC)

        # TEMP DIAGNOSTIC: dump the first 3 markets in the list each scan so
        # we can verify what fields Kalshi is actually returning.  We saw
        # 100% rejection on "open_interest < threshold" even with threshold=50
        # across 40k markets, which strongly suggests a field-name change in
        # Kalshi's API (cf. yes_dollars/no_dollars in the orderbook).  Remove
        # once verified.
        for sample in markets[:3]:
            log.info("market_list_dbg_sample", market=sample)

        # Pre-filter on market metadata before fetching orderbooks.  Each
        # orderbook fetch costs a Kalshi-rate-limited HTTP round-trip; with
        # ~10-20k open markets this dominates scan time.  Anything that can
        # never become a candidate (OI/vol too low, market closing too soon,
        # inside a catalyst window) is excluded here so we never spend a
        # round-trip on it.
        pre_filtered: list[dict[str, Any]] = []
        pre_rej: dict[str, int] = {}
        for m in markets:
            if not m.get("ticker"):
                continue
            oi = int(m.get("open_interest") or 0)
            if oi < self._settings.min_open_interest:
                pre_rej["oi_low"] = pre_rej.get("oi_low", 0) + 1
                continue
            vol = int(m.get("volume_24h") or m.get("volume") or 0)
            if vol < self._settings.min_recent_volume:
                pre_rej["vol_low"] = pre_rej.get("vol_low", 0) + 1
                continue
            hrs = hours_until_close(m, now)
            if hrs is None:
                pre_rej["no_close_time"] = pre_rej.get("no_close_time", 0) + 1
                continue
            if hrs < self._settings.min_hours_to_close:
                pre_rej["close_too_soon"] = pre_rej.get("close_too_soon", 0) + 1
                continue
            in_buf, _ = is_within_catalyst_buffer(
                m, now, self._settings.catalyst_buffer_min
            )
            if in_buf:
                pre_rej["catalyst"] = pre_rej.get("catalyst", 0) + 1
                continue
            pre_filtered.append(m)

        log.info(
            "scan_prefilter_done",
            total_markets=len(markets),
            passed_to_orderbook=len(pre_filtered),
        )

        ask_lookup: dict[str, int | None] = {}
        for m in pre_filtered:
            ticker = m["ticker"]
            try:
                ob = self._client.get_orderbook(ticker)
            except Exception as exc:
                log.warning("orderbook_fetch_failed", ticker=ticker, error=str(exc))
                ask_lookup[ticker] = None
                continue
            ask_lookup[ticker] = ob.yes_ask_cents
            volume = int(m.get("volume_24h") or m.get("volume") or 0)
            open_interest = int(m.get("open_interest") or 0)
            self._db.upsert_market_snapshot(
                ticker=ticker,
                event_ticker=m.get("event_ticker"),
                title=m.get("title"),
                close_time=m.get("close_time"),
                expected_expiry=m.get("expected_expiration_time"),
                ask_cents=ob.yes_ask_cents,
                bid_cents=ob.yes_bid_cents,
                volume=volume,
                open_interest=open_interest,
            )
            try:
                self._mirror.upsert_market(
                    ticker=ticker,
                    event_ticker=m.get("event_ticker"),
                    title=m.get("title"),
                    close_time=m.get("close_time"),
                    expected_expiry=m.get("expected_expiration_time"),
                    ask_cents=ob.yes_ask_cents,
                    bid_cents=ob.yes_bid_cents,
                    volume=volume,
                    open_interest=open_interest,
                )
            except Exception as exc:
                log.warning("pg_market_mirror_failed", ticker=ticker, error=str(exc))

        cands, rejs = filter_candidates(pre_filtered, ask_lookup, self._settings, now)
        # Merge pre-filter reasons with the ask-band rejections from
        # filter_candidates so the dashboard sees one unified histogram.
        rej_reasons: dict[str, int] = pre_rej.copy()
        for r in rejs:
            key = r.reason.split(":", 1)[0]
            rej_reasons[key] = rej_reasons.get(key, 0) + 1
        total_rejected = len(markets) - len(cands)
        self._events.emit(
            "scan_completed",
            {
                "markets_seen": len(markets),
                "candidates": len(cands),
                "rejections": total_rejected,
                "rejection_reasons": rej_reasons,
            },
        )
        for cand in cands:
            try:
                outcome = self._order_mgr.consider_candidate(cand)
                if outcome.startswith("skip"):
                    self._events.emit(
                        "candidate_skipped",
                        {"reason": outcome, "ticker": cand.ticker, "ask_cents": cand.ask_cents},
                        ticker=cand.ticker,
                    )
            except NotImplementedError as exc:
                # Live path tripwire.  Re-raise -- we want the service to fail
                # loudly rather than appear healthy while not trading.
                log.error("live_path_attempted", error=str(exc))
                raise

    def _fetch_all_open_markets(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        cursor: str | None = None
        # 200 pages * 200/page = 40_000 markets ceiling.  Kalshi's typical
        # open-market count fluctuates around 10-25k, so this gives headroom.
        for _ in range(200):
            resp = self._client.list_open_markets(cursor=cursor)
            out.extend(resp.get("markets") or [])
            cursor = resp.get("cursor")
            if not cursor:
                break
        return out

    # --- monitor ------------------------------------------------------------

    def _do_monitor(self) -> None:
        self._simulator.step_open_orders()

    # --- resolution sweep ---------------------------------------------------

    def _do_resolution_sweep(self) -> None:
        rows = self._db._conn.execute(  # noqa: SLF001 -- intentional, internal sweep
            """
            SELECT DISTINCT ticker
              FROM sim_orders
             WHERE status='filled' AND pnl_cents IS NULL
            """
        ).fetchall()
        for row in rows:
            ticker = row["ticker"]
            try:
                resp = self._client.get_market(ticker)
            except Exception as exc:
                log.warning("resolution_fetch_failed", ticker=ticker, error=str(exc))
                continue
            market = resp.get("market") or {}
            status = (market.get("status") or "").lower()
            if status not in {"finalized", "settled"}:
                continue
            outcome = (market.get("result") or "").lower()
            if outcome not in {"yes", "no"}:
                log.warning("resolution_unrecognized_outcome", ticker=ticker, outcome=outcome)
                continue
            self._simulator.resolve_market(ticker, outcome)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.is_live:
        # Session 1 invariant: this binary must never run in live mode.
        log.error("refusing_to_start_live_mode")
        raise SystemExit(
            "MODE=live is not permitted in this build. Session 2 will lift this."
        )
    Runner(settings).run()


if __name__ == "__main__":
    main()
