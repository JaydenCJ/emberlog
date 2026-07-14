"""TTL (time-to-live) parsing, formatting, and expiry arithmetic.

A TTL is spelled as a positive integer plus a unit — ``45d``, ``8w``,
``6m``, ``1y`` — or the literal ``never`` for entries that are meant to
outlive the project (true constants). Month and year arithmetic is
calendar-aware with day clamping, so ``1m`` from Jan 31 lands on the last
day of February instead of overflowing into March.
"""

from __future__ import annotations

import calendar
import datetime as _dt
import re
from dataclasses import dataclass

from .errors import TtlError

__all__ = ["Ttl", "UNITS", "add_months"]

UNITS = ("d", "w", "m", "y")

_UNIT_NAMES = {"d": "day", "w": "week", "m": "month", "y": "year"}

_TTL_RE = re.compile(r"^(\d{1,4})([dwmy])$")

# Guard rail: a TTL over 20 years is almost certainly a typo (e.g. "300m"
# meant as minutes — emberlog has no sub-day units by design).
_MAX_DAYS_SANITY = 20 * 366


@dataclass(frozen=True)
class Ttl:
    """A parsed TTL: ``count`` of ``unit``, or the special ``never``."""

    count: int
    unit: str  # one of UNITS, or "never" (count is 0)

    @classmethod
    def parse(cls, text: str) -> "Ttl":
        """Parse ``45d`` / ``8w`` / ``6m`` / ``1y`` / ``never``."""
        text = text.strip().lower()
        if text == "never":
            return cls(0, "never")
        match = _TTL_RE.match(text)
        if not match:
            raise TtlError(
                f"invalid ttl {text!r}: expected <count><d|w|m|y> (e.g. 45d, "
                "8w, 6m, 1y) or 'never'"
            )
        count = int(match.group(1))
        if count == 0:
            raise TtlError(f"invalid ttl {text!r}: count must be at least 1")
        ttl = cls(count, match.group(2))
        if ttl.approx_days() > _MAX_DAYS_SANITY:
            raise TtlError(f"invalid ttl {text!r}: longer than 20 years — use 'never'")
        return ttl

    @property
    def is_never(self) -> bool:
        return self.unit == "never"

    def approx_days(self) -> int:
        """Rough day count, used only for sanity limits and sorting."""
        if self.is_never:
            return 10**9
        factor = {"d": 1, "w": 7, "m": 30, "y": 365}[self.unit]
        return self.count * factor

    def expiry(self, anchor: _dt.date) -> "_dt.date | None":
        """The date this TTL expires when anchored at *anchor* (None = never)."""
        if self.is_never:
            return None
        if self.unit == "d":
            return anchor + _dt.timedelta(days=self.count)
        if self.unit == "w":
            return anchor + _dt.timedelta(weeks=self.count)
        if self.unit == "m":
            return add_months(anchor, self.count)
        return add_months(anchor, self.count * 12)

    def __str__(self) -> str:
        if self.is_never:
            return "never"
        return f"{self.count}{self.unit}"

    def describe(self) -> str:
        """Human phrasing: ``45 days``, ``1 month``, ``never``."""
        if self.is_never:
            return "never"
        name = _UNIT_NAMES[self.unit]
        plural = "" if self.count == 1 else "s"
        return f"{self.count} {name}{plural}"


NEVER = Ttl(0, "never")


def add_months(anchor: _dt.date, months: int) -> _dt.date:
    """Calendar-aware month addition with end-of-month clamping.

    ``2026-01-31 + 1m`` is ``2026-02-28``: an entry added on the 31st must
    not silently gain extra days by rolling into the next month.
    """
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return _dt.date(year, month, day)
