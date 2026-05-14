from __future__ import annotations

from unittest.mock import patch

from kalshi_maker_bot.config import Settings
from kalshi_maker_bot.kalshi_client import KalshiClient


def _client(settings: Settings) -> KalshiClient:
    return KalshiClient(settings)


def test_orderbook_parses_yes_dollars_no_dollars(tmp_settings: Settings) -> None:
    raw = {
        "orderbook": {
            "yes_dollars": [[0.84, 100], [0.85, 50]],
            "no_dollars": [[0.10, 200], [0.11, 30]],
        }
    }
    client = _client(tmp_settings)
    with patch.object(client, "_request", return_value=raw):
        ob = client.get_orderbook("MKT")
    assert ob.yes_bid_cents == 85
    assert ob.yes_ask_cents == 100 - 11


def test_orderbook_handles_empty_yes_side(tmp_settings: Settings) -> None:
    raw = {"orderbook": {"yes_dollars": [], "no_dollars": [[0.15, 10]]}}
    client = _client(tmp_settings)
    with patch.object(client, "_request", return_value=raw):
        ob = client.get_orderbook("MKT")
    assert ob.yes_bid_cents is None
    assert ob.yes_ask_cents == 85


def test_orderbook_legacy_yes_no_cents_keys_fallback(tmp_settings: Settings) -> None:
    raw = {"orderbook": {"yes": [[84, 100]], "no": [[12, 50]]}}
    client = _client(tmp_settings)
    with patch.object(client, "_request", return_value=raw):
        ob = client.get_orderbook("MKT")
    assert ob.yes_bid_cents == 84
    assert ob.yes_ask_cents == 100 - 12


def test_orderbook_empty_returns_none_ask(tmp_settings: Settings) -> None:
    raw = {"orderbook": {}}
    client = _client(tmp_settings)
    with patch.object(client, "_request", return_value=raw):
        ob = client.get_orderbook("MKT")
    assert ob.yes_bid_cents is None
    assert ob.yes_ask_cents is None
