"""
Simulated order lifecycle.

This module never calls any Kalshi write endpoint.  It only:
  - inserts sim orders into the DB
  - flips them filled/cancelled based on market snapshots
  - emits structured events

If you find yourself wanting to import `KalshiClient.place_order` in this
file, stop.  The contract is that simulation never crosses into the live
write path -- the only Kalshi calls allowed here are READ calls
(`get_orderbook`, `get_market`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .catalysts import minutes_until_close
from .config import Settings
from .db import Database
from .events import EventBus
from .kalshi_client import KalshiClient, OrderbookSnapshot
from .logging_setup import get_logger
from .pnl import order_pnl_cents, per_contract_fee_cents
from .strategy import BidPlan

log = get_logger(__name__)


@dataclass(frozen=True)
class FillDecision:
    kind: str  # 'fill' | 'cancel' | 'hold'
    reason: str
    fill_price_cents: int | None = None


def decide_for_open_order(
    order_bid_cents: int,
    placed_at: datetime,
    ob: OrderbookSnapshot,
    market: dict[str, Any] | None,
    settings: Settings,
    now: datetime,
) -> FillDecision:
    """
    Given a still-open sim order and the latest orderbook snapshot, decide
    whether to mark it filled, cancel it, or leave it open.

    Decision order (first match wins):
      1. close buffer  -- cancel anything within `close_buffer_min` of close
      2. fill          -- if best YES ask has dropped to or below our bid
      3. drift cancel  -- if best YES ask has moved > `cancel_drift_cents`
                          above our bid
      4. refresh       -- if open longer than `refresh_interval_min`, cancel
                          and let the scanner re-evaluate next cycle
      5. hold
    """
    if market is not None:
        mins = minutes_until_close(market, now)
        if mins is not None and mins <= settings.close_buffer_min:
            return FillDecision("cancel", f"close_buffer:{mins:.1f}m")

    ask = ob.yes_ask_cents
    if ask is not None and ask <= order_bid_cents:
        return FillDecision("fill", f"ask<=bid:{ask}<={order_bid_cents}", fill_price_cents=order_bid_cents)

    if ask is not None and ask > order_bid_cents + settings.cancel_drift_cents:
        return FillDecision("cancel", f"drift:ask={ask},bid={order_bid_cents}")

    age_min = (now - placed_at).total_seconds() / 60.0
    if age_min >= settings.refresh_interval_min:
        return FillDecision("cancel", f"refresh:age={age_min:.1f}m")

    return FillDecision("hold", "ok")


class Simulator:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        client: KalshiClient,
        events: EventBus,
    ) -> None:
        self._settings = settings
        self._db = db
        self._client = client
        self._events = events

    # --- placement ----------------------------------------------------------

    def place_sim_order(self, plan: BidPlan, ask_cents: int) -> int:
        if self._settings.is_live:
            # Belt-and-braces: simulator only operates in sim mode.  The runner
            # is responsible for choosing the right code path, but we refuse
            # to silently no-op if someone wires this up incorrectly.
            raise RuntimeError("Simulator.place_sim_order called while MODE=live")
        order_id = self._db.create_sim_order(
            ticker=plan.ticker,
            bid_cents=plan.bid_cents,
            quantity=plan.quantity,
            notes=plan.rationale,
        )
        payload = {
            "order_id": order_id,
            "ticker": plan.ticker,
            "bid_cents": plan.bid_cents,
            "ask_cents_at_placement": ask_cents,
            "quantity": plan.quantity,
            "rationale": plan.rationale,
        }
        self._events.emit("sim_order_placed", payload, ticker=plan.ticker, order_id=order_id)
        log.info("sim_order_placed", **payload)
        return order_id

    # --- monitor (fill / cancel) -------------------------------------------

    def step_open_orders(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Refresh every open order against the latest orderbook. Returns a list
        of event payloads emitted, useful for tests."""
        now = now or datetime.now(UTC)
        emitted: list[dict[str, Any]] = []
        for row in self._db.get_open_orders():
            order_id = int(row["id"])
            ticker = row["ticker"]
            try:
                ob = self._client.get_orderbook(ticker)
                market = self._client.get_market(ticker).get("market")
            except Exception as exc:
                log.warning("monitor_fetch_failed", ticker=ticker, error=str(exc))
                continue
            placed_at = datetime.fromisoformat(row["placed_at"])
            decision = decide_for_open_order(
                order_bid_cents=int(row["bid_cents"]),
                placed_at=placed_at,
                ob=ob,
                market=market,
                settings=self._settings,
                now=now,
            )
            if decision.kind == "fill":
                fill_price = int(decision.fill_price_cents)
                self._db.mark_sim_order_filled(order_id, fill_price)
                payload = {
                    "order_id": order_id,
                    "ticker": ticker,
                    "fill_price_cents": fill_price,
                    "quantity": int(row["quantity"]),
                    "reason": decision.reason,
                    "per_contract_fee_cents": per_contract_fee_cents(fill_price),
                }
                self._events.emit("sim_order_filled", payload, ticker=ticker, order_id=order_id)
                log.info("sim_order_filled", **payload)
                emitted.append({"kind": "fill", **payload})
            elif decision.kind == "cancel":
                self._db.mark_sim_order_cancelled(order_id, decision.reason)
                payload = {
                    "order_id": order_id,
                    "ticker": ticker,
                    "reason": decision.reason,
                    "bid_cents": int(row["bid_cents"]),
                }
                self._events.emit("sim_order_cancelled", payload, ticker=ticker, order_id=order_id)
                log.info("sim_order_cancelled", **payload)
                emitted.append({"kind": "cancel", **payload})
            else:
                emitted.append({"kind": "hold", "order_id": order_id, "ticker": ticker})
        return emitted

    # --- resolution / P&L ---------------------------------------------------

    def resolve_market(self, ticker: str, outcome: str) -> list[dict[str, Any]]:
        """Settle any filled-unresolved sim orders for this market."""
        self._db.mark_market_resolved(ticker, outcome)
        emitted: list[dict[str, Any]] = []
        for row in self._db.get_filled_unresolved_orders(ticker):
            order_id = int(row["id"])
            fill_cents = int(row["fill_price_cents"])
            qty = int(row["quantity"])
            pnl = order_pnl_cents(fill_cents, qty, outcome)
            self._db.record_resolution_pnl(order_id, pnl)
            payload = {
                "order_id": order_id,
                "ticker": ticker,
                "outcome": outcome,
                "fill_price_cents": fill_cents,
                "quantity": qty,
                "pnl_cents": pnl,
            }
            self._events.emit(
                "sim_order_resolved", payload, ticker=ticker, order_id=order_id
            )
            log.info("sim_order_resolved", **payload)
            emitted.append(payload)
        return emitted
