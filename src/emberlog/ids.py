"""Deterministic short entry ids.

Ids are the first six hex characters of a SHA-256 over the entry title and
its added date. Deterministic on purpose: the same ``emberlog add`` under a
pinned clock always yields the same id, which keeps tests, docs, and diffs
stable. Collisions (or re-adding the same title on the same day) bump a
counter into the hash until a free id is found.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re
from typing import Iterable

__all__ = ["ID_LENGTH", "new_id", "is_valid_id"]

ID_LENGTH = 6

_ID_RE = re.compile(r"^[0-9a-f]{6}$")


def is_valid_id(text: str) -> bool:
    """True when *text* is a well-formed emberlog id (6 lowercase hex chars)."""
    return bool(_ID_RE.match(text))


def new_id(title: str, added: _dt.date, taken: Iterable[str] = ()) -> str:
    """Derive a fresh id for an entry, avoiding every id in *taken*.

    The nonce loop terminates in practice long before 16^6 attempts; the
    hard cap only guards against a pathological ``taken`` set.
    """
    existing = set(taken)
    for nonce in range(100_000):
        digest = hashlib.sha256(
            f"{title}\n{added.isoformat()}\n{nonce}".encode("utf-8")
        ).hexdigest()
        candidate = digest[:ID_LENGTH]
        if candidate not in existing:
            return candidate
    raise RuntimeError("id space exhausted")  # pragma: no cover
