"""The entry model: one decision, one block, one lifecycle.

An :class:`Entry` is a single dated claim in the log — a decision, a
constraint, a learned fact. Its lifecycle:

* ``active``   — live knowledge; listed, linted, trusted.
* ``expired``  — TTL ran out and ``sweep`` moved it to the archive.
* ``retired``  — a human or agent explicitly withdrew it (``retire``).

Expiry is computed, never stored authoritatively: the anchor is the last
renewal (or the added date) and the TTL projects forward from there. The
file does carry a redundant ``expires=`` field for human readers; the
writer recomputes it on every save and the linter flags hand-edited drift.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field, replace

from .clock import humanize_delta
from .provenance import Source
from .ttl import Ttl

__all__ = ["Entry", "CONFIDENCE_LEVELS", "STATUSES", "ACTIVE", "EXPIRED", "RETIRED"]

# Ordered weakest → strongest. The linter treats the bottom two as decaying
# faster than their TTL: an old guess is worse than no note at all.
CONFIDENCE_LEVELS = ("guess", "inferred", "observed", "verified")

ACTIVE = "active"
EXPIRED = "expired"
RETIRED = "retired"
STATUSES = (ACTIVE, EXPIRED, RETIRED)


@dataclass
class Entry:
    """One decision-log entry (a ``##`` block plus its ember metadata)."""

    title: str
    id: str
    added: _dt.date
    ttl: "Ttl | None" = None
    renewed: "_dt.date | None" = None
    checked: "_dt.date | None" = None
    source: "Source | None" = None
    confidence: "str | None" = None
    tags: "tuple[str, ...]" = ()
    status: str = ACTIVE
    swept: "_dt.date | None" = None
    reason: "str | None" = None
    body: str = ""
    # Unknown metadata keys, preserved verbatim so hand additions and
    # future emberlog versions round-trip losslessly.
    extras: "dict[str, str]" = field(default_factory=dict)
    # Known keys whose values failed to parse; re-emitted verbatim so a
    # typo never destroys data. The parser reports them as diagnostics.
    invalid: "dict[str, str]" = field(default_factory=dict)
    # The ``expires=`` value as stored in the file (may drift from the
    # computed value if hand-edited); None when absent.
    stored_expires: "_dt.date | None" = None
    # 1-based line number of the entry heading in the source file (0 for
    # entries built in memory).
    line: int = 0

    # -- derived ---------------------------------------------------------

    @property
    def anchor(self) -> _dt.date:
        """The date the TTL counts from: last renewal, else added."""
        return self.renewed or self.added

    @property
    def last_touch(self) -> _dt.date:
        """The most recent date anyone stood behind this entry."""
        candidates = [self.added]
        if self.renewed:
            candidates.append(self.renewed)
        if self.checked:
            candidates.append(self.checked)
        return max(candidates)

    @property
    def expires(self) -> "_dt.date | None":
        """Computed expiry date; None when no TTL or TTL is ``never``."""
        if self.ttl is None or self.ttl.is_never:
            return None
        return self.ttl.expiry(self.anchor)

    def is_expired(self, today: _dt.date) -> bool:
        """True when the computed expiry is strictly in the past."""
        expires = self.expires
        return expires is not None and expires < today

    def age_days(self, today: _dt.date) -> int:
        return (today - self.added).days

    def expiry_phrase(self, today: _dt.date) -> str:
        """Table-column phrasing: ``in 12d``, ``3d ago``, ``never``, ``no ttl``."""
        if self.ttl is None:
            return "no ttl"
        if self.ttl.is_never:
            return "never"
        expires = self.expires
        assert expires is not None
        return humanize_delta(expires, today)

    def with_body(self, body: str) -> "Entry":
        return replace(self, body=body)
