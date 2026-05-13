from __future__ import annotations

from datetime import timedelta

from kalshi_maker_bot.catalysts import (
    hours_until_close,
    is_within_catalyst_buffer,
    minutes_until_close,
    parse_iso,
)


def test_parse_iso_handles_z_suffix():
    assert parse_iso("2026-05-13T20:30:00Z") is not None
    assert parse_iso(None) is None
    assert parse_iso("not-a-date") is None


def test_catalyst_buffer_triggers_within_window(now_utc):
    soon = (now_utc + timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
    m = {"expected_expiration_time": soon}
    hit, label = is_within_catalyst_buffer(m, now_utc, buffer_min=30)
    assert hit
    assert "expected_expiration_time" in label


def test_catalyst_buffer_misses_outside_window(now_utc):
    far = (now_utc + timedelta(hours=12)).isoformat().replace("+00:00", "Z")
    m = {"expected_expiration_time": far}
    hit, _ = is_within_catalyst_buffer(m, now_utc, buffer_min=30)
    assert not hit


def test_catalyst_buffer_disabled_when_zero(now_utc):
    soon = (now_utc + timedelta(minutes=5)).isoformat()
    m = {"expected_expiration_time": soon}
    hit, _ = is_within_catalyst_buffer(m, now_utc, buffer_min=0)
    assert not hit


def test_minutes_and_hours_until_close(now_utc):
    close = (now_utc + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    m = {"close_time": close}
    assert abs(hours_until_close(m, now_utc) - 2.0) < 1e-6
    assert abs(minutes_until_close(m, now_utc) - 120.0) < 1e-6
