"""TTL parsing and calendar-aware expiry arithmetic."""

import datetime as dt

import pytest

from emberlog.errors import TtlError
from emberlog.ttl import Ttl, add_months


def test_parse_every_unit_and_never():
    for text, count, unit in (
        ("45d", 45, "d"),
        ("8w", 8, "w"),
        ("6m", 6, "m"),
        ("1y", 1, "y"),
    ):
        ttl = Ttl.parse(text)
        assert (ttl.count, ttl.unit) == (count, unit)
        assert str(ttl) == text
    assert Ttl.parse("never").is_never
    assert Ttl.parse(" NEVER ").is_never  # case- and whitespace-tolerant


def test_parse_rejects_malformed_and_zero():
    for text in ("", "45", "d45", "45 d", "45h", "1.5d", "-3d", "45dd", "0d", "monthly"):
        with pytest.raises(TtlError):
            Ttl.parse(text)


def test_parse_rejects_over_twenty_years():
    # "300m" as minutes is a classic slip; emberlog has no sub-day units,
    # so an absurd span means the author meant something else.
    with pytest.raises(TtlError):
        Ttl.parse("300m")
    with pytest.raises(TtlError):
        Ttl.parse("21y")


def test_expiry_days_and_weeks():
    anchor = dt.date(2026, 7, 13)
    assert Ttl.parse("30d").expiry(anchor) == dt.date(2026, 8, 12)
    assert Ttl.parse("2w").expiry(anchor) == dt.date(2026, 7, 27)


def test_expiry_months_clamps_end_of_month():
    # Jan 31 + 1 month must be the last day of February, not March 3.
    assert Ttl.parse("1m").expiry(dt.date(2026, 1, 31)) == dt.date(2026, 2, 28)


def test_expiry_months_clamps_in_leap_year():
    assert Ttl.parse("1m").expiry(dt.date(2028, 1, 31)) == dt.date(2028, 2, 29)


def test_expiry_year_from_leap_day():
    assert Ttl.parse("1y").expiry(dt.date(2028, 2, 29)) == dt.date(2029, 2, 28)


def test_expiry_never_is_none():
    assert Ttl.parse("never").expiry(dt.date(2026, 7, 13)) is None


def test_add_months_crosses_year_boundary():
    assert add_months(dt.date(2026, 11, 15), 3) == dt.date(2027, 2, 15)


def test_describe_is_human():
    assert Ttl.parse("1m").describe() == "1 month"
    assert Ttl.parse("45d").describe() == "45 days"
    assert Ttl.parse("never").describe() == "never"
