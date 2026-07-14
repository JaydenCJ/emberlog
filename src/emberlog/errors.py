"""Exception types raised by emberlog.

Every error the package raises deliberately derives from ``EmberlogError``,
so callers embedding the library can catch one type. The CLI maps these to
exit code 2 (usage/IO problems) as opposed to exit code 1 (lint findings).
"""

from __future__ import annotations

__all__ = [
    "EmberlogError",
    "ClockError",
    "TtlError",
    "ProvenanceError",
    "NotEmberlogFileError",
    "EntryNotFoundError",
    "AmbiguousIdError",
    "DuplicateIdError",
    "FieldError",
]


class EmberlogError(Exception):
    """Base class for all emberlog errors."""


class ClockError(EmberlogError):
    """The EMBERLOG_TODAY override or a date field could not be parsed."""


class TtlError(EmberlogError):
    """A TTL string such as ``45d`` or ``never`` could not be parsed."""


class ProvenanceError(EmberlogError):
    """A source tag such as ``agent:claude-code`` could not be parsed."""


class NotEmberlogFileError(EmberlogError):
    """The target file exists but carries no ``<!-- emberlog v1 -->`` marker."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"{path} is not an emberlog file (missing '<!-- emberlog v1 -->' "
            "marker); run 'emberlog init' to create one"
        )
        self.path = path


class EntryNotFoundError(EmberlogError):
    """No entry matches the requested id (or id prefix)."""

    def __init__(self, entry_id: str) -> None:
        super().__init__(f"no entry with id {entry_id!r}")
        self.entry_id = entry_id


class AmbiguousIdError(EmberlogError):
    """An id prefix matches more than one entry."""

    def __init__(self, prefix: str, matches: list) -> None:
        ids = ", ".join(sorted(m.id for m in matches))
        super().__init__(f"id prefix {prefix!r} is ambiguous: matches {ids}")
        self.prefix = prefix


class DuplicateIdError(EmberlogError):
    """An explicit id collides with an existing entry."""

    def __init__(self, entry_id: str) -> None:
        super().__init__(f"an entry with id {entry_id!r} already exists")
        self.entry_id = entry_id


class FieldError(EmberlogError):
    """A metadata field value is invalid (bad date, confidence, etc.)."""
