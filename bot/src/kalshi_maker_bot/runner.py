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
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

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


def _yes_ask_cents_from_list_market(m: dict[str, Any]) -> int | None:
    """Extract the YES ask in integer cents from a Kalshi /markets list-row.

    Kalshi reports `yes_ask_dollars` as a string like "0.85".  When there are
    no NO bidders (and so no derived YES ask), Kalshi returns "1.0000" -- the
    contract cap -- which we treat as "no ask available".  Falls back to the
    legacy `yes_ask` field (integer cents) if a future API revision changes
    the names back.
    """
    raw = m.get("yes_ask_dollars")
    if raw is not None:
        try:
            cents = int(round(float(raw) * 100))
        except (TypeError, ValueError):
            return None
    else:
        legacy = m.get("yes_ask")
        if legacy is None:
            return None
        try:
            cents = int(legacy)
        except (TypeError, ValueError):
            return None
    if cents <= 0 or cents >= 100:
        return None
    return cents


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

        # Log the OI / volume distribution once per scan -- cheap and gives
        # us visibility into Kalshi's market mix in the dashboard's journal.
        if markets:
            oi_values = sorted(int(m.get("open_interest") or 0) for m in markets)
            vol_values = sorted(
                int(m.get("volume_24h") or m.get("volume") or 0) for m in markets
            )
            n = len(oi_values)
            log.info(
                "scan_metadata_distribution",
                total=n,
                oi_max=oi_values[-1],
                oi_p99=oi_values[int(n * 0.99)],
                oi_p90=oi_values[int(n * 0.9)],
                oi_gt_0=sum(1 for v in oi_values if v > 0),
                oi_gt_50=sum(1 for v in oi_values if v > 50),
                vol_max=vol_values[-1],
                vol_p99=vol_values[int(n * 0.99)],
                vol_gt_0=sum(1 for v in vol_values if v > 0),
            )

        # Source the YES ask directly from the market-list response.  Kalshi
        # exposes yes_ask_dollars / yes_bid_dollars per market, so we don't
        # need to make a per-market orderbook round-trip just to filter on
        # ask band -- saves ~15-20k HTTP calls per scan.  Orderbook is fetched
        # only for the handful of candidates that pass the band filter
        # (below), preserving full snapshot data for the dashboard.
        ask_lookup: dict[str, int | None] = {}
        for m in markets:
            ticker = m.get("ticker")
            if not ticker:
                continue
            ask_lookup[ticker] = _yes_ask_cents_from_list_market(m)

        cands, rejs = filter_candidates(markets, ask_lookup, self._settings, now)
        rej_reasons: dict[str, int] = {}
        for r in rejs:
            key = r.reason.split(":", 1)[0]
            rej_reasons[key] = rej_reasons.get(key, 0) + 1
        self._events.emit(
            "scan_completed",
            {
                "markets_seen": len(markets),
                "candidates": len(cands),
                "rejections": len(rejs),
                "rejection_reasons": rej_reasons,
            },
        )

        # For each candidate, snapshot its current orderbook into the DB +
        # Neon mirror (dashboard depends on this) and dispatch to the order
        # manager.  Only candidates get the round-trip; the rest of the
        # 17k-market universe never gets fetched.
        market_by_ticker = {m["ticker"]: m for m in markets if m.get("ticker")}
        for cand in cands:
            m = market_by_ticker.get(cand.ticker, {})
            try:
                ob = self._client.get_orderbook(cand.ticker)
                ob_ask, ob_bid = ob.yes_ask_cents, ob.yes_bid_cents
            except Exception as exc:
                log.warning(
                    "orderbook_fetch_failed", ticker=cand.ticker, error=str(exc)
                )
                ob_ask, ob_bid = cand.ask_cents, None
            volume = int(m.get("volume_24h") or m.get("volume") or 0)
            open_interest = int(m.get("open_interest") or 0)
            self._db.upsert_market_snapshot(
                ticker=cand.ticker,
                event_ticker=m.get("event_ticker"),
                title=m.get("title"),
                close_time=m.get("close_time"),
                expected_expiry=m.get("expected_expiration_time"),
                ask_cents=ob_ask,
                bid_cents=ob_bid,
                volume=volume,
                open_interest=open_interest,
            )
            try:
                self._mirror.upsert_market(
                    ticker=cand.ticker,
                    event_ticker=m.get("event_ticker"),
                    title=m.get("title"),
                    close_time=m.get("close_time"),
                    expected_expiry=m.get("expected_expiration_time"),
                    ask_cents=ob_ask,
                    bid_cents=ob_bid,
                    volume=volume,
                    open_interest=open_interest,
                )
            except Exception as exc:
                log.warning(
                    "pg_market_mirror_failed", ticker=cand.ticker, error=str(exc)
                )
            try:
                outcome = self._order_mgr.consider_candidate(cand)
                if outcome.startswith("skip"):
                    self._events.emit(
                        "candidate_skipped",
                        {
                            "reason": outcome,
                            "ticker": cand.ticker,
                            "ask_cents": cand.ask_cents,
                        },
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
        # Server-side filter: only fetch markets closing within the configured
        # window.  Kalshi's full open catalog (200k+ markets) is dominated by
        # long-dated election micro-markets with no trading; restricting to
        # markets closing in the next N days yields the actually-tradeable
        # set in O(thousands) rather than O(hundreds of thousands).
        max_close_ts = int(
            (
                datetime.now(UTC)
                + timedelta(days=self._settings.scan_close_window_days)
            ).timestamp()
        )
        for _ in range(1000):
            resp = self._client.list_open_markets(
                cursor=cursor, max_close_ts=max_close_ts
            )
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
