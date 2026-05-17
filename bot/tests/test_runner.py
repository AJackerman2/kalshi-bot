from __future__ import annotations

from kalshi_maker_bot.runner import (
    _bucket_asks_by_decile,
    _yes_ask_cents_from_list_market,
)


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


def test_bucket_asks_empty_input() -> None:
    out = _bucket_asks_by_decile([], 82, 97)
    assert out["none"] == 0
    assert out["in_band"] == 0
    assert out["b00_10"] == 0
    assert out["b90_100"] == 0


def test_bucket_asks_counts_none_separately() -> None:
    out = _bucket_asks_by_decile([None, None, None], 82, 97)
    assert out["none"] == 3
    assert out["in_band"] == 0
    assert sum(v for k, v in out.items() if k.startswith("b")) == 0


def test_bucket_asks_distributes_across_deciles() -> None:
    asks = [5, 15, 25, 35, 45, 55, 65, 75, 85, 95]
    out = _bucket_asks_by_decile(asks, 82, 97)
    for k in (
        "b00_10",
        "b10_20",
        "b20_30",
        "b30_40",
        "b40_50",
        "b50_60",
        "b60_70",
        "b70_80",
        "b80_90",
        "b90_100",
    ):
        assert out[k] == 1
    assert out["none"] == 0


def test_bucket_asks_edge_values() -> None:
    # ask=10 lands in b10_20 (not b00_10) -- buckets are [n*10, n*10+10).
    out = _bucket_asks_by_decile([10, 20, 99], 82, 97)
    assert out["b00_10"] == 0
    assert out["b10_20"] == 1
    assert out["b20_30"] == 1
    assert out["b90_100"] == 1


def test_bucket_asks_in_band_count() -> None:
    asks = [50, 80, 82, 85, 90, 97, 98, None]
    out = _bucket_asks_by_decile(asks, 82, 97)
    # 82, 85, 90, 97 satisfy 82 <= ask <= 97 -- 4 markets.
    assert out["in_band"] == 4
    assert out["none"] == 1
