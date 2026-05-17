"""
Order manager: bridges the scanner output to the simulator.

In SIM mode (the only mode allowed in Session 1) this calls into
`Simulator.place_sim_order`.  In LIVE mode (Session 2+), the placeholder
`_place_live_order` raises -- we deliberately leave it unimplemented so the
live path cannot fire by accident.
"""

from __future__ import annotations

from .config import Settings
from .db import Database
from .kalshi_client import KalshiClient
from .logging_setup import get_logger
from .scanner import Candidate
from .simulator import Simulator
from .strategy import build_bid_plan

log = get_logger(__name__)


class OrderManager:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        client: KalshiClient,
        simulator: Simulator,
    ) -> None:
        self._settings = settings
        self._db = db
        self._client = client
        self._simulator = simulator

    def consider_candidate(self, cand: Candidate) -> str:
        existing = self._db.get_open_order_for_ticker(cand.ticker)
        if existing is not None:
            return "skip_existing_open"
        if cand.event_ticker:
            open_for_event = self._db.count_open_orders_for_event(cand.event_ticker)
            if open_for_event >= self._settings.max_orders_per_event:
                return "skip_event_capped"
        plan = build_bid_plan(cand.ticker, cand.ask_cents, self._settings)
        if plan.quantity <= 0:
            return "skip_zero_qty"
        if self._settings.is_live:
            self._place_live_order(plan, cand.ask_cents)
            return "placed_live"
        self._simulator.place_sim_order(plan, cand.ask_cents)
        return "placed_sim"

    def _place_live_order(self, plan, ask_cents) -> None:
        # Deliberately not implemented in Session 1.  The Kalshi client also
        # gates the actual HTTP call, but we add a second refusal here so the
        # live code path cannot be reached without explicit edits.
        raise NotImplementedError(
            "Live order placement is disabled in Session 1. "
            "Implementation is reserved for Session 2 after sign-off."
        )
