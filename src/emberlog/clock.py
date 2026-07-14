"""Day-granularity clock with a deterministic override.

emberlog reasons about knowledge decay in whole days: entries are stamped
with an ISO date (``2026-07-13``), never a time. All "what day is it?"
questions go through :func:`today`, which honors the ``EMBERLOG_TODAY``
environment variable so that tests, examples, and the smoke script are
fully reproducible regardless of when they run.
"""

from __future__ import annotations

import datetime as _dt
import os

from .errors import ClockError

__all__ = ["ENV_TODAY", "today", "parse_date", "format_date", "humanize_delta"]

ENV_TODAY = "EMBERLOG_TODAY"

_ISO_LENGTH = 10  # len("2026-07-13")


def parse_date(text: str) -> _dt.date:
    """Parse a strict ISO ``YYYY-MM-DD`` date.

    Rejects datetimes, slashes, and two-digit years — log files are shared
    artifacts, so only one unambiguous spelling is accepted.
    """
    text = text.strip()
    if len(text) != _ISO_LENGTH:
        raise ClockError(f"invalid date {text!r}: expected YYYY-MM-DD")
    try:
        return _dt.date.fromisoformat(text)
    except ValueError as exc:
        raise ClockError(f"invalid date {text!r}: {exc}") from exc


def format_date(value: _dt.date) -> str:
    """Render a date as ISO ``YYYY-MM-DD``."""
    return value.isoformat()


def today() -> _dt.date:
    """Return the current date, honoring the ``EMBERLOG_TODAY`` override.

    The override exists for reproducibility: CI, tests, and documentation
    can pin the clock (``EMBERLOG_TODAY=2026-07-13``) and get byte-identical
    output forever. An unparseable override is an error, not a silent
    fallback — a typo here would silently corrupt every expiry decision.
    """
    override = os.environ.get(ENV_TODAY)
    if override is not None and override.strip():
        try:
            return parse_date(override)
        except ClockError as exc:
            raise ClockError(f"invalid {ENV_TODAY} override: {exc}") from exc
    return _dt.date.today()


def humanize_delta(target: _dt.date, base: _dt.date) -> str:
    """Describe *target* relative to *base*: ``in 12d``, ``today``, ``3d ago``.

    Compact on purpose — this string is used in table columns.
    """
    days = (target - base).days
    if days == 0:
        return "today"
    if days > 0:
        return f"in {days}d"
    return f"{-days}d ago"
