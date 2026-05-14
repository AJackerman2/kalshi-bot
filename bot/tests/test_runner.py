from __future__ import annotations

from kalshi_maker_bot.runner import _yes_ask_cents_from_list_market


def test_parses_typical_dollar_string() -> None:
    assert _yes_ask_cents_from_list_market({"yes_ask_dollars": "0.85"}) == 85
    assert _yes_ask_cents_from_list_market({"yes_ask_dollars": "0.97"}) == 97
    assert _yes_ask_cents_from_list_market({"yes_ask_dollars": "0.01"}) == 1


def test_no_ask_sentinel_returns_none() -> None:
    # Kalshi encodes "no YES ask available" as $1.00, the contract cap.
    assert _yes_ask_cents_from_list_market({"yes_ask_dollars": "1.0000"}) is None
    assert _yes_ask_cents_from_list_market({"yes_ask_dollars": "1.00"}) is None
    assert _yes_ask_cents_from_list_market({"yes_ask_dollars": "0.00"}) is None


def test_missing_or_unparseable_returns_none() -> None:
    assert _yes_ask_cents_from_list_market({}) is None
    assert _yes_ask_cents_from_list_market({"yes_ask_dollars": None}) is None
    assert _yes_ask_cents_from_list_market({"yes_ask_dollars": "not-a-number"}) is None


def test_legacy_yes_ask_cents_fallback() -> None:
    # If Kalshi ever reverts to integer-cents yes_ask, the helper still parses.
    assert _yes_ask_cents_from_list_market({"yes_ask": 85}) == 85
    assert _yes_ask_cents_from_list_market({"yes_ask": 99}) == 99
    # Sentinel still applies.
    assert _yes_ask_cents_from_list_market({"yes_ask": 100}) is None
    assert _yes_ask_cents_from_list_market({"yes_ask": 0}) is None


def test_dollar_field_takes_precedence_over_legacy() -> None:
    m = {"yes_ask_dollars": "0.42", "yes_ask": 85}
    assert _yes_ask_cents_from_list_market(m) == 42
