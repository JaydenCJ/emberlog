"""Clock behavior: strict ISO dates and the EMBERLOG_TODAY override."""

import datetime as dt

import pytest

from emberlog.clock import humanize_delta, parse_date, today
from emberlog.errors import ClockError


def test_parse_date_accepts_strict_iso_only():
    assert parse_date("2026-07-13") == dt.date(2026, 7, 13)
    assert parse_date("  2026-07-13 ") == dt.date(2026, 7, 13)


def test_parse_date_rejects_ambiguous_spellings():
    # Log files are shared artifacts: datetimes drag in timezones, slashes
    # and two-digit years are locale traps. One spelling, or an error.
    for text in (
        "2026-07-13T10:00:00",
        "13/07/2026",
        "26-07-13",
        "2026-13-01",
        "yesterday",
    ):
        with pytest.raises(ClockError):
            parse_date(text)


def test_today_honors_env_override(set_today):
    set_today("2031-01-02")
    assert today() == dt.date(2031, 1, 2)


def test_today_rejects_garbage_override(set_today):
    # A typo'd override must fail loudly: silently falling back to the real
    # clock would corrupt every expiry decision in a pinned CI run.
    set_today("next tuesday")
    with pytest.raises(ClockError):
        today()


def test_humanize_delta_phrases():
    base = dt.date(2026, 7, 13)
    assert humanize_delta(dt.date(2026, 7, 25), base) == "in 12d"
    assert humanize_delta(base, base) == "today"
    assert humanize_delta(dt.date(2026, 7, 10), base) == "3d ago"
