"""
Kalshi REST client.

Hard rule: write endpoints (`place_order`, `cancel_order`) raise
`SimModeRefused` unless `settings.is_live` is True.  The HTTP call is never
issued in sim mode.  See `tests/test_mode_gate.py`.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import Settings
from .logging_setup import get_logger

log = get_logger(__name__)


class KalshiError(Exception):
    pass


class KalshiAuthError(KalshiError):
    pass


class SimModeRefused(KalshiError):
    """Raised when a write endpoint is called while MODE != live."""


@dataclass(frozen=True)
class OrderbookSnapshot:
    """Best YES bid / ask in cents, plus raw books."""

    ticker: str
    yes_bid_cents: int | None
    yes_ask_cents: int | None
    yes_book: list[tuple[int, int]]
    no_book: list[tuple[int, int]]


def _load_private_key(path: Path) -> rsa.RSAPrivateKey:
    data = path.read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise KalshiAuthError(f"Expected RSA private key at {path}")
    return key


def _sign_request(key: rsa.RSAPrivateKey, timestamp_ms: str, method: str, path: str) -> str:
    message = f"{timestamp_ms}{method.upper()}{path}".encode()
    signature = key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode()


class KalshiClient:
    # TEMP DIAGNOSTIC counter, shared across all instances in a process.
    # Caps the number of orderbook_dbg_sample log lines so journalctl doesn't
    # drown.  Reset on process restart.  Remove once orderbook parser is verified.
    _dbg_orderbook_samples: int = 0

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = http_client or httpx.Client(timeout=15.0)
        self._key: rsa.RSAPrivateKey | None = None

    def close(self) -> None:
        self._client.close()

    # --- auth helpers -------------------------------------------------------

    def _ensure_key(self) -> rsa.RSAPrivateKey:
        if self._key is None:
            if not self._settings.kalshi_api_key_id:
                raise KalshiAuthError("KALSHI_API_KEY_ID is empty")
            self._key = _load_private_key(self._settings.kalshi_private_key_path)
        return self._key

    def _signed_headers(self, method: str, path: str) -> dict[str, str]:
        key = self._ensure_key()
        ts = str(int(time.time() * 1000))
        sig = _sign_request(key, ts, method, path)
        return {
            "KALSHI-ACCESS-KEY": self._settings.kalshi_api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "accept": "application/json",
        }

    def _path_of(self, endpoint: str) -> str:
        base = httpx.URL(self._settings.kalshi_base_url).path.rstrip("/")
        return f"{base}/{endpoint.lstrip('/')}"

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        reraise=True,
    )
    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = self._path_of(endpoint)
        url = f"{self._settings.kalshi_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = self._signed_headers(method, path)
        if json_body is not None:
            headers["content-type"] = "application/json"
        resp = self._client.request(method, url, params=params, json=json_body, headers=headers)
        if resp.status_code >= 400:
            log.warning(
                "kalshi_http_error",
                method=method,
                url=url,
                status=resp.status_code,
                body=resp.text[:1000],
            )
            resp.raise_for_status()
        return resp.json() if resp.content else {}

    # --- read endpoints -----------------------------------------------------

    def list_open_markets(self, limit: int = 200, cursor: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"status": "open", "limit": limit}
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "markets", params=params)

    def get_market(self, ticker: str) -> dict[str, Any]:
        return self._request("GET", f"markets/{ticker}")

    def get_orderbook(self, ticker: str) -> OrderbookSnapshot:
        raw = self._request("GET", f"markets/{ticker}/orderbook")
        # TEMP DIAGNOSTIC: log the raw response shape for the first 5
        # orderbook fetches per process so we can confirm the parser is
        # reading the fields Kalshi actually returns.  Remove once verified.
        if KalshiClient._dbg_orderbook_samples < 5:
            KalshiClient._dbg_orderbook_samples += 1
            log.info("orderbook_dbg_sample", ticker=ticker, raw=raw)
        ob = raw.get("orderbook", {}) or {}
        yes_book = [(int(p), int(s)) for p, s in (ob.get("yes") or [])]
        no_book = [(int(p), int(s)) for p, s in (ob.get("no") or [])]
        yes_bid = max((p for p, _ in yes_book), default=None)
        # YES ask is derived from the highest NO buy: selling YES at P is the
        # same as buying NO at 100 - P.
        no_top = max((p for p, _ in no_book), default=None)
        yes_ask = (100 - no_top) if no_top is not None else None
        return OrderbookSnapshot(
            ticker=ticker,
            yes_bid_cents=yes_bid,
            yes_ask_cents=yes_ask,
            yes_book=yes_book,
            no_book=no_book,
        )

    # --- write endpoints (gated) -------------------------------------------

    def place_order(
        self,
        ticker: str,
        side: str,
        action: str,
        price_cents: int,
        count: int,
        client_order_id: str,
    ) -> dict[str, Any]:
        if not self._settings.is_live:
            raise SimModeRefused(
                f"place_order blocked: MODE={self._settings.mode.value}. "
                "Live endpoint must not fire in Session 1."
            )
        body = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "type": "limit",
            "count": count,
            "yes_price": price_cents if side == "yes" else None,
            "no_price": price_cents if side == "no" else None,
            "client_order_id": client_order_id,
        }
        body = {k: v for k, v in body.items() if v is not None}
        return self._request("POST", "portfolio/orders", json_body=body)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        if not self._settings.is_live:
            raise SimModeRefused(
                f"cancel_order blocked: MODE={self._settings.mode.value}. "
                "Live endpoint must not fire in Session 1."
            )
        return self._request("DELETE", f"portfolio/orders/{order_id}")
